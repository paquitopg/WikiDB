"""French page templates offered in bureau spaces and Main (U11; R24, R25, KTD19)."""

import re
import secrets

import pytest

from test_measures import client_for
from wikidb.client import PageRef

PROVIDERS = ("Modeles.Code.CompteRenduTemplateProvider", "Modeles.Code.NoteBreveTemplateProvider",
             "Modeles.Code.ReleveDecisionTemplateProvider")
DENIED = (401, 403)


def _create_dialog(agent, space: tuple[str, ...]) -> str:
    path = "/".join(space) + "/WebHome"
    return agent.session.get(f"{agent.base_url}/bin/create/{path}", headers={"Accept": "text/html"}).text


@pytest.fixture
def created(world):
    """Pages created by agent A, deleted by A: "save and edit" leaves A's edit lock, which blocks other deleters."""
    pages: list[PageRef] = []
    yield pages
    a = world["agents"]["test-agent-a"]
    for page in pages:
        client_for(a).delete_page(page)


def test_templates_are_offered_in_a_bureau_space_but_not_under_measures(world):
    a = world["agents"]["test-agent-a"]
    offered = set(re.findall(r'value="(Modeles\.Code\.[A-Za-z]+)"', _create_dialog(a, ("Bureaux", "A"))))
    assert offered == set(PROVIDERS)
    assert "Compte rendu de réunion" in _create_dialog(a, ("Bureaux", "A"))
    assert not re.findall(r'value="Modeles\.Code\.', _create_dialog(a, ("Mesures", "A", "Secteur")))


def test_page_created_from_the_minutes_template_has_its_headings(world, robot, created):
    a = world["agents"]["test-agent-a"]
    dialog = _create_dialog(a, ("Bureaux", "A"))
    token = re.search(r'data-xwiki-form-token="([^"]*)"', dialog).group(1)
    name = f"CR-essai-{secrets.token_hex(3)}"
    page = PageRef(("Bureaux", "A", name), "WebHome")
    created.append(page)
    r = a.session.post(f"{a.base_url}/bin/create/Bureaux/A/WebHome", headers={"Accept": "text/html"},
                       data={"form_token": token, "spaceReference": "Bureaux.A", "name": name,
                             "title": "Compte rendu d'essai", "tocreate": "nonterminal",
                             "templateprovider": "Modeles.Code.CompteRenduTemplateProvider"})
    assert r.status_code == 200, r.status_code
    content = robot.get_page(page)["content"]
    for heading in ("== Ordre du jour ==", "== Décisions ==", "== Actions =="):
        assert heading in content


def test_agents_cannot_edit_the_templates(world):
    a = world["agents"]["test-agent-a"]
    assert a.put(PageRef(("Modeles",), "CompteRendu"), "Détourné", "x").status_code in DENIED
    assert a.put(PageRef(("Modeles", "Code"), "CompteRenduTemplateProvider"), "Détourné", "x").status_code in DENIED
