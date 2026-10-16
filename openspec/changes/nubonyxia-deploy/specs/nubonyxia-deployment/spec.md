# Spec Delta

## Purpose

Defines how the wiki is delivered to and runs on Nubonyxia: the same tested images, the same chart, secrets from the platform, and ProConnect reached through the lab proxy, without RIE details in the public repository.

## ADDED Requirements

### Requirement: Nubonyxia runs the image digests tested on SSPCloud
The wiki and export workloads on Nubonyxia SHALL run images whose digests equal those running on SSPCloud when the release is made. No image is rebuilt on the RIE.

#### Scenario: Digests match after a release
- **WHEN** a release made with the wiki and export digests deployed on SSPCloud is deployed on Nubonyxia
- **THEN** the running wiki and export containers report those same image digests

#### Scenario: Forced tag is ignored
- **WHEN** the platform's Deploy job passes `--set image.tag=<short SHA>`
- **THEN** both Deployments still reference their images by digest

### Requirement: One chart for both platforms
`k8s/wikidb` SHALL remain the only chart. Its Nubonyxia additions SHALL be off by default, so the SSPCloud render stays unchanged.

#### Scenario: SSPCloud render unchanged
- **WHEN** the chart is rendered with `values-sspcloud.yaml` before and after the change
- **THEN** the two renders are identical

### Requirement: Registry pull credentials from values
When `imageCredentials.registry` is set, the chart SHALL render a docker-config pull Secret and reference it from both the wiki and export Deployments.

#### Scenario: Credentials set
- **WHEN** `imageCredentials.registry`, `username` and `token` are set
- **THEN** a `kubernetes.io/dockerconfigjson` Secret is rendered and both pod specs list it in `imagePullSecrets`

#### Scenario: Credentials unset
- **WHEN** `imageCredentials.registry` is empty
- **THEN** no pull Secret is rendered and no `imagePullSecrets` is set

### Requirement: Application secrets from values
When `appSecrets.enabled` is true, the chart SHALL render a Secret from `appSecrets.secrets[]` (name and base64 value) and mount it at `/secrets/app` as read-only files. Otherwise it SHALL mount the existing `appSecret` Secret there.

#### Scenario: Runner secrets mounted
- **WHEN** `appSecrets.enabled` is true with `OIDC_CLIENT_ID` and `OIDC_SECRET`
- **THEN** the wiki pod has `/secrets/app/OIDC_CLIENT_ID` and `/secrets/app/OIDC_SECRET`, mode 0400, holding the decoded values

#### Scenario: Fallback to the hand-made Secret
- **WHEN** `appSecrets.enabled` is false
- **THEN** `/secrets/app` is mounted from the Secret named by `appSecret`

### Requirement: Configurable PostgreSQL Secret keys
The chart SHALL read the database name, user and password from the PostgreSQL Secret under the key names given in `postgresql.keys`, defaulting to CloudNativePG's `dbname`, `username` and `password`. Host and port SHALL remain plain values.

#### Scenario: Discoverable PostgreSQL
- **WHEN** `postgresql.keys` is `{database: postgres-database, username: postgres-username, password: password}`
- **THEN** `DB_DATABASE`, `DB_USER` and `DB_PASSWORD` are read from those keys

#### Scenario: Defaults
- **WHEN** `postgresql.keys` is not set
- **THEN** the keys `dbname`, `username` and `password` are used

### Requirement: No RIE specifics in the public repository
The public WikiDB repository SHALL contain no RIE hostname, internal address, Nexus or Harbor URL, ministry certificate or secret. These SHALL live only in the private `wikidb-rie` repository and its Forge mirror.

#### Scenario: Repository scan
- **WHEN** the WikiDB tree is searched for the RIE domain, the Harbor host and the lab proxy address
- **THEN** there are no matches

### Requirement: ProConnect reached through the lab proxy
On Nubonyxia, the wiki's outbound HTTPS calls SHALL use the lab proxy with a `User-Agent` the proxy accepts, while calls to in-cluster services SHALL bypass it.

#### Scenario: Sign-in through the proxy
- **WHEN** an agent signs in with ProConnect Integration on the Nubonyxia wiki
- **THEN** discovery, token and user-info calls succeed through the proxy and the agent lands signed in

#### Scenario: In-cluster calls stay direct
- **WHEN** the wiki or export service calls a `*.svc` host
- **THEN** the call does not go through the proxy

### Requirement: Platform pipeline deploys the chart
A manual Deploy job of the Forge pipeline SHALL install or upgrade the release `wikidb` from the chart and merged RIE values delivered by `wikidb-rie`, keeping the existing volume.

#### Scenario: Upgrade keeps data
- **WHEN** Deploy runs on a namespace where release `wikidb` already exists
- **THEN** the release is upgraded, the PVC `wikidb-data` is reused, and existing pages remain

### Requirement: Superadmin never held by the runner
The first install and its superadmin bootstrap SHALL run from a Nubonyxia VSCode with a hand-made Secret, and `SUPERADMIN_PASSWORD` SHALL be removed before the pipeline takes over the release.

#### Scenario: Pipeline takeover after bootstrap
- **WHEN** the first Deploy job runs after the bootstrap
- **THEN** no Secret in the namespace holds `SUPERADMIN_PASSWORD` and superadmin sign-in is disabled
