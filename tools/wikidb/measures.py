"""Measure sheet model shared by the importer and the wiki application (U6, U9; KTD6, KTD8).

Field names must match xwiki/app/src/main/resources/Mesures/Code/MesureClass.xml.
"""

from __future__ import annotations

import re

from .client import PageRef, XWikiClient

MESURE_CLASS = "Mesures.Code.MesureClass"
PROVENANCE_CLASS = "Mesures.Code.ProvenanceClass"
PERIMETERS = {"secteur": "Secteur", "synthese": "Synthese"}

# R1 fields, in display order. `cleSource` is the import idempotency key.
FIELDS = ("cleSource", "dateCreation", "vecteurJuridique", "raisonEtre", "modalitesModification",
          "documentationInterne", "documentationExterne")
REQUIRED_FOR_COMPLETE = FIELDS[1:]
# A provenance block counts once it names its data item and its sender.
PROVENANCE_REQUIRED = ("donnee", "emetteur")

_ID = re.compile(r"^M-(\d{4,})$")


def measure_page(bureau: str, perimeter: str, identifier: str) -> PageRef:
    """Where a sheet lives: its location is its perimeter (KTD6)."""
    return PageRef(("Mesures", bureau, PERIMETERS[perimeter]), identifier)


def identifier(number: int) -> str:
    return f"M-{number:04d}"


def identifier_number(page_name: str) -> int | None:
    match = _ID.match(page_name)
    return int(match.group(1)) if match else None


def is_complete(mesure: dict[str, str], provenances: list[dict[str, str]]) -> bool:
    """Completeness indicator (success criterion). Keep in step with #mesureComplete in Mesures.Code.MesureMacros."""
    def filled(props: dict[str, str], names) -> bool:
        return all(str(props.get(n) or "").strip() for n in names)
    return filled(mesure, REQUIRED_FOR_COMPLETE) and any(filled(p, PROVENANCE_REQUIRED) for p in provenances)


def completeness(client: XWikiClient) -> dict[tuple[str, str], tuple[int, int]]:
    """(bureau, perimeter) -> (complete sheets, sheets), over every sheet of the wiki."""
    counts: dict[tuple[str, str], tuple[int, int]] = {}
    for ref in client.list_class_pages(MESURE_CLASS):
        page = PageRef.parse(ref)
        if len(page.spaces) != 3 or page.spaces[0] != "Mesures":
            continue
        mesures = client.list_objects(page, MESURE_CLASS)
        provenances = [o.properties for o in client.list_objects(page, PROVENANCE_CLASS)]
        done = bool(mesures) and is_complete(mesures[0].properties, provenances)
        complete, total = counts.get(page.spaces[1:], (0, 0))
        counts[page.spaces[1:]] = (complete + done, total + 1)
    return counts
