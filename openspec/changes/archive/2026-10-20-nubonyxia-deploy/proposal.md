# Proposal

## Why

The wiki is developed and tested on SSPCloud, but it must run on Nubonyxia because it has to be hosted on the RIE. Nothing exists on Nubonyxia yet. The plan made this depend on a feasibility probe (U1) that never ran. The probe's questions have now been answered by tests run from a Nubonyxia VSCode on 2026-10-16, so the deployment route can be fixed and built.

## What Changes

- **Route A: the platform's Forge pipeline deploys our own chart.** The template `bercyhub/nubonyxia/nubonyxia-templates` v3.1 runs Build, Package-Deliver, then a manual Deploy. With `HELM_CHART_PATH` set, Deploy installs `k8s/wikidb` instead of the platform's default chart.
  - **Fallback, route B:** `helm upgrade` from a Nubonyxia VSCode with Role admin, the routine already used on SSPCloud. We switch to B if A fails.
- **Images are copied, not rebuilt.** A Nubonyxia VSCode copies the GHCR images (`wikidb`, `wikidb-export`) into Harbor with `crane`. The chart deploys them by digest, so the RIE runs exactly the image tested on SSPCloud.
  - Rebuilding on the RIE is impossible: the Nexus has no XWiki Maven repository.
  - Neither registry mirror serves our image to Kaniko: Harbor caches only Docker Hub, and the Nexus GHCR proxies answer 404 or need DGFiP credentials.
- **Three platform-neutral changes to `k8s/wikidb`**, so it accepts what the template injects:
  1. A pull Secret built from `imageCredentials`.
  2. The app Secret built from `appSecrets`, which the template fills from the runner's `/secrets/app`, mounted at `/secrets/app`. The existing `appSecret` stays as the fallback.
  3. Configurable PostgreSQL Secret key names, for the "discoverable" PostgreSQL Secret.
- **A new private repository `paquitopg/wikidb-rie`, mirrored to the Forge.** It holds everything specific to the RIE and is delivered with `git forge-push`. It contains `.gitlab-ci.yml`, a placeholder `Dockerfile`, the RIE values, the chart copied from WikiDB, and `release.sh`, which copies the images and the chart for a given WikiDB commit. **This amends KTD16**: the RIE layer is versioned on GitHub (private) as well as the Forge, rather than on the Forge only.
- **ProConnect Integration (Internet) on Nubonyxia to begin with**, through the lab proxy with `oidc.userAgent=curl/8.5.0`. Production ProConnect comes later, with its own client.
- **Platform agreements** requested from nubonyxia@finances.gouv.fr:
  - written agreement to host the wiki;
  - optionally, a GHCR cache project in Harbor, which would remove the manual image copy.

Out of scope: production ProConnect, the HR sync and backup scheduled jobs (KTD14), and the data migration onto the RIE wiki.

## Capabilities

### New Capabilities
- `nubonyxia-deployment`: how the wiki is delivered to and runs on Nubonyxia. This covers:
  - the images in Harbor, identical by digest to those tested on SSPCloud;
  - deployment of our chart by the platform pipeline;
  - secrets coming from the runner;
  - the PostgreSQL Secret's key names;
  - outbound ProConnect calls through the lab proxy.

### Modified Capabilities
None. No specs exist yet.

## Impact

- **WikiDB repository (public):**
  - `k8s/wikidb` templates and `values.yaml`, with three additions that are inert on SSPCloud;
  - main plan, KTD16 and U1;
  - `docs/runbooks/deploy.md` and `docs/runbooks/proconnect.md`, Nubonyxia sections.
  
  No RIE hostname, address or certificate goes into this repository.
- **New private repository `paquitopg/wikidb-rie`**, plus its Forge project, set to fast-forward merges.
- **Nubonyxia resources:**
  - a Harbor project and robot account;
  - a Forge project and runner;
  - a Gitlab-runner service holding the Harbor settings and the app secrets;
  - a discoverable PostgreSQL;
  - a single-level hostname under the lab domain (`<RIE lab domain>`, in `wikidb-rie`).
- **ProConnect:** the Integration client needs the Nubonyxia redirect URI.
- **Tools:** `crane` (go-containerregistry), installed in `~/work/bin` of the Nubonyxia VSCode.
