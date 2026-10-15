"""Word and PowerPoint export service for measure sheets (U13; R27, KTD17, KTD18).

GET /export/Mesures/<B>/<Secteur|Synthese>/<M-NNNN>.<docx|pptx> fetches Mesures.Code.ExportData with the reader's own
cookie or Authorization header, so XWiki decides what the reader may export; the service holds no credentials.

Settings (environment, otherwise /secrets/app, KTD11): WIKIDB_INTERNAL_URL, the wiki as reached from the service
(e.g. http://wikidb:8080); WIKIDB_EXPORT_TEMPLATES, an optional directory holding fiche.docx and fiche.pptx.
Run: uvicorn wikidb.export.server:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Callable
from urllib.parse import quote, urlsplit

import requests
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response

from ..client import setting
from . import docx_writer, pptx_writer
from .sheet import from_export_data

FORMATS = {
    "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", docx_writer, "fiche.docx"),
    "pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", pptx_writer, "fiche.pptx"),
}
_SHEET_PATH = re.compile(r"(Mesures/[A-Za-z0-9]+/(?:Secteur|Synthese)/M-\d{4,})\.(docx|pptx)")
_FORWARDED = ("cookie", "authorization")

# fetch(internal_url, mesure_reference, forwarded_headers) -> (status, json-or-None)
Fetch = Callable[[str, str, dict], tuple[int, dict | None]]


def fetch_export_data(internal_url: str, reference: str, headers: dict) -> tuple[int, dict | None]:
    r = requests.get(f"{internal_url.rstrip('/')}/bin/get/Mesures/Code/ExportData",
                     params={"xpage": "plain", "outputSyntax": "plain", "mesure": reference},
                     headers=headers, allow_redirects=False, timeout=60)
    return r.status_code, (r.json() if r.status_code == 200 else None)


def _page(status: int, message: str, link: tuple[str, str] | None = None) -> HTMLResponse:
    extra = f'<p><a href="{html.escape(link[0])}">{html.escape(link[1])}</a></p>' if link else ""
    body = (f'<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Export</title></head>'
            f"<body><p>{html.escape(message)}</p>{extra}</body></html>")
    return HTMLResponse(body, status_code=status)


def _public_origin(request: Request) -> str:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto.split(',')[0].strip()}://{host.split(',')[0].strip()}"


def create_app(internal_url: str | None = None, templates: Path | None = None,
               fetch: Fetch = fetch_export_data) -> FastAPI:
    app = FastAPI(title="Export des fiches mesures", docs_url=None, redoc_url=None, openapi_url=None)

    def wiki() -> str:
        return internal_url or setting("WIKIDB_INTERNAL_URL")

    def template_dir() -> Path | None:
        if templates:
            return templates
        configured = setting("WIKIDB_EXPORT_TEMPLATES", "")
        return Path(configured) if configured else None

    @app.get("/export/healthz", response_class=PlainTextResponse)
    def healthz() -> str:
        return "ok"

    @app.get("/export/{path:path}")
    def export(path: str, request: Request):
        match = _SHEET_PATH.fullmatch(path)
        if not match:
            return _page(404, "Fiche introuvable.")
        reference, extension = match.group(1).replace("/", "."), match.group(2)
        headers = {h: request.headers[h] for h in _FORWARDED if h in request.headers}
        status, data = fetch(wiki(), reference, headers)
        if status == 401 or 300 <= status < 400:
            # No valid session: XWiki redirects to ProConnect. Never follow it; send the reader to sign in again.
            back = quote(f"/export/{path}", safe="/")
            return _page(401, "Votre session a expiré. Connectez-vous au wiki puis relancez l'export.",
                         (f"/bin/login/XWiki/XWikiLogin?xredirect={back}", "Se connecter"))
        if status != 200 or not data:
            return _page(404 if status in (403, 404) else 502, "Fiche introuvable.")
        origin = _public_origin(request)
        internal = urlsplit(wiki())
        sheet = from_export_data(data, origin, (f"{internal.scheme}://{internal.netloc}",))
        media_type, writer, template_name = FORMATS[extension]
        directory = template_dir()
        content = writer.build(sheet, directory / template_name if directory else None)
        name = sheet.file_name(extension)
        ascii_name = name.encode("ascii", "replace").decode().replace("?", "_")      # file_name() already removed quotes
        disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"
        return Response(content, media_type=media_type, headers={"Content-Disposition": disposition})

    return app


app = create_app()
