import io
from datetime import datetime, timedelta, timezone

import pytest

from wikidb.backup import (MARKER, BackupFailed, Dump, dump_key, is_fresh, last_success, parse_dump,
                           run_backup, to_delete)

NOW = datetime(2026, 10, 14, 2, 0, tzinfo=timezone.utc)


class FakeS3:
    class exceptions:
        class NoSuchKey(Exception):
            pass

    def __init__(self):
        self.store: dict[str, bytes] = {}

    def upload_file(self, filename, bucket, key):
        self.store[key] = open(filename, "rb").read()

    def put_object(self, Bucket, Key, Body):
        self.store[Key] = Body

    def get_object(self, Bucket, Key):
        if Key not in self.store:
            raise self.exceptions.NoSuchKey()
        return {"Body": io.BytesIO(self.store[Key])}

    def list_objects_v2(self, Bucket, Prefix):
        return {"Contents": [{"Key": k} for k in sorted(self.store) if k.startswith(Prefix)]}

    def delete_object(self, Bucket, Key):
        del self.store[Key]


def nightly(days: int) -> list[Dump]:
    return [Dump(dump_key("dumps", NOW - timedelta(days=i)), NOW - timedelta(days=i)) for i in range(days)]


def test_retention_keeps_14_newest_and_one_per_week_for_8_weeks():
    dumps = nightly(90)
    deleted = set(to_delete(dumps))
    kept = [d for d in dumps if d.key not in deleted]
    assert all(d in kept for d in dumps[:14])
    weeks = {d.taken.isocalendar()[:2] for d in kept}
    assert len(weeks) == 8
    assert len(kept) == 14 + (8 - len({d.taken.isocalendar()[:2] for d in dumps[:14]}))
    assert min(d.taken for d in kept) > NOW - timedelta(weeks=8)


def test_retention_keeps_everything_when_there_are_few_dumps():
    assert to_delete(nightly(10)) == []


def test_dump_keys_round_trip():
    assert parse_dump(dump_key("dumps", NOW)) == Dump("dumps/wikidb-20261014T020000Z.dump", NOW)
    assert parse_dump("dumps/notes.txt") is None


def test_successful_run_uploads_dump_and_marks_success(tmp_path):
    s3 = FakeS3()
    fake_dump = ["sh", "-c", 'for a; do case "$a" in --file=*) echo data > "${a#--file=}";; esac; done', "pg_dump"]
    key = run_backup(s3, "b", "dumps", NOW, fake_dump, {"PATH": "/usr/bin:/bin"})
    assert s3.store[key] == b"data\n"
    assert last_success(s3, "b", "dumps") == NOW


def test_failed_dump_uploads_nothing_and_does_not_mark_success():
    s3 = FakeS3()
    with pytest.raises(BackupFailed, match="connection refused"):
        run_backup(s3, "b", "dumps", NOW, ["sh", "-c", "echo connection refused >&2; exit 1"],
                   {"PATH": "/usr/bin:/bin"})
    assert s3.store == {}
    assert f"dumps/{MARKER}" not in s3.store


def test_freshness_check_flags_a_job_that_stopped_running():
    assert is_fresh(NOW - timedelta(hours=20), NOW)
    assert not is_fresh(NOW - timedelta(hours=50), NOW)
    assert not is_fresh(None, NOW)
