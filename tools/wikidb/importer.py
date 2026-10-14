"""Bulk import of existing measure lists into skeleton sheets (U9; R18, F4).

Rows are validated before anything is written. The source key makes re-runs safe: an existing sheet only gets its
empty fields filled, never a field a champion already wrote. Dry run is the default.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path

from .client import PageRef, XWikiClient
from .measures import FIELDS, MESURE_CLASS, PERIMETERS, identifier, identifier_number, measure_page
from .provision import Bureau

# Input column -> class property. `bureau`, `perimetre` and `intitule` are required.
COLUMNS = {
    "cle_source": "cleSource",
    "date_creation": "dateCreation",
    "vecteur_juridique": "vecteurJuridique",
    "raison_etre": "raisonEtre",
    "modalites_modification": "modalitesModification",
    "documentation_interne": "documentationInterne",
    "documentation_externe": "documentationExterne",
}
REQUIRED = ("bureau", "perimetre", "intitule", "cle_source")


class ImportRejected(ValueError):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass
class Row:
    line: int
    bureau: str
    perimeter: str
    title: str
    values: dict[str, str]          # class property -> value (non-empty only)


@dataclass
class Plan:
    create: list[tuple[PageRef, Row]] = field(default_factory=list)
    fill: list[tuple[PageRef, int, dict[str, str]]] = field(default_factory=list)   # page, object number, values
    unchanged: list[PageRef] = field(default_factory=list)

    def describe(self) -> list[str]:
        out = [f"create {p} « {r.title} » (line {r.line})" for p, r in self.create]
        out += [f"fill {p}: {', '.join(sorted(v))}" for p, _, v in self.fill]
        out += [f"unchanged {p}" for p in self.unchanged]
        return out


def _normalize(name) -> str:
    return str(name or "").strip().lower().replace(" ", "_").replace("'", "_").replace("é", "e").replace("è", "e")


def read_rows(path: Path) -> list[dict[str, str]]:
    """Read a CSV or XLSX file into dicts keyed by normalized header names."""
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        from openpyxl import load_workbook
        sheet = load_workbook(path, read_only=False, data_only=True).active
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return []
        headers = [_normalize(h) for h in rows[0]]
        result = []
        for values in rows[1:]:
            result.append({h: ("" if v is None else str(v.date() if hasattr(v, "date") else v)).strip()
                           for h, v in zip(headers, values) if h})
        return result
    text = path.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(io.StringIO(text), delimiter=";" if text.count(";") > text.count(",") else ",")
    return [{_normalize(k): (v or "").strip() for k, v in row.items() if k} for row in reader]


def validate(raw_rows: list[dict[str, str]], bureaux: list[Bureau]) -> list[Row]:
    problems: list[str] = []
    if raw_rows and (missing := [c for c in REQUIRED if c not in raw_rows[0]]):
        raise ImportRejected([f"missing column(s): {', '.join(missing)}"])
    known = {b.code for b in bureaux}
    keys: dict[str, int] = {}
    rows = []
    for line, raw in enumerate(raw_rows, start=2):
        if not any(raw.values()):
            continue
        bureau, perimeter, title = raw.get("bureau", ""), raw.get("perimetre", "").lower(), raw.get("intitule", "")
        key = raw.get("cle_source", "")
        if bureau not in known:
            problems.append(f"line {line}: unknown bureau code {bureau!r}")
        if perimeter not in PERIMETERS:
            problems.append(f"line {line}: perimeter must be 'secteur' or 'synthese', got {perimeter!r}")
        if not title:
            problems.append(f"line {line}: empty title")
        if not key:
            problems.append(f"line {line}: empty source key")
        elif key in keys:
            problems.append(f"line {line}: source key {key!r} already used on line {keys[key]}")
        keys[key] = line
        values = {prop: raw[col] for col, prop in COLUMNS.items() if raw.get(col)}
        rows.append(Row(line, bureau, perimeter, title, values))
    if not rows:
        problems.append("the file has no rows")
    if problems:
        raise ImportRejected(problems)
    return rows


def plan(client: XWikiClient, rows: list[Row]) -> Plan:
    existing: dict[str, tuple[PageRef, int, dict[str, str]]] = {}
    highest = 0
    for ref in client.list_class_pages(MESURE_CLASS):
        page = PageRef.parse(ref)
        highest = max(highest, identifier_number(page.name) or 0)
        for obj in client.list_objects(page, MESURE_CLASS):
            if obj.properties.get("cleSource"):
                existing[obj.properties["cleSource"]] = (page, obj.number, obj.properties)

    result = Plan()
    for row in rows:
        if row.values["cleSource"] in existing:
            page, number, current = existing[row.values["cleSource"]]
            missing = {k: v for k, v in row.values.items() if not str(current.get(k, "")).strip()}
            if missing:
                result.fill.append((page, number, missing))
            else:
                result.unchanged.append(page)
            continue
        highest += 1
        result.create.append((measure_page(row.bureau, row.perimeter, identifier(highest)), row))
    return result


def execute(client: XWikiClient, the_plan: Plan) -> None:
    for page, row in the_plan.create:
        if client.page_exists(page):
            raise RuntimeError(f"{page} appeared during the import; re-run to allocate a new identifier")
        client.put_page(page, row.title)
        client.add_object(page, MESURE_CLASS, {f: row.values.get(f, "") for f in FIELDS})
    for page, number, values in the_plan.fill:
        client.update_object(page, MESURE_CLASS, number, values)
