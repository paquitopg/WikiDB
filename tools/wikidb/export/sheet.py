"""The measure sheet as the export writers see it, built from the ExportData JSON (KTD18)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .html import Block, Paragraph, absolute_url, parse

# Fields shown in the identification table; the others are text sections.
IDENTIFICATION = ("dateCreation", "vecteurJuridique", "cleSource")
SECTIONS = ("raisonEtre", "modalitesModification", "documentationInterne", "documentationExterne")
PROVENANCE_COLUMNS = (("donnee", "Donnée"), ("emetteur", "Émetteur"), ("frequence", "Fréquence"),
                      ("format", "Forme"), ("contact", "Contact"))
_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass
class Field:
    name: str
    label: str
    blocks: list[Block]

    @property
    def text(self) -> str:
        parts = []
        for b in self.blocks:
            parts.append(b.text if isinstance(b, Paragraph) else " ; ".join(" | ".join(r) for r in b.rows))
        return " ".join(p.strip() for p in parts if p.strip())


@dataclass
class Provenance:
    values: dict[str, str]
    sender_url: str | None


@dataclass
class Sheet:
    identifier: str
    title: str
    url: str
    bureau: str
    perimeter: str
    fields: dict[str, Field]
    provenances: list[Provenance] = field(default_factory=list)
    last_modified: str = ""

    def file_name(self, extension: str) -> str:
        name = _FORBIDDEN.sub("-", f"{self.identifier} - {self.title}").strip(" .")
        return f"{name[:150]}.{extension}"


def from_export_data(data: dict, public_origin: str, internal_origins: tuple[str, ...] = ()) -> Sheet:
    def text(html: str) -> str:
        return " ".join(b.text for b in parse(html, public_origin, internal_origins) if isinstance(b, Paragraph)).strip()

    fields = {f["name"]: Field(f["name"], f["label"], parse(f["html"], public_origin, internal_origins))
              for f in data["fields"]}
    provenances = []
    for p in data.get("provenances", []):
        values = {key: p.get(key, "") for key, _ in PROVENANCE_COLUMNS}
        values["frequence"] = text(values["frequence"])
        url = p.get("emetteurUrl") or None
        provenances.append(Provenance(values, absolute_url(url, public_origin, internal_origins) if url else None))
    bureau = data["bureau"]
    last = data.get("lastModified", {})
    return Sheet(
        identifier=data["identifier"],
        title=data["title"],
        url=absolute_url(data["url"], public_origin, internal_origins),
        bureau=f"{bureau['code']} – {bureau['name']}" if bureau.get("name") else bureau["code"],
        perimeter=data["perimetre"]["label"],
        fields=fields,
        provenances=provenances,
        last_modified=f"{last.get('date', '')} par {last.get('author', '')}".strip(),
    )

