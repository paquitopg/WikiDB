"""Procedures, glossary and who-does-what on a provisioned dev wiki (U7; R10, R12-R14, R24)."""

import html
import json
import re
import secrets

import pytest

from test_measures import client_for
from wikidb.client import PageRef, XWikiError

DENIED = (401, 403)
PROCEDURE = "Procedures.Code.ProcedureClass"
TERME = "Glossaire.Code.TermeClass"
ENTREE = "Annuaire.Code.BureauEntreeClass"


@pytest.fixture
def made(robot):
    pages: list[PageRef] = []
    yield pages
    for page in pages:
        robot.delete_page(page)


def _labels(agent, page: PageRef) -> set[str]:
    path = "/".join(page.spaces) + "/" + page.name
    text = agent.session.get(f"{agent.base_url}/bin/view/{path}", headers={"Accept": "text/html"}).text
    names = set()
    for config in re.findall(r'data-config="([^"]*)"', text):
        names |= {p.get("name") for p in json.loads(html.unescape(config))["meta"]["propertyDescriptors"]}
    return names


def test_owning_bureau_edits_its_procedure_and_other_bureaux_only_read_it(world, made):
    a, b = world["agents"]["test-agent-a"], world["agents"]["test-agent-b"]
    page = PageRef(("Procedures", "A"), f"Essai-{secrets.token_hex(3)}")
    made.append(page)
    writer = client_for(a)
    writer.put_page(page, "Procédure d'essai")
    writer.add_object(page, PROCEDURE, {"objet": "Préparer le PLF", "etapes": "1. Collecter", "dateRevue": "01/09/2026"})
    writer.update_object(page, PROCEDURE, 0, {"calendrier": "Chaque année en juin"})
    assert b.get(page).status_code == 200
    assert "Préparer le PLF" in b.view_html(page).text
    assert b.put(page, "Modifié", "x").status_code in DENIED
    with pytest.raises(XWikiError):
        client_for(b).update_object(page, PROCEDURE, 0, {"objet": "Détourné"})


def test_any_direction_agent_creates_and_edits_a_glossary_term(world, made):
    agent = world["agents"]["test-agent-nobureau"]
    page = PageRef(("Glossaire",), f"Terme-{secrets.token_hex(3)}")
    made.append(page)
    writer = client_for(agent)
    writer.put_page(page, "Crédit de paiement")
    writer.add_object(page, TERME, {"definition": "Limite supérieure des dépenses pouvant être payées."})
    writer.update_object(page, TERME, 0, {"definition": "Plafond des dépenses payables dans l'année."})
    view = agent.view_html(page).text
    assert "Plafond des dépenses payables" in view
    assert "[[Crédit de paiement&gt;&gt;Glossaire." in view or "[[Crédit de paiement>>Glossaire." in view


def test_only_administrators_create_external_senders(world):
    a = world["agents"]["test-agent-a"]
    assert a.put(PageRef(("Annuaire", "Externes"), "Detourne"), "Émetteur", "x").status_code in DENIED


def test_external_sender_form_has_professional_fields_only(robot):
    r = robot.session.get(f"{robot.base}/classes/Annuaire.Code.EmetteurClass")
    assert r.status_code == 200
    fields = {p["name"] for p in r.json()["properties"]}
    assert fields == {"organisme", "service", "donnees", "contactFonctionnel", "telephoneService"}


def test_bureau_members_complete_their_directory_entry_and_others_cannot(world):
    page = PageRef(("Annuaire", "Bureaux", "A"))
    client_for(world["agents"]["test-agent-a"]).update_object(page, ENTREE, 0, {"missions": "Missions fictives de A"})
    assert "Missions fictives de A" in world["agents"]["test-agent-b"].view_html(page).text
    with pytest.raises(XWikiError):
        client_for(world["agents"]["test-agent-b"]).update_object(page, ENTREE, 0, {"missions": "Détourné"})


def test_listings_use_french_labels(world):
    agent = world["agents"]["test-agent-a"]
    assert {"Procédure", "Dernière revue"} <= _labels(agent, PageRef(("Procedures",)))
    assert {"Terme", "Définition"} <= _labels(agent, PageRef(("Glossaire",)))
    assert {"Bureau", "Missions", "Émetteur", "Données transmises"} <= _labels(agent, PageRef(("Annuaire",)))
