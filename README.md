# WikiDB

Knowledge wiki of the Direction du Budget: one structured sheet per public-policy measure, plus procedures, a budget
glossary and a who-does-what directory. Each bureau's material is visible only to that bureau and to the synthesis
bureaux. Agents sign in with ProConnect, and the interface follows the Système de Design de l'État (DSFR).

It is a self-hosted XWiki 17.10 LTS packaged to run without internet access. Development runs on SSPCloud with
fictitious data only; production runs on Nubonyxia, whose deployment files live in a private Forge project.

## Repository

| Path | Contents |
|---|---|
| `xwiki/` | Wiki image: the applications and DSFR skin (`app/`), the offline DSFR webjar (`dsfr/`), the default UI and offline extension package (`mainwiki/`, `xip/`), configuration and entrypoint |
| `export/` | Word and PowerPoint export service |
| `tools/wikidb/` | `wikidb` command line: provisioning, HR sync, bulk import, backups |
| `k8s/wikidb/` | Helm chart for SSPCloud |
| `tests/` | Unit tests, and acceptance tests that run against a dev wiki |
| `docs/` | Plans and operations runbooks |

## Getting started

```bash
uv venv && uv pip install -e '.[dev]'
.venv/bin/python -m pytest                                          # unit tests
tests/unit/test_entrypoint.sh                                       # entrypoint tests
cd xwiki && ./mvnw package                                          # build the offline extension package
.venv/bin/python -m pytest tests/acceptance --base-url https://<dev wiki>   # acceptance tests
```

GitHub Actions builds and publishes the wiki and export images to GHCR when their sources change on `main` or `feat/**`.

[What the wiki does](docs/capabilities.md): data model, rights, how to find information, extensions.

## Runbooks

- [Deploy and upgrade](docs/runbooks/deploy.md)
- [ProConnect sign-in](docs/runbooks/proconnect.md)
- [Add a bureau](docs/runbooks/add-a-bureau.md), [HR feed](docs/runbooks/hr-feed.md), [Import measures](docs/runbooks/import-measures.md)
- [Edit the wiki applications](docs/runbooks/editing-wiki-apps.md)
- [Backups and restore](docs/runbooks/restore.md)

## Licence

The DSFR is distributed under the Etalab 2.0 licence. Its terms of use reserve it to State services.
