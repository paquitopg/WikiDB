"""Daily download of the Direction's directory into the HR bucket (U8; R16, KTD14).

The directory is a CSV (`mail`, `affectation`) served on the ministry network. The address, the proxy and the CA are
settings, never defaults in this public repository (KTD16). On Nubonyxia the host is not resolved from job pods, so the
request goes through the lab proxy, which filters on the CONNECT request's User-Agent: curl's passes.
`wikidb hrsync` then validates the stored file fully before touching any group.
"""

from __future__ import annotations

import csv
import http.client
import io
import ssl
from datetime import datetime
from urllib.parse import urlsplit

from .hrsync import COLUMNS

USER_AGENT = "curl/8.5.0"


class FetchFailed(RuntimeError):
    pass


def download(url: str, proxy: str | None = None, cacert: str | None = None, timeout: int = 60) -> bytes:
    target = urlsplit(url)
    https = target.scheme == "https"
    context = None
    if https:
        # The directory's certificate is signed by an internal CA; without its file the certificate is not checked.
        context = ssl.create_default_context(cafile=cacert) if cacert else ssl._create_unverified_context()
    path = (target.path or "/") + (f"?{target.query}" if target.query else "")
    try:
        if proxy and https:
            via = urlsplit(proxy if "://" in proxy else f"http://{proxy}")
            conn = http.client.HTTPSConnection(via.hostname, via.port or 3128, timeout=timeout, context=context)
            conn.set_tunnel(target.hostname, target.port or 443, headers={"User-Agent": USER_AGENT})
        elif https:
            conn = http.client.HTTPSConnection(target.hostname, target.port, timeout=timeout, context=context)
        else:
            conn = http.client.HTTPConnection(target.hostname, target.port, timeout=timeout)
        conn.request("GET", path, headers={"User-Agent": USER_AGENT})
        response = conn.getresponse()
        status, body = response.status, response.read()
    except (OSError, http.client.HTTPException) as error:
        raise FetchFailed(f"download failed ({'through the proxy' if proxy and https else 'direct'}): {error}")
    if status != 200:
        raise FetchFailed(f"the server answered {status} instead of 200")
    return body


def fetch_listing(url: str, s3, bucket: str, prefix: str, now: datetime, proxy: str | None = None,
                  cacert: str | None = None) -> str:
    """Download the directory and store it as UTF-8 under <prefix>annuaire-<UTC time>.csv; return the key."""
    body = download(url, proxy, cacert)
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = body.decode("iso-8859-1")
    first_line = text.split("\n", 1)[0]
    delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
    header = [c.strip().lower() for c in next(csv.reader(io.StringIO(first_line), delimiter=delimiter), [])]
    if not all(any(name in header for name in names) for names in COLUMNS.values()):
        raise FetchFailed(f"unexpected columns {header[:5]}: the file is not the directory, nothing stored")
    key = f"{prefix.rstrip('/')}/annuaire-{now.strftime('%Y%m%dT%H%M%SZ')}.csv"
    s3.put_object(Bucket=bucket, Key=key, Body=text.encode("utf-8"))
    return key
