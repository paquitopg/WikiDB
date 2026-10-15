from fakes import FakeXWiki
from wikidb.client import PageRef
from wikidb.measures import (FIELDS, MESURE_CLASS, PROVENANCE_CLASS, completeness, identifier, identifier_number,
                             is_complete, measure_page)

FILLED = {f: "x" for f in FIELDS[1:]}
NAMED = {"donnee": "Effectifs", "emetteur": "Service"}


def test_location_is_the_perimeter_and_names_are_neutral():
    assert measure_page("A", "synthese", identifier(42)) == PageRef(("Mesures", "A", "Synthese"), "M-0042")
    assert identifier_number("M-0042") == 42 and identifier_number("M-12345") == 12345
    assert identifier_number("Prime") is None


def test_complete_needs_every_field_but_the_source_key_and_one_named_provenance():
    assert is_complete(FILLED, [NAMED])
    assert is_complete(FILLED, [{"donnee": "Sans émetteur"}, NAMED])
    assert not is_complete(FILLED, [])
    assert not is_complete(FILLED, [{"donnee": "Sans émetteur"}])
    assert not is_complete({**FILLED, "raisonEtre": "  "}, [NAMED])
    assert not is_complete({k: v for k, v in FILLED.items() if k != "documentationExterne"}, [NAMED])


def test_completeness_counts_per_bureau_and_perimeter():
    wiki = FakeXWiki()
    sheets = {
        ("A", "secteur", 1): (FILLED, [NAMED]),
        ("A", "secteur", 2): ({}, []),
        ("A", "synthese", 3): (FILLED, [NAMED]),
        ("S1", "synthese", 4): (FILLED, []),
    }
    for (bureau, perimeter, n), (mesure, provenances) in sheets.items():
        page = measure_page(bureau, perimeter, identifier(n))
        wiki.put_page(page, "Mesure")
        wiki.add_object(page, MESURE_CLASS, mesure)
        for p in provenances:
            wiki.add_object(page, PROVENANCE_CLASS, p)
    template = PageRef(("Mesures", "Code"), "MesureTemplate")       # outside a bureau space: not counted
    wiki.put_page(template, "Modèle")
    wiki.add_object(template, MESURE_CLASS, {})
    assert completeness(wiki) == {("A", "Secteur"): (1, 2), ("A", "Synthese"): (1, 1), ("S1", "Synthese"): (0, 1)}
