"""HR listing -> GroupeDirection and bureau group membership (U8; R16, R17, KTD9, KTD14).

The listing is the Direction's directory: a CSV with an email column (`email` or `mail`) and a bureau column
(`bureau` or `affectation`) covering every agent of the Direction. Agents of bureaux outside the registry are
Direction agents in no pilot bureau (R17). A file that fails any check is rejected whole and membership is left
unchanged.
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

# Canonical column -> accepted header names (the directory export uses mail / affectation).
COLUMNS = {"email": ("email", "mail"), "bureau": ("bureau", "affectation")}
# Fraction of GroupeDirection a new listing may remove before the sync refuses it (check_shrink).
MAX_SHRINK = 0.3
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
    # Direction agents whose bureau is not in the registry: GroupeDirection only (R17).
    without_bureau: set[str] = field(default_factory=set)

    @property
    def outside_pilot(self) -> int:
        return len(self.without_bureau)

    @property
    def everyone(self) -> set[str]:
        return set().union(*self.by_bureau.values(), self.without_bureau)


def parse_listing(content: bytes, last_modified: datetime, now: datetime, bureaux: list[Bureau],
                  max_age: timedelta, min_rows: int = 1) -> Listing:
    problems: list[str] = []
    age = now - last_modified
    if age > max_age:
        raise ListingRejected([f"newest listing is {age} old, more than the allowed {max_age}"])

    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text), delimiter=";" if text.count(";") > text.count(",") else ",")
    columns = [c.strip().lower() for c in (reader.fieldnames or [])]
    header = {canonical: next((n for n in names if n in columns), None) for canonical, names in COLUMNS.items()}
    missing = [" or ".join(COLUMNS[c]) for c, name in header.items() if name is None]
    if missing:
        raise ListingRejected([f"missing column(s): {', '.join(missing)}"])

    known = {b.code.upper(): b.code for b in bureaux}
    seen: dict[str, tuple[str, int]] = {}         # email -> (bureau, line)
    references: dict[str, str] = {}               # user name -> email
    by_bureau: dict[str, set[str]] = {b.code: set() for b in bureaux}
    without_bureau: set[str] = set()
    emails: dict[str, str] = {}
    rows = 0
    for line, raw in enumerate(reader, start=2):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        email, bureau = row.get(header["email"], "").lower(), row.get(header["bureau"], "").upper()
        if not email and not bureau:
            continue
        rows += 1
        if not EMAIL.match(email):
            problems.append(f"line {line}: malformed email {email!r}")
            continue
        if not bureau:
            problems.append(f"line {line}: empty bureau for {email}")
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
        (by_bureau[known[bureau]] if bureau in known else without_bureau).add(user_reference(email))
        emails[user_reference(email)] = email
    if rows == 0:
        problems.append("the listing has no rows")
    elif rows < min_rows:
        problems.append(f"{rows} agents, fewer than the expected minimum of {min_rows}")
    if not problems:
        # A registry code nobody is listed under would silently empty that bureau's group.
        problems += [f"registered bureau {code} has no agent in the listing (check the registry code)"
                     for code, members in sorted(by_bureau.items()) if not members]
    if problems:
        raise ListingRejected(problems)
    return Listing(by_bureau, emails, without_bureau)


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


def check_shrink(listing: Listing, current_members: int, force: bool = False) -> None:
    """Refuse a listing that would remove more than MAX_SHRINK of GroupeDirection at once (a truncated export)."""
    listed = len(listing.everyone)
    if not force and current_members and listed < (1 - MAX_SHRINK) * current_members:
        raise ListingRejected([f"{listed} agents instead of {current_members} in GroupeDirection: more than "
                               f"{MAX_SHRINK:.0%} would lose access (re-run with --force if this is expected)"])


def sync(client: XWikiClient, listing: Listing, previous_state: dict[str, str], today: datetime,
         pending_after: timedelta = timedelta(days=14)) -> SyncSummary:
    summary = SyncSummary()
    everyone = listing.everyone
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
