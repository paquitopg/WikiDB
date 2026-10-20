import sys
from pathlib import Path

from fakes import FakeXWiki
from wikidb.provision import BUREAU_CLASS, GLOBAL_RIGHTS_CLASS, PREFERENCES_CLASS, Bureau, apply, target_state

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "acceptance"))
import cleanup  # noqa: E402

GROUPS = "XWiki.XWikiGroups"


def test_removes_the_suite_leftovers_and_keeps_real_bureaux_and_members():
    wiki = FakeXWiki()
    wiki.seed_object("XWiki.XWikiPreferences", PREFERENCES_CLASS, {"authenticate_view": "0"})
    wiki.seed_object("XWiki.XWikiPreferences", GLOBAL_RIGHTS_CLASS,
                     {"groups": "XWiki.XWikiAdminGroup", "users": "", "levels": "admin", "allow": "1"})
    bureaux = [Bureau("A", "A", "secteur"), Bureau("B", "B", "secteur"), Bureau("S1", "S1", "synthese"),
               Bureau("C6", "Vrai", "secteur")]
    for b in bureaux:
        wiki.seed_object("WikiDB.Bureaux", BUREAU_CLASS, {"code": b.code, "name": b.name, "type": b.kind})
    apply(wiki, target_state(bureaux))
    wiki.put_page(cleanup.PageRef(("Mesures", "A", "Secteur"), "M-9001"), "test")
    wiki.put_page(cleanup.PageRef(("Mesures", "C6", "Secteur"), "M-0001"), "real")
    # test-agent-real-finances-gouv-fr: a ProConnect user whose page happens to start like a test user's.
    for user in ("XWiki.test-agent-a", "XWiki.jean-dupont", "XWiki.test-agent-real-finances-gouv-fr"):
        wiki.seed_object(user, "XWiki.XWikiUsers", {"active": "1"})
        wiki.seed_object("XWiki.GroupeDirection", GROUPS, {"member": user})
    wiki.seed_object("XWiki.GroupeA", GROUPS, {"member": "XWiki.test-agent-a"})

    memberships, registry, pages = cleanup.plan(wiki)
    cleanup.apply(wiki, memberships, registry, pages)

    assert wiki.members("XWiki.GroupeDirection") == {"XWiki.jean-dupont", "XWiki.test-agent-real-finances-gouv-fr"}
    assert [o["code"] for o in wiki.objs("WikiDB.Bureaux", BUREAU_CLASS)] == ["C6"]
    left = set(wiki.pages)
    assert not {p for p in left if ".A." in p or ".B." in p or ".S1." in p}
    assert "XWiki.test-agent-a" not in left
    assert {"XWiki.GroupeA", "XWiki.GroupeS1"}.isdisjoint(left)
    assert {"Mesures.C6.Secteur.M-0001", "XWiki.GroupeC6", "XWiki.jean-dupont", "Mesures.WebHome",
            "XWiki.test-agent-real-finances-gouv-fr"} <= left


def test_a_refused_page_does_not_stop_the_others():
    wiki = FakeXWiki()
    for name in ("GroupeA", "GroupeB"):
        wiki.seed_object(f"XWiki.{name}", GROUPS, {"member": ""})
    delete = wiki.delete_page

    def locked(page):
        if page.name == "GroupeA":
            raise cleanup.XWikiError("DELETE .../GroupeA: 412")
        delete(page)

    wiki.delete_page = locked
    refused = cleanup.apply(wiki, *cleanup.plan(wiki, codes=("A", "B")))
    assert [str(page) for page, _ in refused] == ["XWiki.GroupeA"]
    assert "XWiki.GroupeB" not in wiki.pages
