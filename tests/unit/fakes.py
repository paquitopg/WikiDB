"""In-memory stand-in for the XWiki REST layer used by tools/wikidb.

It stores pages and objects the way the wiki would, so tests assert on resulting wiki state rather than on calls.
"""

from wikidb.client import PageRef, XObject


class FakeXWiki:
    def __init__(self):
        self.pages: dict[str, dict] = {}
        self.objects: dict[str, dict[str, dict[int, dict[str, str]]]] = {}
        self.writes = 0

    # -- helpers for tests -----------------------------------------------------------------------------------------

    def objs(self, ref: str, class_name: str) -> list[dict[str, str]]:
        return [props for _, props in sorted(self.objects.get(ref, {}).get(class_name, {}).items())]

    def members(self, ref: str) -> set[str]:
        return {o["member"] for o in self.objs(ref, "XWiki.XWikiGroups") if o.get("member")}

    def seed_object(self, ref: str, class_name: str, props: dict[str, str]) -> None:
        self.pages.setdefault(ref, {"title": ref, "content": ""})
        self.add_object(PageRef.parse(ref), class_name, props)
        self.writes -= 1

    # -- client interface ------------------------------------------------------------------------------------------

    def page_exists(self, page: PageRef) -> bool:
        return str(page) in self.pages

    def get_page(self, page: PageRef):
        return self.pages.get(str(page))

    def put_page(self, page: PageRef, title: str, content: str = "", hidden: bool = False) -> None:
        self.writes += 1
        self.pages[str(page)] = {"title": title, "content": content, "hidden": hidden}

    def delete_page(self, page: PageRef) -> None:
        self.writes += 1
        self.pages.pop(str(page), None)
        self.objects.pop(str(page), None)

    def list_spaces(self):
        spaces = set()
        for ref in self.pages:
            parts = PageRef.parse(ref).spaces
            for i in range(1, len(parts) + 1):
                spaces.add(parts[:i])
        return sorted(spaces)

    def list_pages(self, spaces):
        # Like the REST listing, hidden pages (WebPreferences, groups) are left out.
        return sorted(PageRef.parse(r).name for r, p in self.pages.items()
                      if PageRef.parse(r).spaces == tuple(spaces) and not p.get("hidden"))

    def list_class_pages(self, class_name: str) -> list[str]:
        return sorted(ref for ref, by_class in self.objects.items() if by_class.get(class_name))

    def list_objects(self, page: PageRef, class_name: str) -> list[XObject]:
        stored = self.objects.get(str(page), {}).get(class_name, {})
        return [XObject(class_name, n, dict(p)) for n, p in sorted(stored.items())]

    def add_object(self, page: PageRef, class_name: str, properties: dict[str, str]) -> None:
        if str(page) not in self.pages:
            raise AssertionError(f"object added to missing page {page}")
        self.writes += 1
        by_class = self.objects.setdefault(str(page), {}).setdefault(class_name, {})
        by_class[max(by_class, default=-1) + 1] = dict(properties)

    def update_object(self, page: PageRef, class_name: str, number: int, properties: dict[str, str]) -> None:
        self.writes += 1
        self.objects[str(page)][class_name][number].update(properties)

    def delete_object(self, page: PageRef, class_name: str, number: int) -> None:
        self.writes += 1
        del self.objects[str(page)][class_name][number]
