# Back up and restore

A working wiki needs **two** things back: the PostgreSQL database and the volume's permanent directory.

- **Database:** pages, attachments, history, the recycle bin, users and groups (KTD4).
- **Permanent directory:** the record of which extensions are installed, which XWiki keeps on the volume, not in the
  database (KTD5).

A database restored onto an empty volume is **not** enough. XWiki then believes nothing is installed and reinstalls
the flavor and the applications over the restored pages. The 2026-10-15 rehearsal showed what that costs:
`XWikiAdminGroup` lost the robot and break-glass accounts, and the bureau registry `WikiDB.Bureaux` lost every
bureau. Rights, groups and content pages survived.

## Backups

| What | How | When |
|---|---|---|
| Database | `wikidb backup`: `pg_dump` in custom format to the backup bucket under `dumps/`, with retention (dailies 14 days, weeklies 8 weeks) and a last-success marker | nightly |
| Permanent directory | archive of `/usr/local/xwiki/data` without `cache`, `logs` and `tmp` (below) | after every deployment, and weekly |

The installed-extension state only changes when a new image is deployed, so the archive can be older than the dump.
The search index in it is brought back in line with the database when XWiki starts (`solr.synchronizeAtStartup`).

```bash
kubectl exec deploy/wikidb -n <namespace> -- tar -C /usr/local/xwiki -czf - \
  --exclude=data/cache --exclude=data/logs --exclude=data/tmp data > wikidb-data-<date>.tgz
```

Upload the archive next to the dumps (`permanent-dir/` in the backup bucket). On Nubonyxia the Forge project
schedules both jobs; check freshness with `wikidb check-fresh backup`.

## Restore into an empty namespace

1. Create a PostgreSQL service (CloudNativePG) and the `wikidb-app` Secret as for a first install
   ([deploy.md](deploy.md)).
2. Restore the dump with the new `-app` Secret's credentials:
   `pg_restore --no-owner --no-privileges --clean --if-exists -h <cluster>-rw -U <user> -d <db> wikidb-<date>.dump`
3. Install the chart **with the wiki stopped**, so XWiki cannot start on an empty volume:
   `helm install wikidb k8s/wikidb ... --set replicas=0 --set image.digest=<digest of the archive's deployment>`
4. Fill the volume from the archive with a throwaway pod that mounts `<release>-data` at `/usr/local/xwiki`:
   `kubectl exec -i <pod> -- tar -C /usr/local/xwiki -xzf - < wikidb-data-<date>.tgz`, then delete the pod.
5. Start the wiki: `helm upgrade wikidb k8s/wikidb --reuse-values --set replicas=1`.
6. Check that the startup installed nothing (`kubectl logs deploy/wikidb | grep -c InstallJob` prints 0), run
   `wikidb provision` (it should print `no change`), then the acceptance suite on dev, or the smoke check on
   Nubonyxia.

Use the image digest that was deployed when the archive was taken. A newer image then upgrades the restored wiki
normally on its next deployment.

## Rehearsal record

| Date | Source | Result |
|---|---|---|
| 2026-10-15 | dev dump only, empty volume | **Failed:** reinstall reset `XWikiAdminGroup` and emptied `WikiDB.Bureaux`; local logins refused |
| 2026-10-15 | dev dump (1,770 pages) + permanent-directory archive (55 MB), image 1.0.8 | **Passed:** restore 4 s, wiki up 2 min 13 s after the restore began, no reinstall, `provision`: no change, acceptance suite 42/42 |
