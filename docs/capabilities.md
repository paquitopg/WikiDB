# What the wiki does

What WikiDB stores, who can read it, how to find it, and which extensions it ships with or could add. Written for
XWiki 17.10.13 LTS and the applications in `xwiki/app`; keep it in step when they change.

## 1. Data and storage

### 1.1 Where data lives

| Where | What |
|---|---|
| PostgreSQL (CloudNativePG) | Pages, their structured fields, attachments (`xwiki.store.attachment.hint=hibernate`), full version history, the recycle bin, users and groups |
| Volume (`/usr/local/xwiki/data`) | The installed-extension state and the Solr search index (rebuilt from the database at startup) |
| S3 buckets (Nubonyxia) | Daily HR directory listings (`listings/`), database dumps (`dumps/`: dailies 14 days, weeklies 8 weeks) |

A restore needs the database **and** the volume archive ([restore.md](runbooks/restore.md)).

### 1.2 How content is modelled

Every piece of content is a **page**. A page can carry **objects** of a **class**, a typed form definition. The
classes below are versioned in `xwiki/app/src/main/resources/` and shipped in the image.

#### Measure sheet (`Mesures.Code.MesureClass`)

One page per measure. The page name is a neutral, unique identifier (`M-0042`) given on creation; the page title is
the measure's usual name.

| Field | Type | Content |
|---|---|---|
| `cleSource` (Clé source) | short text | The measure's identifier in the bureau's source list; the import's key |
| `dateCreation` | date (dd/MM/yyyy) | |
| `vecteurJuridique` | short text | e.g. the law and article |
| `raisonEtre`, `modalitesModification`, `documentationInterne`, `documentationExterne` | rich text (WYSIWYG) | Formatting, links, tables |

**The owning bureau and the perimeter are the page's location, not fields:** `Mesures.<code>.<Secteur|Synthese>.M-NNNN`.
Rights follow from the location (section 2), and changing a sheet's perimeter means moving the page.

#### Data provenance (`Mesures.Code.ProvenanceClass`)

Any number of blocks per sheet, each with: Donnée, Émetteur, Fiche « Qui fait quoi » (a page reference that turns the
sender into a link), Fréquence (quotidienne, hebdomadaire, mensuelle, trimestrielle, semestrielle, annuelle,
ponctuelle, autre), Forme, Contact.

#### Completeness

A sheet is complete when every field except `cleSource` is filled and at least one provenance block names its data item
and its sender. The sheet shows a green or orange banner. The rule lives in `Mesures.Code.MesureMacros` and in
`tools/wikidb/measures.py`, which must stay in step.

#### Other structured pages

| Type | Location | Fields | Edited by |
|---|---|---|---|
| Fiche procédure | `Procedures.<code>` | Objet, Étapes, Calendrier, Références (rich text), Dernière revue (date) | The owning bureau |
| Terme du glossaire | `Glossaire` | Title = the term; Définition (rich text) | Every Direction agent |
| Qui fait quoi, bureau | `Annuaire.Bureaux.<code>` | Missions, Sujets suivis, Référents par sujet (rich text), Adresse fonctionnelle | The bureau |
| Qui fait quoi, external sender | `Annuaire.Externes` | Organisme, Service, Données transmises, Contact fonctionnel, Téléphone du service | Administrators |
| Bureau (registry) | `WikiDB.Bureaux` | Code, Intitulé, Type (sectoriel, de synthèse) | Administrators |

The directory holds professional contact details only.

#### Free-form content

- **Private bureau space** `Bureaux.<code>`: any pages, readable by the bureau's members only.
- **French templates** offered when creating a page in `Bureaux.*` or `Main`: Compte rendu de réunion, Note brève,
  Relevé de décision.
- **Diagrams** (draw.io-based Diagram application) drawn inside a page, offline, with that page's rights.
- **Attachments** on any page the agent can edit, versioned and stored in PostgreSQL.

#### Not modelled yet

- Figures and computed *chiffrages* (calculation engines are deferred).
- A status or validation workflow.
- Structured links between measures (only wiki links in rich text).
- Data flows shared by several measures (each sheet holds its own provenance).
- Field-level visibility.

## 2. Who sees what

### 2.1 Groups

| Group | Members | Maintained by |
|---|---|---|
| `GroupeDirection` | Every agent of the daily HR listing. A ProConnect user outside it sees nothing | `wikidb hrsync` |
| `Groupe<code>` | The agents of that bureau (`affectation` column of the listing) | `wikidb hrsync` |
| `GroupeSynthese` | The groups of the synthesis bureaux (registry type) | `wikidb provision` |
| `XWikiAdminGroup` | The robot and break-glass accounts, which sign in locally at `?oidc.skipped=true` | By hand |

### 2.2 Rights (`tools/wikidb/provision.py`)

| Area | Read | Edit |
|---|---|---|
| `Mesures.<B>.Secteur` | Bureau B and every synthesis bureau | Bureau B |
| `Mesures.<B>.Synthese` | Every Direction agent | Bureau B |
| `Bureaux.<B>` (private space) | Bureau B only, not the synthesis bureaux | Bureau B |
| `Procedures.<B>` | Every Direction agent | Bureau B |
| `Glossaire` | Every Direction agent | Every Direction agent |
| `Annuaire.Bureaux.<B>` | Every Direction agent | Bureau B |
| `Annuaire.Externes`, application homes, `Modeles`, `XWiki` | Every Direction agent | Administrators |
| `WikiDB` (registry, HR sync report) | Administrators | Administrators |
| Script code in pages | Runs only when saved by an administrator | |

An agent of the listing whose bureau is not registered reads the common area and the synthesis perimeter, and edits
the glossary only. Search, listings, links, notifications and exports never reveal a page the reader cannot read; the
acceptance suite checks it (AE1 to AE10 in the [plan](plans/2026-10-14-1629-feat-direction-budget-wiki-plan.md)).

### 2.3 Finding information

| Need | How |
|---|---|
| Every sheet of bureau X | **Fiches mesures**, *Bureau* = X, *Filtrer*; or the address `/bin/view/Mesures/?bureau=X`, with `&perimetre=Secteur` or `&perimetre=Synthese` to narrow it |
| Every synthesis-perimeter sheet | The same page, *Périmètre* = Synthèse |
| Narrow or sort the list | Column filters and sorting on Intitulé, Emplacement, Vecteur juridique, Date de création, Dernière modification, Modifiée par |
| Sheets last changed by someone | Filter the *Modifiée par* column |
| Free text across all content and attachments | The search bar (Solr), filtered by rights, with a facet on location |
| Browse | The navigation tree: Mesures, then the bureau, then Secteur or Synthese |
| Completeness | Bottom of **Fiches mesures**: complete sheets among those the reader can see. Direction-wide, per bureau and perimeter: `wikidb completeness` (administrator) |
| Changes over time | Each sheet shows its last change and author; **Historique** keeps every version, with diff and restore |
| A sheet as an Office file | **Exporter : Word \| PowerPoint** on the sheet; XWiki's own export menu also gives PDF, ODT and RTF |
| The list in a spreadsheet | **Exporter la liste (tableur)** on **Fiches mesures**: a CSV file for Excel with the current bureau and perimeter filters and every field, rich text as plain text, provenances, completeness, last change and address; only sheets the reader can view. Address: `/bin/get/Mesures/Code/ListeExport?bureau=X&perimetre=Secteur` |
| Procedures, glossary, directory | Filterable lists on their home pages |
| Programmatic access | REST API (`/rest/wikis/xwiki/spaces/Mesures/spaces/X/...`), for administrator and robot accounts: agents sign in with ProConnect and have no password |

Current limits: the bureau filter takes the code, not the name; Office exports cover one
sheet per file; rich-text fields are not list columns.

## 3. Extensions

### 3.1 Shipped

Everything is packaged in the image. Extension repositories are disabled (`extension.repositories=`), so no extension
can be installed from the administration: a new one goes through the repository, the image and a deployment.

| Extension | Role |
|---|---|
| XWiki Standard flavor 17.10.13 | WYSIWYG editor, Live Data lists, Solr search, history and diff, comments, annotations, tags, attachments, recycle bin, in-app notifications and mentions, page export, navigation tree, App Within Minutes |
| `wikidb-oidc-authenticator` (OIDC authenticator 2.28.1, patched) | ProConnect sign-in, fixed post-logout address, local administrator login |
| Diagram application 1.3.1 | draw.io diagrams in pages, offline |
| `wikidb-dsfr` | DSFR skin and assets, offline |
| `wikidb-app` | The applications above, the templates, the registry, the export data page and the list export |
| Export service (`export/`, not an XWiki extension) | Word and PowerPoint export of one sheet, with the reader's own session and rights |

### 3.2 Candidates

Ordered by value against the requirements. Compatibility with 17.10 and offline packaging are to be checked for each.

| Candidate | Brings | Cost or condition |
|---|---|---|
| Change Request (xwiki-contrib) | Review and approval before a change is published, for champions | Check its interplay with location-based rights |
| Publication Workflow (xwiki-contrib) | Draft, validated and published states | Overlaps with Change Request; choose one |
| Email notifications | Watch a sheet and receive changes by email | An SMTP relay reachable from Nubonyxia |
| Chart macro (in the flavor) and administrator scripts | First computed tables and charts, towards the *chiffrages* engines | Written by administrators as application code (script right) |
| PDF export based on headless Chrome | Better PDF rendering | A Chrome service in the namespace |
| Office server (LibreOffice) | Import Word files as pages, preview Office attachments | A much heavier image |
| Task Manager | Follow-up actions from minutes and decision records | Deferred in the plan |
| LDAP or Active Directory sync | Replaces the HR CSV feed | Deferred; the CSV feed works |
