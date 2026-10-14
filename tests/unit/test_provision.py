import pytest

from wikidb.client import PageRef

from fakes import FakeXWiki
from wikidb.provision import (GLOBAL_RIGHTS_CLASS, PREFERENCES_CLASS, Bureau, Rule, apply, target_state)

A = Bureau("A", "Bureau A", "secteur")
B = Bureau("B", "Bureau B", "secteur")
S1 = Bureau("S1", "Synthèse 1", "synthese")


def wiki_with_flavor() -> FakeXWiki:
    wiki = FakeXWiki()
    # What the Standard flavor leaves behind: preferences object and the admin group's rights.
    wiki.seed_object("XWiki.XWikiPreferences", PREFERENCES_CLASS, {"authenticate_view": "0"})
    wiki.seed_object("XWiki.XWikiPreferences", GLOBAL_RIGHTS_CLASS,
                     {"groups": "XWiki.XWikiAdminGroup", "users": "", "levels": "admin,programming", "allow": "1"})
    return wiki


def rules(wiki: FakeXWiki, space: str) -> set[Rule]:
    return {Rule.from_properties(p) for p in wiki.objs(f"{space}.WebPreferences", GLOBAL_RIGHTS_CLASS)}


def test_sector_space_is_readable_by_owner_and_synthesis_and_editable_by_owner_only():
    wiki = wiki_with_flavor()
    apply(wiki, target_state([A, S1]))
    assert rules(wiki, "Mesures.A.Secteur") == {
        Rule(("XWiki.GroupeA", "XWiki.GroupeSynthese"), ("view",)),
        Rule(("XWiki.GroupeA",), ("delete", "edit")),
    }
    # Synthesis-perimeter sheets inherit the wiki-wide view and are edited by the owner only.
    assert rules(wiki, "Mesures.A.Synthese") == {Rule(("XWiki.GroupeA",), ("delete", "edit"))}
    assert rules(wiki, "Bureaux.A") == {Rule(("XWiki.GroupeA",), ("delete", "edit", "view"))}


def test_synthesis_bureaux_are_members_of_the_synthesis_group():
    wiki = wiki_with_flavor()
    apply(wiki, target_state([A, S1]))
    assert wiki.members("XWiki.GroupeSynthese") == {"XWiki.GroupeS1"}


def test_switching_a_bureau_to_synthesis_adds_it_to_the_synthesis_group_on_next_run():
    wiki = wiki_with_flavor()
    apply(wiki, target_state([A, B, S1]))
    apply(wiki, target_state([A, Bureau("B", "Bureau B", "synthese"), S1]))
    assert wiki.members("XWiki.GroupeSynthese") == {"XWiki.GroupeB", "XWiki.GroupeS1"}
    apply(wiki, target_state([A, B, S1]))
    assert wiki.members("XWiki.GroupeSynthese") == {"XWiki.GroupeS1"}


def test_second_run_changes_nothing():
    wiki = wiki_with_flavor()
    state = target_state([A, B, S1])
    apply(wiki, state)
    writes = wiki.writes
    report = apply(wiki, state)
    assert report.changes == []
    assert wiki.writes == writes


def test_wiki_level_rules_restrict_access_to_direction_agents_and_scripts_to_admins():
    wiki = wiki_with_flavor()
    apply(wiki, target_state([A]))
    wiki_rules = {Rule.from_properties(p) for p in wiki.objs("XWiki.XWikiPreferences", GLOBAL_RIGHTS_CLASS)}
    assert Rule(("XWiki.GroupeDirection",), ("comment", "edit", "view")) in wiki_rules
    assert Rule(("XWiki.XWikiAdminGroup",), ("register", "script")) in wiki_rules
    # The flavor's own admin rule is left alone.
    assert Rule(("XWiki.XWikiAdminGroup",), ("admin", "programming")) in wiki_rules
    prefs = wiki.objs("XWiki.XWikiPreferences", PREFERENCES_CLASS)[0]
    assert prefs["authenticate_view"] == "1" and prefs["default_language"] == "fr"


def test_application_code_and_group_pages_are_editable_by_admins_only():
    wiki = wiki_with_flavor()
    apply(wiki, target_state([A]))
    admins = {Rule(("XWiki.XWikiAdminGroup",), ("delete", "edit"))}
    for space in ("Mesures", "Procedures", "Annuaire", "Glossaire.Code", "XWiki", "Mesures.A"):
        assert rules(wiki, space) == admins, space


def test_rights_changed_by_hand_are_restored():
    wiki = wiki_with_flavor()
    state = target_state([A, S1])
    apply(wiki, state)
    wiki.seed_object("Mesures.A.Secteur.WebPreferences", GLOBAL_RIGHTS_CLASS,
                     {"groups": "XWiki.XWikiAllGroup", "users": "", "levels": "view", "allow": "1"})
    report = apply(wiki, state)
    assert any("Mesures.A.Secteur" in c for c in report.changes)
    assert Rule(("XWiki.XWikiAllGroup",), ("view",)) not in rules(wiki, "Mesures.A.Secteur")


def test_spaces_of_bureaux_missing_from_the_registry_are_reported_not_deleted():
    wiki = wiki_with_flavor()
    apply(wiki, target_state([A, B]))
    report = apply(wiki, target_state([A]), existing_bureau_spaces=["A", "B"])
    assert report.orphans == ["B"]
    assert wiki.page_exists(PageRef(("Mesures", "B", "Secteur")))


def test_registry_rejects_unknown_type_and_duplicate_codes():
    with pytest.raises(ValueError):
        Bureau("C", "Bureau C", "autre")
    with pytest.raises(ValueError):
        target_state([A, Bureau("A", "Doublon", "secteur")])
