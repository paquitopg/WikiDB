# Deploy the wiki

The wiki runs two images built by GitHub Actions and pushed to GHCR:

| Image | Workflow | Built when |
|---|---|---|
| `ghcr.io/paquitopg/wikidb` (XWiki + offline extensions) | `.github/workflows/build-image.yml` | `xwiki/**` changes |
| `ghcr.io/paquitopg/wikidb-export` (Word/PowerPoint export) | `.github/workflows/build-export-image.yml` | `export/**`, `tools/wikidb/**`, `pyproject.toml` change |

Each build is tagged `1.0.<run>`, `sha-<commit>` and `dev` (feature branches) or `latest` (`main`). **Deploy by
digest**, never by a moving tag. Find a digest with:

```bash
gh api /users/paquitopg/packages/container/wikidb/versions --jq '.[] | select(.metadata.container.tags | index("1.0.12")) | .name'
```

SSPCloud and Nubonyxia run the same images, by the same digests, with the same Helm chart `k8s/wikidb`. See
[Nubonyxia](#nubonyxia) for the RIE.

## Prerequisites (SSPCloud)

- A VSCode service with **Role admin** (`kubectl auth can-i create secrets` answers `yes`).
- A PostgreSQL service from the catalog (CloudNativePG). Its `<name>-rw` service and `<name>-app` Secret go into
  `k8s/wikidb/values-sspcloud.yaml`.
- The Secret `wikidb-app`, created by hand, never in Git (keys: `OIDC_CLIENT_ID`, `OIDC_SECRET`, see
  [proconnect.md](proconnect.md), and `SUPERADMIN_PASSWORD` for the first install only):

  ```bash
  read -rsp "Superadmin password: " PW && echo
  kubectl create secret generic wikidb-app -n user-<id> --from-literal=SUPERADMIN_PASSWORD="$PW"
  unset PW
  ```

## First install

1. Check the render against the cluster:
   `helm template wikidb k8s/wikidb -f k8s/wikidb/values-sspcloud.yaml --set image.digest=<wiki> --set export.image.digest=<export> | kubectl apply --dry-run=server -n user-<id> -f -`
2. `helm upgrade --install wikidb k8s/wikidb -n user-<id> -f k8s/wikidb/values-sspcloud.yaml --set image.digest=<wiki> --set export.image.digest=<export>`
3. Wait for `kubectl rollout status deploy/wikidb` (the first start installs the default UI: up to 10 minutes).
4. Create the local administrators as superadmin (KTD13). Put `WIKIDB_ROBOT_PASSWORD` and `BREAKGLASS_PASSWORD` in
   a second Secret (`wikidb-tooling`) and, from a shell that reads them without echo:

   ```bash
   wikidb bootstrap wikidb-robot
   wikidb bootstrap Admin --password-setting BREAKGLASS_PASSWORD
   ```

5. Remove `SUPERADMIN_PASSWORD` from `wikidb-app` and restart the pod: superadmin is then disabled.
6. Register the bureaux and run `wikidb provision` ([add-a-bureau.md](add-a-bureau.md)).
7. Smoke check: the home page asks for ProConnect sign-in; the acceptance suite passes on dev
   (`pytest tests/acceptance --base-url https://<host>`).

## Upgrade

1. Wait for the CI run of the commit to deploy, and read both digests.
2. `helm upgrade wikidb k8s/wikidb -n user-<id> -f k8s/wikidb/values-sspcloud.yaml --set image.digest=<wiki> --set export.image.digest=<export>`
3. The wiki restarts (`Recreate`, a few minutes of downtime) and upgrades its applications non-interactively.
   Updating only the export digest does not restart XWiki.
4. Run `wikidb provision` (new spaces or rights may come with the release), then the acceptance suite on dev.
5. Archive the volume's permanent directory, which records the newly installed extensions
   ([restore.md](restore.md#backups)).

### DSFR skin

The skin `WikiDB.Code.Skin` overrides two Flamingo templates; their sources are `xwiki/app/src/main/skin/`.

- **XWiki upgrade:** diff Flamingo's `menus_view.vm` and `footer.vm` between the old and new platform tags
  (`xwiki-platform-flamingo-skin-resources/src/main/resources/flamingo/` in xwiki-platform) and carry the changes into
  the overrides. The acceptance tests in `tests/acceptance/test_appearance.py` fail if search or the user menu leave the
  header.
- **DSFR upgrade:** set `dsfr.version` and `dsfr.sha512` in `xwiki/pom.xml` from the npm registry
  (`npm view @gouvfr/dsfr@<version> dist.integrity`, base64 to hex), choosing a release at least two weeks old. Then
  walk the visual checklist of the DSFR plan on dev: home, a measure sheet in view and edit, search results, the login
  page, Administration, a dropdown and a modal, on desktop and at 360 px.

## Rollback

`helm rollback wikidb <revision>` returns to the previous digests. Application pages keep the newer version (XWiki
does not downgrade extensions): restore the database ([restore.md](restore.md)) if the newer pages are the problem.

## Export service

Disable it with `--set export.enabled=false`; the wiki is unaffected. Official Word and PowerPoint templates, when
supplied, go in a directory named by `WIKIDB_EXPORT_TEMPLATES` (`fiche.docx`, `fiche.pptx`); without it the export
uses neutral built-in styles.

## Nubonyxia

The RIE layer lives in the private repository `paquitopg/wikidb-rie`, mirrored to a Forge project. That repository's
README is the runbook: setup, release, first install, fallback. It holds every RIE host, the proxy and the Harbor
project, which stay out of this repository. The design is in `openspec/changes/nubonyxia-deploy/design.md`.

- **Images are copied, not rebuilt.** `release.sh` copies the digests running on SSPCloud from GHCR into Harbor with
  `crane`, so the RIE runs exactly what was tested here.
- **The chart is this one.** `release.sh` regenerates `helm/` from `k8s/wikidb` at a WikiDB commit and merges the RIE
  values. The Forge pipeline's manual Deploy job installs it. The chart values `imageCredentials`, `appSecrets` and
  `postgresql.keys` (see `k8s/wikidb/values.yaml`) exist for that job and stay off on SSPCloud.
- **First install** runs from a Nubonyxia VSCode with `helm`, so the runner never holds `SUPERADMIN_PASSWORD`. The
  pipeline takes over the release `wikidb` afterwards.
