from datetime import datetime, timedelta, timezone

import pytest

from fakes import FakeXWiki
from wikidb.hrsync import ListingRejected, check_shrink, parse_listing, sync
from wikidb.provision import Bureau, apply, target_state

A = Bureau("A", "Bureau A", "secteur")
B = Bureau("B", "Bureau B", "secteur")
S1 = Bureau("S1", "Synthèse 1", "synthese")
BUREAUX = [A, B, S1]
NOW = datetime(2026, 10, 14, 6, 0, tzinfo=timezone.utc)
FRESH = NOW - timedelta(hours=2)
MAX_AGE = timedelta(hours=72)


def listing(text: str, last_modified=FRESH, bureaux=None, min_rows=1):
    """Parse a listing against a registry; by default, only the bureaux the text names are registered."""
    if bureaux is None:
        named = {line.split(",")[-1].strip().upper() for line in text.splitlines()[1:]}
        bureaux = [b for b in BUREAUX if b.code in named]
    return parse_listing(text.encode(), last_modified, NOW, bureaux, MAX_AGE, min_rows=min_rows)


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
    sync(wiki, listing("email,bureau\nc@finances.gouv.fr,A\nb@finances.gouv.fr,S1\n"), {}, NOW)
    assert wiki.members("XWiki.GroupeDirection") == {"XWiki.c-finances-gouv-fr", "XWiki.b-finances-gouv-fr"}
    assert wiki.members("XWiki.GroupeA") == {"XWiki.c-finances-gouv-fr"}


def test_agent_of_a_bureau_outside_the_pilot_joins_only_the_direction_group():
    """R17, AE7: the directory lists the whole Direction; agents of unregistered bureaux get the common area only."""
    wiki = provisioned()
    result = listing("email,bureau\na@finances.gouv.fr,A\nhors.pilote@finances.gouv.fr,2BLF\n", bureaux=[A])
    summary = sync(wiki, result, {}, NOW)
    assert wiki.members("XWiki.GroupeDirection") == {"XWiki.a-finances-gouv-fr", "XWiki.hors-pilote-finances-gouv-fr"}
    for code in ("A", "B", "S1"):
        assert "XWiki.hors-pilote-finances-gouv-fr" not in wiki.members(f"XWiki.Groupe{code}")
    assert result.outside_pilot == 1
    assert "XWiki.hors-pilote-finances-gouv-fr" not in summary.users_without_bureau


def test_directory_columns_mail_and_affectation_are_accepted_in_any_case():
    result = listing("mail,affectation\nMarie.Curie@finances.gouv.fr,a\n", bureaux=[A])
    assert result.by_bureau["A"] == {"XWiki.marie-curie-finances-gouv-fr"}


def test_blank_bureau_rejects_the_whole_file():
    """A blank or emptied bureau column must fail visibly, never strip every bureau group (review #1)."""
    with pytest.raises(ListingRejected, match="line 3: empty bureau"):
        listing("email,bureau\na@finances.gouv.fr,A\nb@finances.gouv.fr,\n", bureaux=[A])
    with pytest.raises(ListingRejected, match="empty bureau"):
        listing("email,bureau\na@finances.gouv.fr,\nb@finances.gouv.fr,\n", bureaux=[A, B])


def test_registered_bureau_absent_from_the_listing_rejects_the_whole_file():
    """A registry code that matches nobody would silently empty that bureau's group."""
    with pytest.raises(ListingRejected, match="registered bureau S1 has no agent"):
        listing("email,bureau\na@finances.gouv.fr,A\n", bureaux=[A, S1])


def test_listing_shorter_than_the_minimum_is_rejected():
    with pytest.raises(ListingRejected, match="2 agents, fewer than the expected minimum of 50"):
        listing("email,bureau\na@finances.gouv.fr,A\nb@finances.gouv.fr,A\n", min_rows=50)


def test_listing_that_drops_a_third_of_the_direction_is_rejected_unless_forced():
    small = listing("email,bureau\n" + "".join(f"a{i}@finances.gouv.fr,A\n" for i in range(6)), bureaux=[A])
    with pytest.raises(ListingRejected, match="6 agents instead of 10"):
        check_shrink(small, current_members=10)
    check_shrink(small, current_members=10, force=True)
    check_shrink(small, current_members=8)


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
        listing("email,bureau\na@finances.gouv.fr,\n", bureaux=[A])
    assert wiki.writes == before
    assert wiki.members("XWiki.GroupeA") == {"XWiki.a-finances-gouv-fr"}


def test_uppercase_and_dots_map_to_the_name_the_authenticator_creates():
    result = listing("Email;Bureau\nMarie.Curie@Finances.Gouv.FR;A\n", bureaux=[A])
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
