# Back up and restore

All content (pages, attachments, history, users and groups) is in PostgreSQL (KTD4). The volume holds the installed
extensions, which the image can reinstall (KTD5).

## Backups

`wikidb backup` runs `pg_dump` in custom format, uploads it to the backup bucket under `dumps/`, writes a
last-success marker and prunes old dumps (dailies for 14 days, weeklies for 8 weeks). Nubonyxia schedules it nightly
from the Forge project. Check freshness with `wikidb check-fresh backup` (exit 1 after 48 hours without success).

## Restore into an empty namespace

1. Create the PostgreSQL service, the `wikidb-app` Secret and the tooling Secret as for a first install
   ([deploy.md](deploy.md)), but do not start the wiki yet.
2. Download the chosen dump from the backup bucket and restore it with the `-app` Secret's credentials:
   `pg_restore --no-owner --no-privileges --clean --if-exists -d "$DATABASE_URL" wikidb-<date>.dump`
3. Deploy the image digest that was running when the dump was taken (or a newer one). On first start XWiki finds the
   database already populated and only reinstalls the extensions into the empty volume.
4. Run `wikidb provision`, then the acceptance suite on dev, or the smoke check on Nubonyxia.

## Rehearsal record

The restore is rehearsed once on SSPCloud with fictitious content before the pilot opens (U10).

| Date | Dump | Duration | Acceptance suite after restore | Remarks |
|---|---|---|---|---|
| | | | | |
