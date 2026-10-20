"""Acceptance fixtures: fictitious bureaux, users and sheets on a dev wiki (never production data, R20).

Run: pytest tests/acceptance --base-url http://localhost:8085   (robot credentials from the environment or
/secrets/app, see tools/wikidb/client.py). Provision bureaux A, B (sector) and S1 (synthesis) first.
"""

import secrets
import sys
import time
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from wikidb.client import PageRef, XWikiClient, setting  # noqa: E402
from wikidb.provision import set_group_members  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from cleanup import TEST_USERS  # noqa: E402

# One marker word per sheet makes search assertions unambiguous.
SHEETS = {
    "a_secteur": (("Mesures", "A", "Secteur"), "M-9001", "Mesure fictive A secteur zorglubA"),
    "b_secteur": (("Mesures", "B", "Secteur"), "M-9002", "Mesure fictive B secteur zorglubB"),
    "s1_secteur": (("Mesures", "S1", "Secteur"), "M-9003", "Mesure fictive S1 secteur zorglubS"),
    "s1_synthese": (("Mesures", "S1", "Synthese"), "M-9004", "Mesure fictive S1 synthese zorglubT"),
}
USERS = {  # name -> groups
    "test-agent-a": ["GroupeDirection", "GroupeA"],
    "test-agent-a2": ["GroupeDirection", "GroupeA"],
    "test-agent-b": ["GroupeDirection", "GroupeB"],
    "test-agent-s1": ["GroupeDirection", "GroupeS1"],
    "test-agent-nobureau": ["GroupeDirection"],
    "test-outsider": [],
}
assert {f"XWiki.{u}" for u in USERS} == TEST_USERS, "keep cleanup.TEST_USERS in step with USERS"


def pytest_addoption(parser):
    parser.addoption("--base-url", default=None, help="dev wiki URL for acceptance tests")
    parser.addoption("--export-url", default=None,
                     help="deployed export service (e.g. the wiki URL); default: run it in-process")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--base-url"):
        skip = pytest.mark.skip(reason="acceptance tests need --base-url")
        for item in items:
            item.add_marker(skip)


class Agent:
    """A test user talking to the wiki through REST and page views."""

    def __init__(self, base_url: str, name: str | None, password: str | None):
        self.base_url, self.name = base_url.rstrip("/"), name
        self.session = requests.Session()
        if name:
            self.session.auth = (name, password)
        self.session.headers["Accept"] = "application/json"

    def get(self, page: PageRef):
        return self.session.get(f"{self.base_url}/rest/wikis/xwiki{page.path()}")

    def put(self, page: PageRef, title: str, content: str):
        return self.session.put(f"{self.base_url}/rest/wikis/xwiki{page.path()}",
                                json={"title": title, "content": content})

    def view_html(self, page: PageRef) -> requests.Response:
        path = "/".join(page.spaces) + "/" + page.name
        return self.session.get(f"{self.base_url}/bin/view/{path}", headers={"Accept": "text/html"})

    def plain(self, page: PageRef) -> str:
        path = "/".join(page.spaces) + "/" + page.name
        return self.session.get(f"{self.base_url}/bin/get/{path}", params={"xpage": "plain"},
                                headers={"Accept": "text/html"}).text

    def search(self, word: str) -> list[str]:
        r = self.session.get(f"{self.base_url}/rest/wikis/query",
                             params={"q": word, "type": "solr", "number": 50})
        if r.status_code != 200:
            return []
        return [h.get("pageFullName") or h.get("id") for h in r.json().get("searchResults", [])]


@pytest.fixture(scope="session")
def base_url(request):
    return request.config.getoption("--base-url")


@pytest.fixture(scope="session")
def robot(base_url):
    return XWikiClient(base_url, setting("WIKIDB_ROBOT_USER", "wikidb-robot"), setting("WIKIDB_ROBOT_PASSWORD"))


@pytest.fixture(scope="session")
def world(base_url, robot):
    """Create users, memberships and sheets once per run; return agents and page references."""
    passwords = {}
    for name in USERS:
        page = PageRef(("XWiki",), name)
        passwords[name] = secrets.token_hex(12)
        if not robot.page_exists(page):
            robot.put_page(page, name, hidden=True)
        users = robot.list_objects(page, "XWiki.XWikiUsers")
        props = {"first_name": name, "active": "1", "password": passwords[name]}
        if users:
            robot.update_object(page, "XWiki.XWikiUsers", users[0].number, props)
        else:
            robot.add_object(page, "XWiki.XWikiUsers", props)
    for group in ("GroupeDirection", "GroupeA", "GroupeB", "GroupeS1"):
        wanted = {f"XWiki.{u}" for u, groups in USERS.items() if group in groups}
        # Keep members that are not test users (e.g. HR-synced agents on a shared dev wiki).
        current = {o.properties.get("member") for o in robot.list_objects(PageRef(("XWiki",), group),
                                                                          "XWiki.XWikiGroups")}
        keep = {m for m in current if m and not m.startswith("XWiki.test-")}
        set_group_members(robot, PageRef(("XWiki",), group), wanted | keep, [])
    pages = {}
    for key, (spaces, name, title) in SHEETS.items():
        pages[key] = PageRef(spaces, name)
        robot.put_page(pages[key], title, f"Contenu de test : {title}.")
    # A sheet of A linking to B's sector sheet (AE5).
    pages["a_links_b"] = PageRef(("Mesures", "A", "Secteur"), "M-9005")
    robot.put_page(pages["a_links_b"], "Mesure fictive A avec lien",
                   "Voir [[Mesures.B.Secteur.M-9002]] pour comparaison.")
    # Wait for the search index to catch up with the new sheets.
    deadline = time.time() + 120
    while time.time() < deadline and not robot_search(base_url, robot, "zorglubB"):
        time.sleep(3)
    agents = {name: Agent(base_url, name, passwords[name]) for name in USERS}
    agents["guest"] = Agent(base_url, None, None)
    return {"agents": agents, "pages": pages}


@pytest.fixture(scope="module")
def made(robot):
    """Pages a test module creates, deleted by the robot after the module."""
    pages: list[PageRef] = []
    yield pages
    for page in pages:
        robot.delete_page(page)


def robot_search(base_url, robot, word) -> bool:
    r = robot.session.get(f"{base_url.rstrip('/')}/rest/wikis/query", params={"q": word, "type": "solr"})
    return r.status_code == 200 and bool(r.json().get("searchResults"))
