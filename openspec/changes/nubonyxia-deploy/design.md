# Design

## Context

See proposal.md, "Why". The facts below were measured from a Nubonyxia VSCode on 2026-10-16. They replace the feasibility probe U1 of `docs/plans/2026-10-14-1629-feat-direction-budget-wiki-plan.md`.

| Question | Test | Result |
|---|---|---|
| Does the RIE reach GHCR? | `curl` to `ghcr.io/v2/…/tags/list` and `pkg-containers.githubusercontent.com` through the VSCode's proxy | 200 and the tunnel opened. **Only through the lab proxy** (`<lab proxy URL>`, in `wikidb-rie`) |
| Which `User-Agent` reaches ProConnect Integration through the proxy? | `CONNECT` to `fca.integ01.dev-agentconnect.fr` | `Java/21.0.12.1` refused (000). `curl/8.5.0` and `curl/8.5.0 Java/21.0.12.1` → 200 |
| Does the proxy accept a Go client (`crane`)? | `CONNECT` with `Go-http-client/1.1` to `ghcr.io` | 401 from GHCR, so it passes |
| Can the namespace hold the wiki's volume and resources? | `kubectl get storageclass`, `kubectl describe quota`, a test PVC | Checked by the user on 2026-10-16: OK. This lifts KTD5's stop condition. The storage class goes in `values-rie.yaml` |
| Can WikiDB be rebuilt on the RIE? | Nexus repository list | Maven Central and Shibboleth only, no `maven.xwiki.org`. **No** |
| Can a registry mirror serve our image to Kaniko? | Harbor proxy-cache projects; Nexus `ghcr_registry`; DGFiP `nexus-ghcr-pull` | Harbor caches Docker Hub (`docker_hub`) and `us-docker_pkg_dev` only. Nexus answers 404 for the manifest, and 404 on the `/v2/repository/…` form Kaniko uses. DGFiP has no HTTPS and requires credentials over HTTP. **No** |
| What does the template do with a custom chart? | `nubonyxia-unified.gitlab-ci.yml` v3.1, plus `package-chart.sh` and `deploy-k8s.sh` from `nubonyxia-job-runner:3.1.7` | See the contract below |

The Java version is that of the current image (Temurin 21.0.12.1). Java appends ` Java/<version>` to `http.agent`. The chart already passes `-Dhttp.agent` from `oidc.userAgent` (`k8s/wikidb/templates/_helpers.tpl`).

**The template's contract for a custom chart (v3.1):**
- **Build.** Kaniko builds the root `Dockerfile` and pushes `<harbor>/<runner project>/<APPLICATION_NAME>:<short SHA>`. It is logged in to Harbor only, and its `--registry-mirror` is Harbor's `docker_hub`. The ministry CA is copied into the build context as `mefr-ca.crt`.
- **Package.** The chart is copied as is from `HELM_CHART_PATH`, with no placeholders replaced. `version` and `appVersion` are overwritten. `HELM_VALUES_OVERRIDE` is appended as text to `values.yaml`. The chart is then pushed to Harbor OCI.
- **Deploy (manual).** The runner's namespace is the only target.
  ```
  helm upgrade --install <APPLICATION_NAME> oci://<harbor>/<project>/<APPLICATION_NAME>-chart \
    [-f values-secrets.yaml] --set image.tag=<short SHA> \
    --set imageCredentials.{registry,username,token}=… \
    --set serviceAccount.create=false --set rbac.create=false --wait --timeout 10m
  ```
  `values-secrets.yaml` is `appSecrets: {enabled: true, secrets: [{name, valueBase64}]}`, generated from the files in the runner's `/secrets/app`.
- **Default chart only.** The `STARTUP_*`, `RESOURCE_*`, `PERSISTENCE_*` and `INGRESS_*` variables fill the default chart's placeholders and do nothing for a custom chart.

## Goals / Non-Goals

**Goals:**
- The RIE runs the image digests tested on SSPCloud, unchanged.
- `k8s/wikidb` remains the single chart. Its Nubonyxia additions are inert on SSPCloud.
- No RIE hostname, address, certificate or secret enters the public WikiDB repository.
- Route B stays possible at all times, with the same chart and the same values.

**Non-Goals:**
- Making the Kaniko build meaningful. It exists only because Package-Deliver waits for it.
- Automating the image copy. It stays a manual step until Harbor has a GHCR cache.
- Scheduled jobs (KTD14) and their access to PostgreSQL and MinIO.

## Decisions

**D1. Deploy by digest from images copied into Harbor.** A Nubonyxia VSCode runs `crane copy ghcr.io/paquitopg/<image>@<digest> <harbor>/<project>/<image>-upstream@<digest>` for `wikidb` and `wikidb-export`. The RIE values set `image.repository` and `image.digest`. The chart's `wikidb.image` helper prefers the digest, so the `image.tag` that Deploy forces is ignored.
- *Alternatives considered:*
  - Deploying the Kaniko-built image: its tag is the `wikidb-rie` short SHA, and its digest differs from what was tested.
  - Pulling GHCR from the build: not reachable, see Context.
  - Ask for a Harbor GHCR cache: requested, but not in our hands. Once it exists, only `image.repository` changes.
- The root `Dockerfile` is a `FROM busybox` line plus `COPY helm/Chart.yaml /`, pulled through Harbor's `docker_hub` mirror that Kaniko already uses. The Build job's image is never deployed, so it must be cheap: `FROM` the copied `wikidb` image would pull the whole XWiki image on every pipeline for nothing.
- *This amends KTD2*: Nubonyxia adds no ministry CA to the image. Every outbound call today goes to ProConnect Internet, which has a public certificate. When production moves to ProConnect RIE, whose certificate is likely signed by the ministry CA, the JVM gets a truststore mounted from a ConfigMap (`-Djavax.net.ssl.trustStore`). The image is still not rebuilt.

**D2. Three additions to `k8s/wikidb`, all off by default.**
1. **Pull Secret.** When `imageCredentials.registry` is set, render a `kubernetes.io/dockerconfigjson` Secret and reference it in `imagePullSecrets` of both Deployments.
2. **App secrets.** When `appSecrets.enabled`, render a Secret from `appSecrets.secrets[].valueBase64` and mount it at `/secrets/app` instead of `appSecret`. The entrypoint already maps `/secrets/app/<NAME>` to the variables XWiki expects (KTD11).
3. **PostgreSQL key names.** Add `postgresql.keys.{database,username,password}`, defaulting to CloudNativePG's `dbname`, `username` and `password`. The RIE sets them to `postgres-database`, `postgres-username` and `password`. `password` is the user's password, not `postgres-password`. `postgresql.host` and `port` stay plain values: the port in that Secret is not base64-encoded and unusable, so it stays `5432`.
- *Alternative considered:* create `wikidb-app` and the pull Secret by hand with `kubectl`. That needs no chart change, but every secret change would then need a VSCode with Role admin, and route A would no longer be self-contained. The hand-made `appSecret` remains the fallback for route B.

**D3. The RIE layer lives in `paquitopg/wikidb-rie`, private on GitHub, mirrored to the Forge.** GitHub `main` is development and Forge `main` is what runs. Delivery uses `git forge-push` on a `release/<date>` branch and fast-forward merges only, the Opsonium model in the onyxia skill's `nubonyxia.md`. Layout:
- `.gitlab-ci.yml`: include the template at `v3.1`, plus
  - `APPLICATION_NAME=wikidb`
  - `APPLICATION_PORT=8080`
  - `HELM_CHART_PATH=helm`
  - `HELM_CREATE_IF_MISSING=false`
- `Dockerfile`: one `FROM` line, see D1.
- `values-rie.yaml`:
  - Harbor repositories and digests;
  - PostgreSQL host, Secret and keys;
  - ingress class and single-level hostname;
  - `oidc.discoveryUrl` (Integration), `proxyHost`/`proxyPort` (`<lab proxy host>`/`<lab proxy port>`), `userAgent=curl/8.5.0`.
- `helm/`: generated, never edited by hand.
- `release.sh`: see D4.

*This amends KTD16 ("RIE files only in the private Forge project"):* the private GitHub repository is the source, so the layer can be edited from SSPCloud and is backed up. The chart is copied rather than referenced, because the runner cannot reach GitHub.

**D4. `release.sh <wikidb commit>` is the only release step that touches images and the chart.** Run from a Nubonyxia VSCode, it does four things (the fixed `Dockerfile` of D1 is not touched):
1. takes the two digests that run on SSPCloud (`helm get values wikidb`) and checks they exist on GHCR. The image workflows are path-filtered, so most WikiDB commits have no `sha-<commit>` tag to resolve;
2. runs `crane copy` for both and checks that each digest is unchanged in Harbor;
3. replaces `helm/` with `git archive <commit> k8s/wikidb` from a WikiDB clone, sets `name: wikidb-chart`, and merges `values-rie.yaml` into `helm/values.yaml` with a real YAML merge;
4. records the WikiDB commit and both digests in the commit message, and commits.

The merge is done here, not through `HELM_VALUES_OVERRIDE`, because the template appends that variable as text, and duplicate top-level keys are not a safe override.

**D5. ProConnect Integration on Nubonyxia, through the proxy.** The same Integration client serves both platforms if ProConnect accepts both redirect URIs; otherwise there is one client per platform. `-Dhttps.proxyHost`, `-Dhttps.proxyPort` and `-Dhttp.agent=curl/8.5.0` apply JVM-wide. `nonProxyHosts` keeps in-cluster traffic (`*.svc`) direct, and must also cover the RIE domain (`<RIE domain>`) if the wiki ever calls an RIE host.

**D6. Route B is the same chart and the same merged values,** installed with `helm upgrade --install wikidb wikidb-rie/helm -n user-<id>` from a Nubonyxia VSCode. The app secrets come from a hand-made `wikidb-app` Secret; the Harbor robot is passed with `--set imageCredentials.*`, read from Vault, so the chart renders `wikidb-pull` exactly as Deploy does. It is the fallback for any failure of the template's jobs.

**D7. The first install and its superadmin bootstrap use route B; every later delivery uses route A.** The runner never holds `SUPERADMIN_PASSWORD`.
1. From a Nubonyxia VSCode, create by hand the `wikidb-app` Secret (`SUPERADMIN_PASSWORD`, `OIDC_CLIENT_ID`, `OIDC_SECRET`). The pull Secret is **not** made by hand: Deploy later renders `wikidb-pull`, and Helm refuses to adopt an object it did not create. Route B passes `imageCredentials.registry`, `username` and `token` with `--set`, the robot's name and password read from Vault (`git-credential-vault secret HARBOR_ROBOT_USER` / `HARBOR_ROBOT_TOKEN`), so the release owns `wikidb-pull` from the start. The password then sits in the release's values, as it does under Deploy.
2. Run `helm upgrade --install` with route B, then the bootstrap steps of `deploy.md`.
3. Delete `wikidb-app`.
4. Run the first Deploy job. It takes over the release `wikidb`, which keeps the same name and therefore the same PVC `wikidb-data`.
- *Alternative considered:* bootstrap through route A. Removing the password then means deleting the Gitlab-runner service, relaunching it, and re-running Deploy, because a running Onyxia service's values cannot be edited. The password would also stay in the runner's values until then.

**D8. The `wikidb` CLI on the RIE is installed from the WikiDB clone through the Nexus.** In the Nubonyxia VSCode, run `uv pip install -e .` (or `pip`) with the Nexus `pypi-group` index. The CLI reads its settings from the environment or from `/secrets/app` (KTD11). Its passwords come from a `wikidb-tooling` Secret in the RIE namespace, read without echo, as on SSPCloud. Like every other tool, it is reinstalled by the init script or by hand in each new VSCode, and kept under `~/work`.

## Risks / Trade-offs

- [The template changes its contract in a later version] → Pin `ref: v3.1` and `nubonyxia-job-runner:3.1.7`, and re-read both scripts before upgrading.
- [`--wait --timeout 10m` expires on the first start, which installs the default UI] → The Deploy job may go red while the pod keeps starting. Check `kubectl rollout status`, and re-run Deploy once the pod is ready. The startup probe allows 600 s.
- [Manual image copy from a VSCode] → Documented in `release.sh`, and removed by a Harbor GHCR cache if the platform team adds one.
- [The robot password passes through `--set` into a Secret, and the template prints the registry username in the logs] → This is the platform's own mechanism. Use a robot account limited to the WikiDB Harbor project.
- [`http.agent` is JVM-wide, so every outbound Java call claims to be curl] → This is acceptable: the only outbound calls are ProConnect's.
- [Java may not send `User-Agent` on `CONNECT`, in which case the proxy refuses it] → The first ProConnect sign-in on Nubonyxia is the check. If it fails, look at the proxy's 403 and ask nubonyxia@finances.gouv.fr to open the destination.
- [Hosting agreement refused] → Nothing technical helps; it blocks the whole change. Request it first.
- [`helm/` drifts from WikiDB's chart] → It is only ever regenerated by `release.sh` from a WikiDB commit.

## Migration Plan

1. **Requests:**
   - Email nubonyxia@finances.gouv.fr for the hosting agreement in writing and, optionally, a Harbor GHCR cache.
   - Choose the hostname, then add the Nubonyxia redirect URI to the ProConnect Integration client.
2. **WikiDB:** the three chart additions of D2, with unit coverage of the rendered templates. Check that SSPCloud renders unchanged (`helm template` diff) and still deploys.
3. **Nubonyxia resources:**
   - a Harbor project and robot account;
   - an empty Forge project, set to fast-forward merges, with a project runner tagged `nubonyxia`;
   - a Gitlab-runner service with Harbor and the app secrets `OIDC_CLIENT_ID` and `OIDC_SECRET`;
   - a discoverable PostgreSQL.
4. **`wikidb-rie`:** create it, then run the first `release.sh`.
5. **First install (D7):** route B with a hand-made `wikidb-app` and the robot passed by `--set`, bootstrap, delete `wikidb-app`. Then `git forge-push`, the merge request, the pipeline, and the first manual Deploy.
6. **Verify:**
   - rollout;
   - `wikidb provision` from a Nubonyxia VSCode (D8);
   - the acceptance suite against the RIE host;
   - one ProConnect Integration sign-in with a test account.

**Rollback:** re-run Deploy on the previous Forge `main` commit, or `helm rollback wikidb`. The SSPCloud deployment is not affected at any step.

## Open Questions

- The Nubonyxia ingress class and TLS setup: `kubectl get ingressclass`, and an existing Ingress in the namespace. This only fills a value.
- ~~The chart name under which `deliver-chart.sh` pushes~~: read on 2026-10-19, it pushes `<project>/<Chart.yaml name>`, so D4's renaming to `wikidb-chart` is what Deploy pulls. The same log shows that `package-chart.sh` falls back to the platform's default chart when `HELM_CHART_PATH` is missing, despite `HELM_CREATE_IF_MISSING=false`. The `COPY helm/Chart.yaml` line in the `Dockerfile` (D1) makes the Build fail instead.
- Whether ProConnect Integration accepts two redirect URIs on one client: this decides one client or two, with no design change.
- Whether `nonProxyHosts` needs the RIE domain (`<RIE domain>`): only if the wiki ever calls an RIE host.
