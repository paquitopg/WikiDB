# HR listing feed

Access follows the Direction's directory (R16, R17, KTD14). Two scheduled steps run every day on Nubonyxia:

1. `wikidb fetch-listing` downloads the directory CSV and stores it in the HR bucket as
   `listings/annuaire-<UTC time>.csv`. A failed download, an error status or a file without the directory's columns
   stores nothing, and the previous listings stay.
2. `wikidb hrsync` reads the newest listing, validates it whole, and sets `GroupeDirection` and every `Groupe<code>`
   to match.

The directory's address, the lab proxy and the internal CA are settings (`HR_LISTING_URL`, `HR_LISTING_PROXY`,
`HR_LISTING_CACERT`). Their values, the bucket keys and the schedule live in the private Forge project, never in this
repository (KTD16). The directory is only reachable from the ministry network, so SSPCloud uses fictitious listings
uploaded by hand.

## Listing format

The directory export: CSV, UTF-8 (Latin-1 is converted on download), comma or semicolon separated, covering **every
agent of the Direction**.

| mail | affectation |
|---|---|
| prenom.nom@finances.gouv.fr | 2BLF |

- `mail` (or `email`) is the professional address ProConnect returns for the agent.
- `affectation` (or `bureau`) is the agent's bureau code, compared without regard to case with the registry codes.
- An agent whose bureau is in the registry joins `GroupeDirection` and `Groupe<code>`. An agent of any other bureau
  joins `GroupeDirection` only: they read the common area and the synthesis perimeter (R17).

## Checks

The whole file is rejected, and membership left unchanged, when:

- it is older than `--max-age-hours` (default 72), or misses a column;
- a row has a malformed email or an empty bureau;
- an address appears twice, or two addresses map to the same wiki user;
- it holds fewer than `--min-rows` agents (default 50);
- a registered bureau has no agent in it (a registry code that matches nobody would empty that bureau's group);
- it would remove more than 30% of `GroupeDirection` at once. Re-run with `--force` only after checking the file.

The job then fails visibly. Listed agents are added to the groups at once, even before their first sign-in; the
membership takes effect when they first sign in with ProConnect.

Each run writes a summary to `WikiDB.SynchronisationRH` (admins only): counts, listed agents who have not signed in
after 14 days, and signed-in users absent from the listing.

## Run and check

- By hand: `wikidb fetch-listing`, then `wikidb hrsync`, with `AWS_S3_ENDPOINT`, `AWS_ACCESS_KEY_ID`,
  `AWS_SECRET_ACCESS_KEY`, `WIKIDB_HR_BUCKET` and the `HR_LISTING_*` settings set.
- Freshness: `wikidb check-fresh hrsync` exits 1 when no sync has succeeded in the last 48 hours. Check it weekly, or
  wire it to the platform's alerting.
- Registry codes must be the directory's `affectation` codes (e.g. `2BLF`), so check them against a recent listing
  when adding a bureau ([add-a-bureau.md](add-a-bureau.md)).
