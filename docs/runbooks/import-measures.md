# Import a bureau's measures

`wikidb import` creates skeleton measure sheets from an existing list (R18, F4). It validates every row before
writing anything, and is a dry run unless `--apply` is given.

## Input file

CSV (UTF-8, comma or semicolon) or XLSX, one row per measure. Column names (accents and case are ignored):

| Column | Required | Content |
|---|---|---|
| `bureau` | yes | registered bureau code |
| `perimetre` | yes | `secteur` or `synthese` |
| `intitule` | yes | the measure's usual name (becomes the page title) |
| `cle_source` | yes | the measure's identifier in the source list, unique in the file |
| `date_creation` | no | jj/mm/aaaa |
| `vecteur_juridique`, `raison_etre`, `modalites_modification`, `documentation_interne`, `documentation_externe` | no | text |

## Steps

1. `wikidb import mesures.xlsx` and read the plan: `create`, `fill` (empty fields of an existing sheet) or `unchanged`.
   Any invalid row stops the import with the list of problems; nothing is written.
2. `wikidb import mesures.xlsx --apply`.
3. Re-running with a corrected file is safe: the source key finds the existing sheet, and only fields still empty are
   filled. A field a champion already wrote is never overwritten.

Real lists are imported on Nubonyxia only; SSPCloud uses fictitious data (R20).
