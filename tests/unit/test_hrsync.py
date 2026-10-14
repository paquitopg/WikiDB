from datetime import datetime, timedelta, timezone

import pytest

from fakes import FakeXWiki
from wikidb.hrsync import ListingRejected, parse_listing, sync
from wikidb.provision import Bureau, apply, target_state

A = Bureau("A", "Bureau A", "secteur")
B = Bureau("B", "Bureau B", "secteur")
S1 = Bureau("S1", "Synthèse 1", "synthese")
BUREAUX = [A, B, S1]
NOW = datetime(2026, 10, 14, 6, 0, tzinfo=timezone.utc)
FRESH = NOW - timedelta(hours=2)
MAX_AGE = timedelta(hours=72)


def listing(text: str, last_modified=FRESH):
    return parse_listing(text.encode(), last_modified, NOW, BUREAUX, MAX_AGE)


def provisioned() -> FakeXWiki:
    wiki = FakeXWiki()
    wiki.seed_object("XWiki.XWikiPreferences", "XWiki.XWikiPreferences", {})
    apply(wiki, target_state(BUREAUX))
    return wiki


def login(wiki: FakeXWiki, email: str):
    from wikidb.naming import user_reference
    wiki.seed_object(user_reference(email), "XWiki.XWikiUsers", {"email": email})


def test_moving_an_agent_changes_only_their_bureau_groups():
    wiki = provisioned()
    sync(wiki, listing("email,bureau\nmarie.curie@finances.gouv.fr,A\npaul.dirac@finances.gouv.fr,A\n"), {}, NOW)
    summary = sync(wiki, listing("email,bureau\nmarie.curie@finances.gouv.fr,B\npaul.dirac@finances.gouv.fr,A\n"),
                   {}, NOW)
    assert wiki.members("XWiki.GroupeA") == {"XWiki.paul-dirac-finances-gouv-fr"}
    assert wiki.members("XWiki.GroupeB") == {"XWiki.marie-curie-finances-gouv-fr"}
    assert sorted(summary.changes) == ["XWiki.GroupeA: removed XWiki.marie-curie-finances-gouv-fr",
                                       "XWiki.GroupeB: added XWiki.marie-curie-finances-gouv-fr"]


def test_every_listed_agent_is_in_the_direction_group_and_unlisted_agents_leave_it():
    wiki = provisioned()
    sync(wiki, listing("email,bureau\na@finances.gouv.fr,A\nb@finances.gouv.fr,S1\n"), {}, NOW)
    assert wiki.members("XWiki.GroupeDirection") == {"XWiki.a-finances-gouv-fr", "XWiki.b-finances-gouv-fr"}
    sync(wiki, listing("email,bureau\nb@finances.gouv.fr,S1\n"), {}, NOW)
    assert wiki.members("XWiki.GroupeDirection") == {"XWiki.b-finances-gouv-fr"}
    assert wiki.members("XWiki.GroupeA") == set()


def test_unknown_bureau_code_rejects_the_whole_file():
    with pytest.raises(ListingRejected, match="unknown bureau code 'Z'"):
        listing("email,bureau\na@finances.gouv.fr,A\nb@finances.gouv.fr,Z\n")


@pytest.mark.parametrize("text, message", [
    ("email\na@finances.gouv.fr\n", "missing column"),
    ("email,bureau\n", "no rows"),
    ("email,bureau\nnot-an-email,A\n", "malformed email"),
])
def test_malformed_listings_are_rejected(text, message):
    with pytest.raises(ListingRejected, match=message):
        listing(text)


def test_same_email_twice_is_rejected_and_names_both_bureaux():
    with pytest.raises(ListingRejected, match="bureaux A and B"):
        listing("email,bureau\na@finances.gouv.fr,A\nA@finances.gouv.fr,B\n")


def test_two_emails_mapping_to_the_same_wiki_user_are_rejected():
    with pytest.raises(ListingRejected, match="same wiki user"):
        listing("email,bureau\njean.dupont@finances.gouv.fr,A\njean-dupont@finances.gouv.fr,B\n")


def test_stale_listing_is_rejected():
    with pytest.raises(ListingRejected, match="more than the allowed"):
        listing("email,bureau\na@finances.gouv.fr,A\n", last_modified=NOW - timedelta(days=4))


def test_rejected_listing_leaves_membership_unchanged():
    wiki = provisioned()
    sync(wiki, listing("email,bureau\na@finances.gouv.fr,A\n"), {}, NOW)
    before = wiki.writes
    with pytest.raises(ListingRejected):
        listing("email,bureau\na@finances.gouv.fr,Z\n")
    assert wiki.writes == before
    assert wiki.members("XWiki.GroupeA") == {"XWiki.a-finances-gouv-fr"}


def test_uppercase_and_dots_map_to_the_name_the_authenticator_creates():
    result = listing("Email;Bureau\nMarie.Curie@Finances.Gouv.FR;A\n")
    assert result.by_bureau["A"] == {"XWiki.marie-curie-finances-gouv-fr"}


def test_summary_lists_agents_never_logged_in_after_14_days_and_users_without_bureau():
    wiki = provisioned()
    login(wiki, "a@finances.gouv.fr")
    login(wiki, "visiteur@autre.gouv.fr")
    text = "email,bureau\na@finances.gouv.fr,A\nb@finances.gouv.fr,B\n"
    first = sync(wiki, listing(text), {}, NOW)
    assert first.pending_first_login == []
    assert first.state == {"b@finances.gouv.fr": "2026-10-14"}
    later = sync(wiki, listing(text, last_modified=NOW + timedelta(days=15)), first.state, NOW + timedelta(days=15))
    assert later.pending_first_login == [("b@finances.gouv.fr", "2026-10-14")]
    assert later.users_without_bureau == ["XWiki.visiteur-autre-gouv-fr"]
