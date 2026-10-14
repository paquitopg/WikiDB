"""Bureau registry -> groups, spaces and rights (U5; KTD6, KTD7, KTD12).

The registry is the list of WikiDB.Code.BureauClass objects on WikiDB.Bureaux. `target_state` turns it into the
wanted groups, space home pages and rights; `apply` makes the wiki match, idempotently. Spaces of bureaux missing from
the registry are reported, never deleted.
"""

from __future__ import annotations

from dataclasses import dataclass

from .client import PageRef, XWikiClient
from .naming import GROUP_DIRECTION, GROUP_SYNTHESE, bureau_group, group_reference

REGISTRY_PAGE = PageRef(("WikiDB",), "Bureaux")
BUREAU_CLASS = "WikiDB.Code.BureauClass"
GROUPS_CLASS = "XWiki.XWikiGroups"
GLOBAL_RIGHTS_CLASS = "XWiki.XWikiGlobalRights"
PREFERENCES_CLASS = "XWiki.XWikiPreferences"
WIKI_PREFERENCES = PageRef(("XWiki",), "XWikiPreferences")
ADMINS = "XWiki.XWikiAdminGroup"
ALL_USERS = "XWiki.XWikiAllGroup"

SECTEUR = "secteur"
SYNTHESE = "synthese"


@dataclass(frozen=True)
class Bureau:
    code: str
    name: str
    kind: str  # SECTEUR or SYNTHESE

    def __post_init__(self):
        if self.kind not in (SECTEUR, SYNTHESE):
            raise ValueError(f"bureau {self.code}: unknown type {self.kind!r}")
        if not self.code.isalnum():
            raise ValueError(f"bureau code {self.code!r} must be alphanumeric")


@dataclass(frozen=True)
class Rule:
    """One XWiki.XWikiGlobalRights object: allow `levels` to `groups`."""
    groups: tuple[str, ...]
    levels: tuple[str, ...]

    def properties(self) -> dict[str, str]:
        return {"groups": ",".join(self.groups), "users": "", "levels": ",".join(self.levels), "allow": "1"}

    @classmethod
    def from_properties(cls, props: dict[str, str]) -> "Rule | None":
        if str(props.get("allow", "1")) not in ("1", "true") or props.get("users"):
            return None
        split = lambda v: tuple(sorted(x.strip() for x in (v or "").split(",") if x.strip()))
        return cls(split(props.get("groups")), split(props.get("levels")))

    def normalized(self) -> "Rule":
        return Rule(tuple(sorted(self.groups)), tuple(sorted(self.levels)))


@dataclass(frozen=True)
class Space:
    spaces: tuple[str, ...]
    title: str
    rules: tuple[Rule, ...]

    @property
    def home(self) -> PageRef:
        return PageRef(self.spaces, "WebHome")

    @property
    def preferences(self) -> PageRef:
        return PageRef(self.spaces, "WebPreferences")


@dataclass
class TargetState:
    groups: list[str]                      # group page names that must exist
    synthese_members: list[str]            # members of GroupeSynthese (group references)
    spaces: list[Space]
    wiki_rules: list[Rule]                 # wiki-level rules that must exist (others are left alone)
    wiki_preferences: dict[str, str]


def _g(name: str) -> str:
    return group_reference(name)


def target_state(bureaux: list[Bureau]) -> TargetState:
    codes = [b.code for b in bureaux]
    if len(set(codes)) != len(codes):
        raise ValueError("duplicate bureau codes in the registry")

    direction, synthese = _g(GROUP_DIRECTION), _g(GROUP_SYNTHESE)
    admins_only_edit = (Rule((ADMINS,), ("edit", "delete")),)

    spaces = [
        # Application homes and code: readable by all agents, editable by administrators only (KTD12).
        Space(("Mesures",), "Fiches mesures", admins_only_edit),
        Space(("Procedures",), "Fiches procédures", admins_only_edit),
        Space(("Annuaire",), "Qui fait quoi", admins_only_edit),
        Space(("Annuaire", "Bureaux"), "Bureaux", admins_only_edit),
        Space(("Annuaire", "Externes"), "Émetteurs externes", admins_only_edit),
        Space(("Glossaire",), "Glossaire budgétaire", (Rule((direction,), ("edit", "delete")),)),
        Space(("Glossaire", "Code"), "Glossaire - code", admins_only_edit),
        Space(("WikiDB",), "Administration du wiki", (Rule((ADMINS,), ("view", "edit", "delete")),)),
        # Group pages and every other XWiki-space page: administrators only; user profiles keep their page rights.
        Space(("XWiki",), "XWiki", admins_only_edit),
    ]
    for b in sorted(bureaux, key=lambda b: b.code):
        own = _g(bureau_group(b.code))
        spaces += [
            Space(("Mesures", b.code), f"Mesures - {b.name}", admins_only_edit),
            Space(("Mesures", b.code, "Secteur"), f"Mesures sectorielles - {b.name}",
                  (Rule(tuple(sorted({own, synthese})), ("view",)), Rule((own,), ("edit", "delete")))),
            Space(("Mesures", b.code, "Synthese"), f"Mesures de synthèse - {b.name}",
                  (Rule((own,), ("edit", "delete")),)),
            Space(("Bureaux", b.code), f"Espace privé - {b.name}",
                  (Rule((own,), ("view", "edit", "delete")),)),
            Space(("Procedures", b.code), f"Procédures - {b.name}", (Rule((own,), ("edit", "delete")),)),
            Space(("Annuaire", "Bureaux", b.code), b.name, (Rule((own,), ("edit", "delete")),)),
        ]

    wiki_rules = [
        # Only agents in the HR listing read and edit (R6, R10, R17); everyone else is implicitly denied.
        Rule((direction,), ("view", "edit", "comment")),
        # Script and register are granted to administrators only, which denies them to everyone else (KTD12).
        Rule((ADMINS,), ("script", "register")),
    ]
    return TargetState(
        groups=[GROUP_DIRECTION, GROUP_SYNTHESE] + [bureau_group(c) for c in sorted(codes)],
        synthese_members=sorted(_g(bureau_group(b.code)) for b in bureaux if b.kind == SYNTHESE),
        spaces=spaces,
        wiki_rules=wiki_rules,
        wiki_preferences={"authenticate_view": "1", "default_language": "fr", "multilingual": "0",
                          "languages": "fr"},
    )


def read_registry(client: XWikiClient) -> list[Bureau]:
    return [Bureau(o.properties["code"].strip(), o.properties.get("name", "").strip(),
                   o.properties.get("type", "").strip())
            for o in client.list_objects(REGISTRY_PAGE, BUREAU_CLASS)]


@dataclass
class Report:
    changes: list[str]
    orphans: list[str]


def _ensure_group(client: XWikiClient, name: str, changes: list[str]) -> PageRef:
    page = PageRef(("XWiki",), name)
    if not client.page_exists(page):
        client.put_page(page, name, hidden=True)
        changes.append(f"created group page {page}")
    if not client.list_objects(page, GROUPS_CLASS):
        # An empty member object makes XWiki treat the page as a group.
        client.add_object(page, GROUPS_CLASS, {"member": ""})
        changes.append(f"initialized group {page}")
    return page


def set_group_members(client: XWikiClient, page: PageRef, wanted: set[str], changes: list[str]) -> None:
    """Make the non-empty `member` values of `page` equal `wanted`."""
    present: dict[str, list[int]] = {}
    for obj in client.list_objects(page, GROUPS_CLASS):
        member = obj.properties.get("member", "").strip()
        if member:
            present.setdefault(member, []).append(obj.number)
    for member, numbers in sorted(present.items()):
        extra = numbers if member not in wanted else numbers[1:]
        for number in extra:
            client.delete_object(page, GROUPS_CLASS, number)
            changes.append(f"{page}: removed {member}")
    for member in sorted(wanted - present.keys()):
        client.add_object(page, GROUPS_CLASS, {"member": member})
        changes.append(f"{page}: added {member}")


def _set_space_rules(client: XWikiClient, space: Space, changes: list[str]) -> None:
    wanted = {r.normalized() for r in space.rules}
    objects = client.list_objects(space.preferences, GLOBAL_RIGHTS_CLASS)
    present = {Rule.from_properties(o.properties) for o in objects}
    if present == wanted and len(objects) == len(wanted):
        return
    if not client.page_exists(space.preferences):
        client.put_page(space.preferences, "WebPreferences", hidden=True)
    for obj in objects:
        client.delete_object(space.preferences, GLOBAL_RIGHTS_CLASS, obj.number)
    for rule in sorted(wanted, key=lambda r: (r.groups, r.levels)):
        client.add_object(space.preferences, GLOBAL_RIGHTS_CLASS, rule.properties())
    changes.append(f"{'.'.join(space.spaces)}: rights set to "
                   + "; ".join(f"{','.join(r.levels)} -> {','.join(r.groups)}" for r in sorted(wanted, key=str)))


def apply(client: XWikiClient, state: TargetState, existing_bureau_spaces: list[str] | None = None) -> Report:
    changes: list[str] = []

    for name in state.groups:
        _ensure_group(client, name, changes)
    set_group_members(client, PageRef(("XWiki",), GROUP_SYNTHESE), set(state.synthese_members), changes)

    for space in state.spaces:
        if not client.page_exists(space.home):
            client.put_page(space.home, space.title)
            changes.append(f"created space {'.'.join(space.spaces)}")
        _set_space_rules(client, space, changes)

    # Every registered user is in XWikiAllGroup, including ProConnect users absent from the HR listing. The Standard
    # flavor allows it edit (which implies view) at wiki level; remove any such grant so GroupeDirection is the only
    # way in (R6, R17).
    for obj in client.list_objects(WIKI_PREFERENCES, GLOBAL_RIGHTS_CLASS):
        rule = Rule.from_properties(obj.properties)
        if rule and ALL_USERS in rule.groups:
            client.delete_object(WIKI_PREFERENCES, GLOBAL_RIGHTS_CLASS, obj.number)
            changes.append(f"wiki: removed {','.join(rule.levels)} granted to {ALL_USERS}")

    present_rules = {Rule.from_properties(o.properties)
                     for o in client.list_objects(WIKI_PREFERENCES, GLOBAL_RIGHTS_CLASS)}
    for rule in state.wiki_rules:
        if rule.normalized() not in present_rules:
            client.add_object(WIKI_PREFERENCES, GLOBAL_RIGHTS_CLASS, rule.properties())
            changes.append(f"wiki: allowed {','.join(rule.levels)} to {','.join(rule.groups)}")

    prefs = client.list_objects(WIKI_PREFERENCES, PREFERENCES_CLASS)
    if prefs:
        current = prefs[0].properties
        diff = {k: v for k, v in state.wiki_preferences.items() if str(current.get(k, "")) != v}
        if diff:
            client.update_object(WIKI_PREFERENCES, PREFERENCES_CLASS, prefs[0].number, diff)
            changes.append(f"wiki preferences: {diff}")
    else:
        changes.append("wiki preferences object missing: is the flavor installed?")

    known = {s.spaces[1] for s in state.spaces if s.spaces[0] == "Mesures" and len(s.spaces) > 1}
    orphans = sorted(set(existing_bureau_spaces or []) - known)
    return Report(changes, orphans)
