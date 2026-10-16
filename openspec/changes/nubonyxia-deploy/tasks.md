# Tasks

## 1. Requests and Nubonyxia resources

- [ ] 1.1 Email nubonyxia@finances.gouv.fr for the written hosting agreement and, optionally, a Harbor GHCR cache project; verify a written answer is filed (the whole change stops if hosting is refused)
- [x] 1.2 Choose the single-level hostname under the lab domain (`<RIE lab domain>`, in `wikidb-rie`), add its redirect URI to the ProConnect Integration client (or register a second client if one client refuses two URIs); verify the client lists the URI
- [x] 1.3 Create the Harbor project (private) and a robot account limited to it; verify `crane auth login` with the robot succeeds from a Nubonyxia VSCode
- [x] 1.4 Create a discoverable PostgreSQL service; verify its `discoverable-postgresql-<id>` Secret holds `postgres-database`, `postgres-username` and `password`
- [x] 1.5 Read the ingress class and TLS setup (`kubectl get ingressclass`, an existing Ingress in the namespace); verify the values are noted for `values-rie.yaml`

## 2. Chart additions in `k8s/wikidb` (D2)

- [x] 2.1 Add `tests/unit/test_chart.py`, which renders the chart with `helm template` (skipped when `helm` is absent), and a snapshot of the current SSPCloud render; verify it passes on the unchanged chart
- [x] 2.2 Add `imageCredentials` (pull Secret plus `imagePullSecrets` on both Deployments, off when `registry` is empty); verify the set and unset tests pass
- [x] 2.3 Add `appSecrets` (rendered Secret mounted at `/secrets/app`, 0400, `appSecret` as fallback); verify the enabled and fallback tests pass
- [x] 2.4 Add `postgresql.keys` with CloudNativePG defaults; verify the default and discoverable-key tests pass
- [x] 2.5 Verify the SSPCloud render still equals the snapshot from 2.1, then `helm upgrade` on SSPCloud and check that the wiki still serves the home page
- [x] 2.6 Document the three values in `k8s/wikidb/values.yaml` comments; verify `grep -rE 'rie\.gouv\.fr|172\.16\.' k8s docs xwiki tools openspec` finds nothing

## 3. Private repository `paquitopg/wikidb-rie` (D3, D4)

- [ ] 3.1 Create the private GitHub repository and its empty Forge project, set to fast-forward merges, with a project runner tagged `nubonyxia`; add the `FORGE_REMOTES` entry in Vault; verify `git forge-push` reaches the Forge from a work branch
- [ ] 3.2 Add `.gitlab-ci.yml` (template `v3.1`, `APPLICATION_NAME=wikidb`, `APPLICATION_PORT=8080`, `HELM_CHART_PATH=helm`, `HELM_CREATE_IF_MISSING=false`), the one-line `Dockerfile` `FROM busybox`, and `values-rie.yaml` (Harbor repositories, PostgreSQL host, Secret and keys, ingress, OIDC Integration, proxy, `userAgent=curl/8.5.0`, storage class); verify `helm lint` with these values
- [ ] 3.3 Write `release.sh <wikidb commit>`: resolve both GHCR digests for `sha-<commit>`, `crane copy` to Harbor and check the digests, regenerate `helm/` from `git archive` with `name: wikidb-chart`, YAML-merge `values-rie.yaml`, commit with the commit and digests in the message; verify a dry run against the current WikiDB `main` produces a `helm/` that `helm template` renders with both digests
- [ ] 3.4 Write the repository's README (setup once, release, route B, D7 bootstrap); verify every command in it matches `release.sh` and `.gitlab-ci.yml`
- [ ] 3.5 Start the Gitlab-runner service (Harbor project and robot, app secrets `OIDC_CLIENT_ID` and `OIDC_SECRET`, no platform Basic Auth); verify the runner has a green dot in the Forge

## 4. Tooling on the RIE VSCode (D8)

- [ ] 4.1 Install `crane` in `~/work/bin` and the `wikidb` CLI from the WikiDB clone through the Nexus `pypi-group`; verify `crane version` and `wikidb --help` run; add both to the init script or the README of 3.4

## 5. First install (D7)

- [ ] 5.1 Run `release.sh` on the WikiDB commit to deliver, and push the result to GitHub; verify both digests are in Harbor
- [ ] 5.2 Create by hand `wikidb-app` (`SUPERADMIN_PASSWORD`, `OIDC_CLIENT_ID`, `OIDC_SECRET`), then `helm upgrade --install wikidb helm -n user-<id>` (route B) with `--set imageCredentials.registry=<Harbor host>`, `imageCredentials.username` and `imageCredentials.token` read from Vault (`HARBOR_ROBOT_USER`, `HARBOR_ROBOT_TOKEN`), never a hand-made pull Secret; verify `kubectl rollout status deploy/wikidb` and that `wikidb-pull` carries the label `app.kubernetes.io/managed-by: Helm`
- [ ] 5.3 Bootstrap `wikidb-robot` and `Admin` from `wikidb-tooling`, delete `wikidb-app`, restart the pod; verify superadmin sign-in is refused
- [ ] 5.4 `git forge-push` a `release/<date>` branch, fast-forward merge on the Forge, run the pipeline and the manual Deploy; verify the release revision increases, the PVC `wikidb-data` is unchanged, and no Secret holds `SUPERADMIN_PASSWORD`. If Deploy times out on `--wait`, check the rollout and re-run it
- [ ] 5.5 Read the chart name `deliver-chart.sh` pushes; verify Deploy pulled `wikidb-chart` (job log)

## 6. Verification on Nubonyxia

- [ ] 6.1 Verify the running digests equal the GHCR digests for the delivered commit (`kubectl get pod -o jsonpath` on `imageID`)
- [ ] 6.2 Run `wikidb provision` from the Nubonyxia VSCode; verify it ends without errors
- [ ] 6.3 Sign in once with a ProConnect Integration test account; verify the agent lands signed in. If it fails, capture the proxy's 403 and write to nubonyxia@finances.gouv.fr
- [ ] 6.4 Run `pytest tests/acceptance --base-url https://<RIE host>`; verify it passes
- [ ] 6.5 Check that export calls to `*.svc` bypass the proxy (an export of one sheet succeeds); verify a Word file downloads

## 7. Documentation in WikiDB

- [x] 7.1 Amend KTD2, KTD16 and U1 in the main plan (D1, D3, the storage measure); verify the plan no longer says U1 is open
- [ ] 7.2 Add a Nubonyxia section to `docs/runbooks/deploy.md` and `docs/runbooks/proconnect.md` that points to the private repository and names no RIE host; verify with the grep of 2.6

## Workflow follow-up

- Archive the change once section 6 passes and the hosting agreement is filed.
