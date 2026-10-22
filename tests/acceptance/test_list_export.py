"""Spreadsheet export of the measure list (Mesures.Code.ListeExport) against the dev wiki (R3, R7, R9)."""

import csv
import io

import pytest

from test_measures import FILLED, client_for, create, created_page
from wikidb.client import PageRef
from wikidb.measures import FIELDS, MESURE_CLASS, PROVENANCE_CLASS


@pytest.fixture(scope="module")
def sheets(world, robot):
    """A sheet of A whose fields hold rich text and a would-be formula, and a sector sheet of B."""
    a = world["agents"]["test-agent-a"]
    own = created_page(create(a, "Mesure listée zorglubL", "A"))
    writer = client_for(a)
    writer.update_object(own, MESURE_CLASS, 0, {**FILLED, "vecteurJuridique": "=1+1",
                                                "raisonEtre": "Une **raison** en gras."})
    writer.add_object(own, PROVENANCE_CLASS, {"donnee": "Effectifs listés", "emetteur": "Service émetteur",
                                              "frequence": "mensuelle"})
    other = PageRef(("Mesures", "B", "Secteur"), "M-9202")
    robot.put_page(other, "Mesure secrète de B zorglubM")
    if not robot.list_objects(other, MESURE_CLASS):
        robot.add_object(other, MESURE_CLASS, {f: "" for f in FIELDS})
    yield {"own": own, "other": other}
    for page in (own, other):
        robot.delete_page(page)


def export(agent, **filters):
    return agent.session.get(f"{agent.base_url}/bin/get/Mesures/Code/ListeExport", params=filters,
                             headers={"Accept": "text/csv"}, allow_redirects=False)


def rows(response) -> list[dict]:
    assert response.status_code == 200, response.status_code
    assert response.headers["Content-Type"].startswith("text/csv")
    assert response.content.startswith(b"\xef\xbb\xbf"), "no BOM: Excel would misread accents"
    return list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))


def test_list_holds_the_readers_sheets_and_their_fields(world, sheets):
    by_id = {r["Identifiant"]: r for r in rows(export(world["agents"]["test-agent-a"]))}
    row = by_id[sheets["own"].name]
    assert row["Intitulé"] == "Mesure listée zorglubL"
    assert (row["Bureau"], row["Périmètre"]) == ("A", "Sectoriel")
    assert row["Date de création"] == "01/01/2020"
    assert row["Raison d'être"] == "Une raison en gras."
    assert row["Provenances"] == "Effectifs listés : Service émetteur, mensuelle"
    assert row["Complète"] == "oui"
    assert row["Adresse"].endswith("/" + "/".join(sheets["own"].spaces) + "/" + sheets["own"].name)


def test_formula_cells_are_neutralised(world, sheets):
    by_id = {r["Identifiant"]: r for r in rows(export(world["agents"]["test-agent-a"]))}
    assert by_id[sheets["own"].name]["Vecteur juridique"] == "'=1+1"


def test_list_hides_sheets_the_reader_cannot_view(world, sheets):
    a = world["agents"]["test-agent-a"]
    titles = {r["Intitulé"] for r in rows(export(a))} | {r["Intitulé"] for r in rows(export(a, bureau="B"))}
    assert "Mesure secrète de B zorglubM" not in titles
    s1 = {r["Identifiant"] for r in rows(export(world["agents"]["test-agent-s1"], bureau="B"))}
    assert sheets["other"].name in s1


def test_filters_narrow_the_list_and_name_the_file(world, sheets):
    response = export(world["agents"]["test-agent-a"], bureau="A", perimetre="Synthese")
    assert {(r["Bureau"], r["Périmètre"]) for r in rows(response)} <= {("A", "Synthèse")}
    assert 'filename="mesures-a-synthese.csv"' in response.headers["Content-Disposition"]


def test_guest_gets_no_file(world, sheets):
    response = export(world["agents"]["guest"])
    assert not response.headers.get("Content-Type", "").startswith("text/csv")
