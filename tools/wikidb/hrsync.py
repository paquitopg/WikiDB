"""HR listing -> GroupeDirection and bureau group membership (U8; R16, R17, KTD9, KTD14).

The listing is a CSV with two columns, `email` and `bureau`. A file that fails any check is rejected whole and
membership is left unchanged.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .client import PageRef, XWikiClient
from .naming import GROUP_DIRECTION, bureau_group, user_name, user_reference
from .provision import Bureau, set_group_members

REQUIRED_COLUMNS = ("email", "bureau")
EMAIL = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[a-z]{2,}$", re.IGNORECASE)
USERS_CLASS = "XWiki.XWikiUsers"
# Accounts that sign in locally and never appear in the listing.
LOCAL_ACCOUNTS = {"XWiki.wikidb-robot", "XWiki.Admin", "XWiki.superadmin"}


class ListingRejected(ValueError):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass
class Listing:
    by_bureau: dict[str, set[str]]           # bureau code -> user references
    emails: dict[str, str]                   # user reference -> email


def parse_listing(content: bytes, last_modified: datetime, now: datetime, bureaux: list[Bureau],
                  max_age: timedelta) -> Listing:
    problems: list[str] = []
    age = now - last_modified
    if age > max_age:
        raise ListingRejected([f"newest listing is {age} old, more than the allowed {max_age}"])

    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text), delimiter=";" if text.count(";") > text.count(",") else ",")
    columns = [c.strip().lower() for c in (reader.fieldnames or [])]
    missing = [c for c in REQUIRED_COLUMNS if c not in columns]
    if missing:
        raise ListingRejected([f"missing column(s): {', '.join(missing)}"])

    known = {b.code for b in bureaux}
    seen: dict[str, tuple[str, int]] = {}         # email -> (bureau, line)
    references: dict[str, str] = {}               # user name -> email
    by_bureau: dict[str, set[str]] = {code: set() for code in known}
    emails: dict[str, str] = {}
    rows = 0
    for line, raw in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        email, bureau = row.get("email", "").lower(), row.get("bureau", "")
        if not email and not bureau:
            continue
        rows += 1
        if not EMAIL.match(email):
            problems.append(f"line {line}: malformed email {email!r}")
            continue
        if bureau not in known:
            problems.append(f"line {line}: unknown bureau code {bureau!r}")
            continue
        if email in seen:
            problems.append(f"line {line}: {email} already listed on line {seen[email][1]} "
                            f"(bureaux {seen[email][0]} and {bureau})")
            continue
        seen[email] = (bureau, line)
        name = user_name(email)
        if name in references:
            problems.append(f"line {line}: {email} and {references[name]} map to the same wiki user {name}")
            continue
        references[name] = email
        by_bureau[bureau].add(user_reference(email))
        emails[user_reference(email)] = email
    if rows == 0:
        problems.append("the listing has no rows")
    if problems:
        raise ListingRejected(problems)
    return Listing(by_bureau, emails)


@dataclass
class SyncSummary:
    changes: list[str] = field(default_factory=list)
    pending_first_login: list[tuple[str, str]] = field(default_factory=list)   # (email, first seen)
    users_without_bureau: list[str] = field(default_factory=list)
    state: dict[str, str] = field(default_factory=dict)                       # email -> first seen (ISO date)

    def render(self, finished: datetime) -> str:
        lines = [f"Synchronisation RH réussie le {finished.isoformat(timespec='minutes')}", "",
                 f"== Modifications ({len(self.changes)}) =="]
        lines += [f"* {c}" for c in self.changes] or ["Aucune."]
        lines += ["", f"== Agents listés sans connexion depuis 14 jours ({len(self.pending_first_login)}) =="]
        lines += [f"* {e} (listé depuis le {d})" for e, d in self.pending_first_login] or ["Aucun."]
        lines += ["", f"== Utilisateurs connectés sans bureau ({len(self.users_without_bureau)}) =="]
        lines += [f"* {u}" for u in self.users_without_bureau] or ["Aucun."]
        return "\n".join(lines)


def sync(client: XWikiClient, listing: Listing, previous_state: dict[str, str], today: datetime,
         pending_after: timedelta = timedelta(days=14)) -> SyncSummary:
    summary = SyncSummary()
    everyone = set().union(*listing.by_bureau.values()) if listing.by_bureau else set()
    set_group_members(client, PageRef(("XWiki",), GROUP_DIRECTION), everyone, summary.changes)
    for code, members in sorted(listing.by_bureau.items()):
        set_group_members(client, PageRef(("XWiki",), bureau_group(code)), members, summary.changes)

    existing_users = set(client.list_class_pages(USERS_CLASS))
    for reference, email in sorted(listing.emails.items(), key=lambda kv: kv[1]):
        if reference in existing_users:
            continue
        first_seen = previous_state.get(email, today.date().isoformat())
        summary.state[email] = first_seen
        if today - datetime.fromisoformat(first_seen).replace(tzinfo=today.tzinfo) >= pending_after:
            summary.pending_first_login.append((email, first_seen))
    summary.users_without_bureau = sorted(existing_users - everyone - LOCAL_ACCOUNTS)
    return summary
