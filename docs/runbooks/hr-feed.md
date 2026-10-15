# HR listing feed

Bureau membership follows an HR listing (R16, KTD14). `wikidb hrsync` reads the newest listing from the HR bucket,
validates it, and sets `GroupeDirection` and every `Groupe<code>` to match.

## Listing format

CSV, UTF-8, comma or semicolon separated, two columns:

| email | bureau |
|---|---|
| prenom.nom@finances.gouv.fr | 6BCS |

- `email` is the professional address ProConnect returns for the agent.
- `bureau` is a registered bureau code, or empty for an agent of the Direction in no bureau (they see the common area
  and the synthesis perimeter only, R17).

## Rules

- The whole file is rejected, and membership left unchanged, if it is older than `--max-age-hours` (default 72),
  misses a column, holds a malformed email, an unknown bureau code or a duplicate. The job then fails visibly.
- Listed agents are added to the groups at once, even before their first sign-in; the membership takes effect
  when they first sign in with ProConnect.
- Each run writes a summary to `WikiDB.SynchronisationRH` (admins only): counts, rejected lines, listed agents who have
  not signed in after 14 days, signed-in users in no bureau.

## Run and check

- Scheduled daily on Nubonyxia by the Forge project (HR bucket, MinIO keys and schedule are defined there).
- By hand: `wikidb hrsync --prefix listings/` with `AWS_S3_ENDPOINT`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and
  `WIKIDB_HR_BUCKET` set.
- Freshness: `wikidb check-fresh hrsync` exits 1 when no run has succeeded in the last 48 hours. Check it weekly, or
  wire it to the platform's alerting.
