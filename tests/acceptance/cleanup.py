"""Remove what the acceptance suite leaves on a wiki: the test users, their group memberships, and bureaux A, B, S1
with their registry entries, groups and spaces. For a wiki that will hold real data (Nubonyxia); dev wikis keep them.

Run, with the same settings as `wikidb provision` (WIKIDB_URL, WIKIDB_ROBOT_PASSWORD):
  python tests/acceptance/cleanup.py           # lists what it would remove, changes nothing
  python tests/acceptance/cleanup.py --apply   # removes it; pages go to the recycle bin
Then run `wikidb provision`, which takes GroupeS1 out of GroupeSynthese.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from wikidb.client import PageRef, XWikiClient  # noqa: E402
from wikidb.naming import bureau_group, group_reference  # noqa: E402
from wikidb.provision import BUREAU_CLASS, GROUPS_CLASS, REGISTRY_PAGE  # noqa: E402

BUREAUX = ("A", "B", "S1")
TEST_USER_PREFIX = "XWiki.test-"  # every user of conftest.USERS
USERS_CLASS = "XWiki.XWikiUsers"
# Spaces provision creates per bureau, each followed by the bureau code.
BUREAU_ROOTS = (("Mesures",), ("Bureaux",), ("Procedures",), ("Annuaire", "Bureaux"))


def plan(client, codes=BUREAUX):
    """Return (memberships, registry entries, pages) to remove, without changing anything."""
    groups = {group_reference(bureau_group(c)) for c in codes}
    memberships = []
    for ref in client.list_class_pages(GROUPS_CLASS):
        if ref in groups:
            continue  # the whole group page goes
        page = PageRef.parse(ref)
        memberships += [(page, o.number, o.properties["member"]) for o in client.list_objects(page, GROUPS_CLASS)
                        if o.properties.get("member", "").startswith(TEST_USER_PREFIX)]
    registry = [o for o in client.list_objects(REGISTRY_PAGE, BUREAU_CLASS) if o.properties.get("code", "").strip() in codes]
    roots = {root + (c,) for root in BUREAU_ROOTS for c in codes}
    spaces = [s for s in client.list_spaces() if any(s[:len(r)] == r for r in roots)]
    pages = [PageRef(s, n) for s in spaces for n in client.list_pages(s)]
    # The REST listing leaves out hidden pages; provision's only one there holds the space's rights.
    pages += [p for p in (PageRef(s, "WebPreferences") for s in spaces) if client.page_exists(p)]
    pages += [PageRef.parse(r) for r in client.list_class_pages(USERS_CLASS) if r.startswith(TEST_USER_PREFIX)]
    pages += [PageRef.parse(g) for g in sorted(groups) if client.page_exists(PageRef.parse(g))]
    return memberships, registry, pages


def apply(client, memberships, registry, pages):
    for page, number, _ in memberships:
        client.delete_object(page, GROUPS_CLASS, number)
    for obj in registry:
        client.delete_object(REGISTRY_PAGE, BUREAU_CLASS, obj.number)
    for page in pages:
        client.delete_page(page)


def main(argv):
    client = XWikiClient.from_settings()
    memberships, registry, pages = plan(client)
    for page, _, member in memberships:
        print(f"membership {member} in {page}")
    for obj in registry:
        print(f"registry entry {obj.properties.get('code')}")
    for page in pages:
        print(f"page {page}")
    if "--apply" not in argv:
        print(f"dry run: {len(memberships) + len(registry) + len(pages)} items; rerun with --apply to remove them")
        return 0
    apply(client, memberships, registry, pages)
    print("removed; now run wikidb provision")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
