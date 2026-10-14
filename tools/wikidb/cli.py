"""`wikidb` command: provisioning, HR sync, import, backup and freshness checks.

Settings come from the environment, otherwise from /secrets/app/<NAME> (KTD11):
WIKIDB_URL, WIKIDB_ROBOT_USER, WIKIDB_ROBOT_PASSWORD; for MinIO: AWS_S3_ENDPOINT, AWS_ACCESS_KEY_ID,
AWS_SECRET_ACCESS_KEY, WIKIDB_HR_BUCKET, WIKIDB_BACKUP_BUCKET.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import backup, hrsync, importer, provision
from .client import PageRef, XWikiClient, setting

SYNC_REPORT_PAGE = PageRef(("WikiDB",), "SynchronisationRH")
HR_STATE_KEY = "state/pending-first-login.json"
HR_MARKER_PREFIX = "state"


def _s3():
    import boto3
    endpoint = setting("AWS_S3_ENDPOINT")
    return boto3.client("s3", endpoint_url=endpoint if endpoint.startswith("http") else f"https://{endpoint}",
                        aws_access_key_id=setting("AWS_ACCESS_KEY_ID"),
                        aws_secret_access_key=setting("AWS_SECRET_ACCESS_KEY"),
                        aws_session_token=os.environ.get("AWS_SESSION_TOKEN") or None)


def cmd_bootstrap(args) -> int:
    """Create a local administrator account (break-glass admin or wikidb-robot), run as superadmin once (U4)."""
    client = XWikiClient(setting("WIKIDB_URL"), "superadmin", setting("SUPERADMIN_PASSWORD"))
    password = setting(args.password_setting)
    user = PageRef(("XWiki",), args.user)
    if not client.page_exists(user):
        client.put_page(user, args.user, hidden=True)
    if not client.list_objects(user, "XWiki.XWikiUsers"):
        client.add_object(user, "XWiki.XWikiUsers", {"first_name": args.user, "active": "1", "email": "",
                                                    "password": password})
    else:
        number = client.list_objects(user, "XWiki.XWikiUsers")[0].number
        client.update_object(user, "XWiki.XWikiUsers", number, {"password": password, "active": "1"})
    admins = PageRef(("XWiki",), "XWikiAdminGroup")
    members = {o.properties.get("member") for o in client.list_objects(admins, provision.GROUPS_CLASS)}
    if f"XWiki.{args.user}" not in members:
        client.add_object(admins, provision.GROUPS_CLASS, {"member": f"XWiki.{args.user}"})
    print(f"XWiki.{args.user} is a local administrator")
    return 0


def cmd_provision(args) -> int:
    client = XWikiClient.from_settings()
    bureaux = provision.read_registry(client)
    existing = sorted({s[1] for s in client.list_spaces() if len(s) > 1 and s[0] == "Mesures" and s[1] != "Code"})
    report = provision.apply(client, provision.target_state(bureaux), existing)
    print("\n".join(report.changes) or "no change")
    for orphan in report.orphans:
        print(f"WARNING: Mesures.{orphan} belongs to no bureau in the registry (left untouched)")
    return 0


def cmd_hrsync(args) -> int:
    client, s3, bucket = XWikiClient.from_settings(), _s3(), setting("WIKIDB_HR_BUCKET")
    now = datetime.now(timezone.utc)
    listed = [o for o in s3.list_objects_v2(Bucket=bucket, Prefix=args.prefix).get("Contents", [])
              if o["Key"].lower().endswith(".csv")]
    if not listed:
        print("ERROR: no HR listing found", file=sys.stderr)
        return 2
    newest = max(listed, key=lambda o: o["LastModified"])
    content = s3.get_object(Bucket=bucket, Key=newest["Key"])["Body"].read()
    try:
        listing = hrsync.parse_listing(content, newest["LastModified"], now, provision.read_registry(client),
                                       timedelta(hours=args.max_age_hours))
    except hrsync.ListingRejected as rejected:
        print(f"ERROR: {newest['Key']} rejected, membership unchanged:", file=sys.stderr)
        for problem in rejected.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    try:
        state = json.loads(s3.get_object(Bucket=bucket, Key=HR_STATE_KEY)["Body"].read())
    except s3.exceptions.NoSuchKey:
        state = {}
    summary = hrsync.sync(client, listing, state, now)
    s3.put_object(Bucket=bucket, Key=HR_STATE_KEY, Body=json.dumps(summary.state, indent=1).encode())
    client.put_page(SYNC_REPORT_PAGE, "Synchronisation RH", summary.render(now), hidden=True)
    s3.put_object(Bucket=bucket, Key=f"{HR_MARKER_PREFIX}/{backup.MARKER}", Body=now.isoformat().encode())
    print(summary.render(now))
    return 0


def cmd_import(args) -> int:
    client = XWikiClient.from_settings()
    try:
        rows = importer.validate(importer.read_rows(Path(args.file)), provision.read_registry(client))
    except importer.ImportRejected as rejected:
        print("ERROR: file rejected, nothing written:", file=sys.stderr)
        for problem in rejected.problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    the_plan = importer.plan(client, rows)
    print("\n".join(the_plan.describe()) or "nothing to do")
    if args.apply:
        importer.execute(client, the_plan)
        print(f"applied: {len(the_plan.create)} created, {len(the_plan.fill)} filled")
    else:
        print("dry run: re-run with --apply to write")
    return 0


def cmd_backup(args) -> int:
    pg_env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
              "PGHOST": setting("POSTGRESQL_DB_HOST"), "PGPORT": setting("POSTGRESQL_DB_PORT", "5432"),
              "PGDATABASE": setting("POSTGRESQL_DB_NAME"), "PGUSER": setting("POSTGRESQL_DB_USER"),
              "PGPASSWORD": setting("POSTGRESQL_DB_PASSWORD")}
    try:
        key = backup.run_backup(_s3(), setting("WIKIDB_BACKUP_BUCKET"), args.prefix,
                                datetime.now(timezone.utc), ["pg_dump"], pg_env)
    except backup.BackupFailed as failed:
        print(f"ERROR: {failed}", file=sys.stderr)
        return 1
    print(f"backup written: {key}")
    return 0


def cmd_check_fresh(args) -> int:
    s3 = _s3()
    bucket = setting("WIKIDB_BACKUP_BUCKET" if args.job == "backup" else "WIKIDB_HR_BUCKET")
    prefix = args.prefix or ("dumps" if args.job == "backup" else HR_MARKER_PREFIX)
    marker = backup.last_success(s3, bucket, prefix)
    now = datetime.now(timezone.utc)
    if backup.is_fresh(marker, now, timedelta(hours=args.max_age_hours)):
        print(f"{args.job}: last success {marker.isoformat()}")
        return 0
    print(f"ALERT: {args.job} has not succeeded since {marker.isoformat() if marker else 'ever'}", file=sys.stderr)
    return 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="wikidb")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("bootstrap", help="create a local admin account as superadmin (first deployment only)")
    p.add_argument("user", help="account name, e.g. wikidb-robot or the break-glass admin")
    p.add_argument("--password-setting", default="WIKIDB_ROBOT_PASSWORD",
                   help="setting holding the new account's password (environment or /secrets/app)")
    sub.add_parser("provision", help="apply the bureau registry: groups, spaces, rights")
    p = sub.add_parser("hrsync", help="sync GroupeDirection and bureau groups from the newest HR listing")
    p.add_argument("--prefix", default="listings/")
    p.add_argument("--max-age-hours", type=int, default=72)
    p = sub.add_parser("import", help="import a CSV/XLSX list of measures as skeleton sheets")
    p.add_argument("file")
    p.add_argument("--apply", action="store_true", help="write (default is a dry run)")
    p = sub.add_parser("backup", help="dump PostgreSQL to the backup bucket and prune old dumps")
    p.add_argument("--prefix", default="dumps")
    p = sub.add_parser("check-fresh", help="exit 1 when a scheduled job has not succeeded recently")
    p.add_argument("job", choices=["backup", "hrsync"])
    p.add_argument("--prefix")
    p.add_argument("--max-age-hours", type=int, default=48)
    args = parser.parse_args(argv)
    return {"bootstrap": cmd_bootstrap, "provision": cmd_provision, "hrsync": cmd_hrsync, "import": cmd_import, "backup": cmd_backup,
            "check-fresh": cmd_check_fresh}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
