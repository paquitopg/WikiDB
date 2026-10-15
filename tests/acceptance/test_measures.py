"""Measure sheet application on a provisioned dev wiki (U6; R1-R4, R8, KTD6, KTD8).

Sheets are created through the real creation form (Mesures.NouvelleMesure) and deleted at the end of the run.
"""

import re
from concurrent.futures import ThreadPoolExecutor

from wikidb.client import PageRef, XWikiClient
from wikidb.measures import FIELDS, MESURE_CLASS, PROVENANCE_CLASS, identifier_number

FORM = PageRef(("Mesures",), "NouvelleMesure")
FILLED = {
    "dateCreation": "01/01/2020",
    "vecteurJuridique": "LFI 2020, article 1",
    "raisonEtre": "Raison d'être de test.",
    "modalitesModification": "Modalités de test.",
    "documentationInterne": "Note interne de test.",
    "documentationExterne": "Rapport public de test.",
}


def _html(agent, action: str, page: PageRef, **params):
    path = "/".join(page.spaces) + "/" + page.name
    return agent.session.get(f"{agent.base_url}/bin/{action}/{path}", params=params,
                             headers={"Accept": "text/html"})


def _token(html: str) -> str:
    match = re.search(r'name="form_token" value="([^"]*)"', html) or re.search(r'data-xwiki-form-token="([^"]*)"', html)
    assert match, "no CSRF token in the page"
    return match.group(1)


def create(agent, title: str, bureau: str, perimeter: str = "Secteur"):
    """Submit the creation form; return the response without following the redirect to the editor."""
    token = _token(_html(agent, "view", FORM).text)
    path = "/".join(FORM.spaces) + "/" + FORM.name
    return agent.session.post(f"{agent.base_url}/bin/view/{path}", allow_redirects=False,
                              headers={"Accept": "text/html"},
                              data={"form_token": token, "intitule": title, "bureau": bureau,
                                    "perimetre": perimeter})


def created_page(response) -> PageRef:
    errors = [re.sub(r"<[^>]+>|\s+", " ", e)[:400] for e in
              re.findall(r'class="box (?:errormessage|xwikirenderingerror)">(.*?)</div>', response.text, flags=re.S)]
    assert response.status_code in (301, 302, 303), errors or response.status_code
    match = re.search(r"/bin/edit/((?:[^/?]+/)+[^/?]+)", response.headers["Location"])
    *spaces, name = match.group(1).split("/")
    return PageRef(tuple(spaces), name)


def client_for(agent) -> XWikiClient:
    return XWikiClient(agent.base_url, *agent.session.auth)


def test_creation_places_the_sheet_under_the_bureau_and_perimeter(world, made, robot):
    a = world["agents"]["test-agent-a"]
    for perimeter in ("Secteur", "Synthese"):
        page = created_page(create(a, f"Mesure créée {perimeter} zorglubC", "A", perimeter))
        made.append(page)
        assert page.spaces == ("Mesures", "A", perimeter)
        assert identifier_number(page.name) is not None, page.name
        assert robot.get_page(page)["title"] == f"Mesure créée {perimeter} zorglubC"
        assert len(robot.list_objects(page, MESURE_CLASS)) == 1


def test_concurrent_creations_get_distinct_identifiers(world, made):
    # Same space (the database rejects the duplicate) and different spaces (the form detects it).
    a, a2 = world["agents"]["test-agent-a"], world["agents"]["test-agent-a2"]
    calls = [(a, "Secteur"), (a2, "Secteur"), (a, "Synthese"), (a2, "Synthese")] * 2
    with ThreadPoolExecutor(len(calls)) as pool:
        responses = list(pool.map(lambda call: create(call[0], "Mesure concurrente", "A", call[1]), calls))
    pages = [created_page(r) for r in responses]
    made.extend(pages)
    assert len({p.name for p in pages}) == len(pages)


def test_agent_cannot_create_a_sheet_for_another_bureau(world, robot):
    a = world["agents"]["test-agent-a"]
    before = set(robot.list_class_pages(MESURE_CLASS))
    response = create(a, "Mesure usurpée", "B")
    assert response.status_code == 200
    assert "votre bureau" in response.text
    assert set(robot.list_class_pages(MESURE_CLASS)) == before


def test_agent_without_bureau_is_offered_no_form(world):
    html = _html(world["agents"]["test-agent-nobureau"], "view", FORM).text
    assert "Créer la fiche" not in html


def test_provenance_blocks_and_directory_link(world, made, robot):
    a = world["agents"]["test-agent-a"]
    page = created_page(create(a, "Mesure avec provenances", "A"))
    made.append(page)
    sender = PageRef(("Annuaire", "Externes"), "TestEmetteur")
    robot.put_page(sender, "Émetteur de test")
    made.append(sender)
    writer = client_for(a)
    writer.add_object(page, PROVENANCE_CLASS, {"donnee": "Effectifs zorglubP1", "emetteur": "Service fictif",
                                               "ficheAnnuaire": "Annuaire.Externes.TestEmetteur",
                                               "frequence": "mensuelle"})
    writer.add_object(page, PROVENANCE_CLASS, {"donnee": "Crédits zorglubP2", "emetteur": "Autre service"})
    html = _html(a, "view", page).text
    assert "zorglubP1" in html and "zorglubP2" in html
    assert re.search(r'href="[^"]*/Annuaire/Externes/TestEmetteur"[^>]*>Service fictif<', html)
    assert "Mensuelle" in html


def test_edit_form_adds_and_removes_provenance_blocks(world, made, robot):
    a = world["agents"]["test-agent-a"]
    page = created_page(create(a, "Mesure éditée", "A"))
    made.append(page)
    form = _html(a, "edit", page, editor="inline").text
    assert 'name="objectPolicy"' in form and "Mesures.Code.ProvenanceClass_0_donnee" in form
    path = "/".join(page.spaces) + "/" + page.name
    save = f"{a.base_url}/bin/save/{path}"
    r = a.session.post(save, headers={"Accept": "text/html"},
                       data={"form_token": _token(form), "title": "Mesure éditée",
                             "objectPolicy": "updateOrCreate",
                             "Mesures.Code.MesureClass_0_vecteurJuridique": "LFI test",
                             "Mesures.Code.ProvenanceClass_0_donnee": "Donnée ajoutée",
                             "Mesures.Code.ProvenanceClass_0_emetteur": "Émetteur ajouté"})
    assert r.status_code == 200
    assert robot.list_objects(page, MESURE_CLASS)[0].properties["vecteurJuridique"] == "LFI test"
    assert [o.properties["donnee"] for o in robot.list_objects(page, PROVENANCE_CLASS)] == ["Donnée ajoutée"]

    form = _html(a, "edit", page, editor="inline").text
    assert 'value="Mesures.Code.ProvenanceClass_0"' in form
    r = a.session.post(save, headers={"Accept": "text/html"},
                       data={"form_token": _token(form), "title": "Mesure éditée",
                             "deletedObjects": "Mesures.Code.ProvenanceClass_0"})
    assert r.status_code == 200
    assert robot.list_objects(page, PROVENANCE_CLASS) == []


def test_sheet_shows_last_modification(world, made):
    a = world["agents"]["test-agent-a"]
    page = created_page(create(a, "Mesure datée", "A"))
    made.append(page)
    html = _html(a, "view", page).text
    assert "Dernière modification" in html and "test-agent-a" in html


def test_completeness_needs_every_field_and_a_named_provenance(world, made):
    a = world["agents"]["test-agent-a"]
    page = created_page(create(a, "Mesure à compléter", "A"))
    made.append(page)
    writer = client_for(a)

    def complete() -> bool:
        html = _html(a, "view", page).text
        assert ("Fiche complète" in html) != ("Fiche incomplète" in html)
        return "Fiche complète" in html

    assert not complete()
    writer.update_object(page, MESURE_CLASS, 0, FILLED)
    assert not complete()                                   # no provenance yet
    writer.add_object(page, PROVENANCE_CLASS, {"donnee": "Donnée sans émetteur"})
    assert not complete()                                   # provenance without a sender
    writer.update_object(page, PROVENANCE_CLASS, 0, {"emetteur": "Service fictif"})
    assert complete()
    writer.update_object(page, MESURE_CLASS, 0, {"documentationExterne": ""})
    assert not complete()


def _listing(agent, space_filter: str) -> set[str]:
    r = agent.session.get(f"{agent.base_url}/bin/get/XWiki/LiveTableResults",
                          params={"outputSyntax": "plain", "className": MESURE_CLASS, "collist": "doc.title,doc.space",
                                  "doc.space": space_filter, "limit": 500, "reqNo": 1},
                          headers={"Accept": "application/json"})
    assert r.status_code == 200, r.text[:300]
    return {row["doc_fullName"] for row in r.json()["rows"]}


def test_listing_shows_only_readable_sheets_and_filters_by_bureau(world, made, robot):
    a = world["agents"]["test-agent-a"]
    own = created_page(create(a, "Mesure listée A", "A"))
    made.append(own)
    others = {
        "b_secteur": PageRef(("Mesures", "B", "Secteur"), "M-9101"),
        "s1_secteur": PageRef(("Mesures", "S1", "Secteur"), "M-9102"),
        "s1_synthese": PageRef(("Mesures", "S1", "Synthese"), "M-9103"),
    }
    for page in others.values():
        robot.put_page(page, "Mesure listée")
        if not robot.list_objects(page, MESURE_CLASS):
            robot.add_object(page, MESURE_CLASS, {f: "" for f in FIELDS})
        made.append(page)

    everything = _listing(a, "Mesures.")
    assert str(own) in everything and str(others["s1_synthese"]) in everything
    assert str(others["b_secteur"]) not in everything and str(others["s1_secteur"]) not in everything

    only_a = _listing(a, "Mesures.A.")
    assert str(own) in only_a
    assert all(name.startswith("Mesures.A.") for name in only_a)

    synthesis = _listing(a, ".Synthese")
    assert str(others["s1_synthese"]) in synthesis
    assert all(".Synthese." in name for name in synthesis)
