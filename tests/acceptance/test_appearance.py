"""DSFR appearance on a dev wiki: offline DSFR files, State header and footer, XWiki tools kept (DSFR plan U1-U4)."""

import re
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests

from conftest import Agent
from wikidb.client import PageRef, setting

ROOT = Path(__file__).resolve().parents[2]
DSFR_VERSION = re.search(r"<dsfr.version>([^<]+)</dsfr.version>", (ROOT / "xwiki/pom.xml").read_text()).group(1)
HOME = PageRef(("Main",), "WebHome")
NAVIGATION = ("Mesures", "Procedures", "Glossaire", "Annuaire", "Modeles")
FOOTER_PAGES = ("Accessibilite", "MentionsLegales", "DonneesPersonnelles")


def header(html: str) -> str:
    """The DSFR header up to its menu, where XWiki's tools sit."""
    start = html.index('class="fr-header"')
    return html[start:html.index('id="wikidbMenu"', start)]


def stylesheets(html: str) -> list[str]:
    return re.findall(r'<link\b[^>]*\bhref="([^"]+\.css[^"]*)"', html)


def test_wiki_serves_the_pinned_dsfr_files_itself(world, base_url):
    a = world["agents"]["test-agent-a"]
    core = next(h for h in stylesheets(a.view_html(HOME).text) if "/wikidb-dsfr/" in h and "core.min.css" in h)
    css = a.session.get(urljoin(base_url, core), headers={"Accept": "*/*"})
    assert css.status_code == 200 and "text/css" in css.headers["Content-Type"]
    assert f"DSFR v{DSFR_VERSION} " in css.text[:300]      # the DSFR stamps its version in the CSS header comment
    font = a.session.get(urljoin(base_url, core.replace("core/core.min.css", "fonts/Marianne-Regular.woff2")),
                         headers={"Accept": "*/*"})
    assert font.status_code == 200 and font.content[:4] == b"wOF2"


def test_every_page_shows_the_dsfr_header_navigation_and_footer(world):
    html = world["agents"]["test-agent-a"].view_html(HOME).text
    top = header(html)
    assert 'class="fr-logo"' in top and "Direction du Budget" in top
    nav = html[html.index('id="wikidbNavigation"'):]
    for space in NAVIGATION:
        assert f'href="/bin/view/{space}/"' in nav, space
    footer = html[html.index('class="fr-footer"'):]
    for page in FOOTER_PAGES:
        assert f'href="/bin/view/APropos/{page}"' in footer, page


def test_bridge_stylesheet_loads_after_the_dsfr_stylesheets(world):
    sheets = stylesheets(world["agents"]["test-agent-a"].view_html(HOME).text)
    dsfr = [i for i, h in enumerate(sheets) if "/wikidb-dsfr/" in h and "/dist/" in h]
    bridge = [i for i, h in enumerate(sheets) if h.split("?")[0].endswith("/wikidb/dsfr-bridge.css")]
    assert dsfr and bridge and max(dsfr) < bridge[0]


def test_xwiki_tools_stay_in_the_header(world, base_url):
    top = header(world["agents"]["test-agent-a"].view_html(HOME).text)
    for tool in ("headerglobalsearchinput", 'id="tmUser"', 'id="tmLogout"', 'id="tmDrawerActivator"'):
        assert tool in top, tool
    admin = Agent(base_url, setting("WIKIDB_ROBOT_USER", "wikidb-robot"), setting("WIKIDB_ROBOT_PASSWORD"))
    assert 'id="tmAdminWiki"' in header(admin.view_html(HOME).text)


def test_login_page_and_outsiders_get_the_dsfr_layout(world, base_url):
    login = requests.get(f"{base_url.rstrip('/')}/bin/login/XWiki/XWikiLogin", params={"oidc.skipped": "true"})
    assert 'class="fr-header"' in login.text and 'class="fr-footer"' in login.text
    outsider = world["agents"]["test-outsider"].view_html(world["pages"]["a_secteur"])
    assert 'class="fr-header"' in outsider.text and "zorglubA" not in outsider.text


def test_pages_load_resources_from_the_wiki_only(world, base_url):
    a = world["agents"]["test-agent-a"]
    own = urlsplit(base_url).netloc
    for page in (HOME, world["pages"]["a_secteur"]):
        html = a.view_html(page).text
        sources = re.findall(r'\bsrc="(https?://[^"/]+)', html)
        sources += re.findall(r'<link\b[^>]*\bhref="(https?://[^"/]+)', html)
        assert {urlsplit(s).netloc for s in sources} <= {own}, sources


def test_footer_pages_are_french_readable_by_agents_and_edited_by_admins_only(world):
    a = world["agents"]["test-agent-a"]
    for name, title in zip(FOOTER_PAGES, ("Accessibilité", "Mentions légales", "Données personnelles")):
        page = PageRef(("APropos",), name)
        r = a.get(page)
        assert r.status_code == 200 and r.json()["title"] == title, name
        assert a.put(page, title, "Modification par un agent").status_code in (401, 403), name
