"""Minimal XWiki REST client for the operations tooling (KTD13).

Pages are addressed by a list of nested space names plus a page name.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

import requests

SECRETS_DIR = Path(os.environ.get("SECRETS_DIR", "/secrets/app"))


def setting(name: str, default: str | None = None) -> str:
    """Read a setting from the environment, otherwise from SECRETS_DIR/<name> (KTD11)."""
    value = os.environ.get(name)
    if value:
        return value
    try:
        return (SECRETS_DIR / name).read_text().rstrip("\r\n")
    except FileNotFoundError:
        if default is not None:
            return default
        raise KeyError(name) from None


@dataclass(frozen=True)
class PageRef:
    spaces: tuple[str, ...]
    name: str = "WebHome"

    @classmethod
    def parse(cls, reference: str) -> "PageRef":
        """Parse 'A.B.C' as spaces (A, B) and page C. Dots in names are not supported."""
        *spaces, name = reference.split(".")
        return cls(tuple(spaces), name)

    def __str__(self) -> str:
        return ".".join((*self.spaces, self.name))

    def path(self) -> str:
        spaces = "".join(f"/spaces/{quote(s, safe='')}" for s in self.spaces)
        return f"{spaces}/pages/{quote(self.name, safe='')}"


@dataclass
class XObject:
    class_name: str
    number: int
    properties: dict[str, str] = field(default_factory=dict)


class XWikiError(RuntimeError):
    pass


class XWikiClient:
    def __init__(self, base_url: str, user: str, password: str, wiki: str = "xwiki", session=None):
        self.base = f"{base_url.rstrip('/')}/rest/wikis/{wiki}"
        self.session = session or requests.Session()
        self.session.auth = (user, password)
        self.session.headers.update({"Accept": "application/json"})

    @classmethod
    def from_settings(cls) -> "XWikiClient":
        return cls(setting("WIKIDB_URL"), setting("WIKIDB_ROBOT_USER", "wikidb-robot"),
                   setting("WIKIDB_ROBOT_PASSWORD"))

    def _check(self, response, *ok):
        if response.status_code not in ok:
            raise XWikiError(f"{response.request.method} {response.url}: {response.status_code} {response.text[:300]}")
        return response

    # -- pages -----------------------------------------------------------------------------------------------------

    def page_exists(self, page: PageRef) -> bool:
        r = self.session.get(self.base + page.path())
        return self._check(r, 200, 404).status_code == 200

    def get_page(self, page: PageRef) -> dict | None:
        r = self._check(self.session.get(self.base + page.path()), 200, 404)
        return r.json() if r.status_code == 200 else None

    def put_page(self, page: PageRef, title: str, content: str = "", hidden: bool = False) -> None:
        body = {"title": title, "content": content, "hidden": hidden}
        self._check(self.session.put(self.base + page.path(), json=body), 200, 201, 202, 304)

    def delete_page(self, page: PageRef) -> None:
        """Move a page to the recycle bin; a missing page is not an error."""
        self._check(self.session.delete(self.base + page.path()), 200, 204, 404)

    def list_spaces(self) -> list[tuple[str, ...]]:
        """Every space of the wiki, as tuples of nested space names."""
        r = self._check(self.session.get(f"{self.base}/spaces"), 200)
        result = []
        for space in r.json().get("spaces", []):
            # ids look like "xwiki:Mesures.A.Secteur"; escaped dots are not used by this wiki.
            result.append(tuple(space["id"].split(":", 1)[1].split(".")))
        return result

    def list_pages(self, spaces: tuple[str, ...]) -> list[str]:
        """Names of the visible pages directly in a space (not in its nested spaces); hidden pages are left out."""
        path = "".join(f"/spaces/{quote(s, safe='')}" for s in spaces)
        r = self._check(self.session.get(f"{self.base}{path}/pages"), 200, 404)
        return [] if r.status_code == 404 else [p["name"] for p in r.json().get("pageSummaries", [])]

    def list_class_pages(self, class_name: str) -> list[str]:
        """References of every page holding an object of `class_name` (e.g. all user profiles)."""
        refs: set[str] = set()
        start, size = 0, 1000                     # XWiki caps a REST page at 1000 results
        while True:
            r = self._check(self.session.get(f"{self.base}/classes/{class_name}/objects",
                                             params={"start": start, "number": size}), 200)
            summaries = r.json().get("objectSummaries", [])
            refs |= {f"{o['space']}.{o['pageName']}" for o in summaries}
            if len(summaries) < size:
                return sorted(refs)
            start += size

    # -- objects ---------------------------------------------------------------------------------------------------

    def list_objects(self, page: PageRef, class_name: str) -> list[XObject]:
        r = self._check(self.session.get(f"{self.base}{page.path()}/objects/{class_name}",
                                         params={"withPrettyNames": "false"}), 200, 404)
        if r.status_code == 404:
            return []
        objects = []
        for summary in r.json().get("objectSummaries", []):
            number = int(summary["number"])
            objects.append(XObject(class_name, number, self.get_object_properties(page, class_name, number)))
        return objects

    def get_object_properties(self, page: PageRef, class_name: str, number: int) -> dict[str, str]:
        r = self._check(self.session.get(f"{self.base}{page.path()}/objects/{class_name}/{number}"), 200)
        return {p["name"]: p.get("value") or "" for p in r.json().get("properties", [])}

    def add_object(self, page: PageRef, class_name: str, properties: dict[str, str]) -> None:
        # JSON bodies: form-encoded writes need XWiki's CSRF form token.
        body = {"className": class_name, "properties": [{"name": k, "value": v} for k, v in properties.items()]}
        self._check(self.session.post(f"{self.base}{page.path()}/objects", json=body), 200, 201)

    def update_object(self, page: PageRef, class_name: str, number: int, properties: dict[str, str]) -> None:
        body = {"className": class_name, "number": number,
                "properties": [{"name": k, "value": v} for k, v in properties.items()]}
        self._check(self.session.put(f"{self.base}{page.path()}/objects/{class_name}/{number}", json=body),
                    200, 202)

    def delete_object(self, page: PageRef, class_name: str, number: int) -> None:
        self._check(self.session.delete(f"{self.base}{page.path()}/objects/{class_name}/{number}"), 200, 204)
