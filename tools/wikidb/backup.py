"""Nightly PostgreSQL dump to MinIO, retention, and last-success marker (U10; R23, KTD4, KTD14).

Attachments live in PostgreSQL (KTD4), so the dump is a complete content backup. The permanent directory is captured
by the method recorded in nubonyxia/feasibility.md.
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

MARKER = "last-success.txt"
DAILY_KEEP = 14
WEEKLY_KEEP = 8


@dataclass(frozen=True)
class Dump:
    key: str
    taken: datetime


def dump_key(prefix: str, now: datetime) -> str:
    return f"{prefix.rstrip('/')}/wikidb-{now.strftime('%Y%m%dT%H%M%SZ')}.dump"


def parse_dump(key: str) -> Dump | None:
    name = key.rsplit("/", 1)[-1]
    if not (name.startswith("wikidb-") and name.endswith(".dump")):
        return None
    try:
        taken = datetime.strptime(name[len("wikidb-"):-len(".dump")], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return Dump(key, taken)


def to_delete(dumps: list[Dump]) -> list[str]:
    """Keep the 14 newest dumps plus the newest dump of each of the 8 most recent other ISO weeks."""
    ordered = sorted(dumps, key=lambda d: d.taken, reverse=True)
    keep = {d.key for d in ordered[:DAILY_KEEP]}
    weeks: list[tuple[int, int]] = []
    for d in ordered:
        week = d.taken.isocalendar()[:2]
        if week not in weeks:
            weeks.append(week)
            if len(weeks) <= WEEKLY_KEEP:
                keep.add(d.key)
    return sorted(d.key for d in ordered if d.key not in keep)


class BackupFailed(RuntimeError):
    pass


def run_backup(s3, bucket: str, prefix: str, now: datetime, pg_dump: list[str], env: dict[str, str]) -> str:
    """Dump, upload, prune, then mark success. Nothing is uploaded when the dump fails."""
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "wikidb.dump"
        result = subprocess.run([*pg_dump, "--format=custom", f"--file={target}"], env=env,
                                capture_output=True, text=True)
        if result.returncode != 0 or not target.exists() or target.stat().st_size == 0:
            raise BackupFailed(f"pg_dump failed ({result.returncode}): {result.stderr.strip()[:500]}")
        key = dump_key(prefix, now)
        s3.upload_file(str(target), bucket, key)

    listed = s3.list_objects_v2(Bucket=bucket, Prefix=prefix.rstrip("/") + "/").get("Contents", [])
    dumps = [d for d in (parse_dump(o["Key"]) for o in listed) if d]
    for old in to_delete(dumps):
        s3.delete_object(Bucket=bucket, Key=old)
    s3.put_object(Bucket=bucket, Key=f"{prefix.rstrip('/')}/{MARKER}", Body=now.isoformat().encode())
    return key


def last_success(s3, bucket: str, prefix: str) -> datetime | None:
    try:
        body = s3.get_object(Bucket=bucket, Key=f"{prefix.rstrip('/')}/{MARKER}")["Body"].read()
    except s3.exceptions.NoSuchKey:
        return None
    return datetime.fromisoformat(body.decode().strip())


def is_fresh(marker: datetime | None, now: datetime, max_age: timedelta = timedelta(hours=48)) -> bool:
    """The check the runbooks run: a scheduled job that silently stopped shows up as stale."""
    return marker is not None and now - marker <= max_age
