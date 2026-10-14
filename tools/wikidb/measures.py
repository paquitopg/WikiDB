"""Measure sheet model shared by the importer and the wiki application (U6, U9; KTD6, KTD8).

Field names must match xwiki/app/src/main/resources/Mesures/Code/MesureClass.xml.
"""

from __future__ import annotations

import re

from .client import PageRef

MESURE_CLASS = "Mesures.Code.MesureClass"
PROVENANCE_CLASS = "Mesures.Code.ProvenanceClass"
PERIMETERS = {"secteur": "Secteur", "synthese": "Synthese"}

# R1 fields, in display order. `cleSource` is the import idempotency key.
FIELDS = ("cleSource", "dateCreation", "vecteurJuridique", "raisonEtre", "modalitesModification",
          "documentationInterne", "documentationExterne")
REQUIRED_FOR_COMPLETE = FIELDS[1:]

_ID = re.compile(r"^M-(\d{4,})$")


def measure_page(bureau: str, perimeter: str, identifier: str) -> PageRef:
    """Where a sheet lives: its location is its perimeter (KTD6)."""
    return PageRef(("Mesures", bureau, PERIMETERS[perimeter]), identifier)


def identifier(number: int) -> str:
    return f"M-{number:04d}"


def identifier_number(page_name: str) -> int | None:
    match = _ID.match(page_name)
    return int(match.group(1)) if match else None
