# Add a bureau

A bureau exists once it is registered and provisioned. Provisioning creates its group, its spaces and their rights,
and its who-does-what page (KTD6, KTD7). It never deletes anything.

1. As an administrator, open `WikiDB.Bureaux` and edit it with the object editor: add a **Bureau** object with its
   code (letters and digits only, e.g. `6BCS`), its name, and its type (sectoriel or de synthèse).
2. Run `wikidb provision` (settings from the environment or `/secrets/app`: `WIKIDB_URL`, `WIKIDB_ROBOT_USER`,
   `WIKIDB_ROBOT_PASSWORD`). It prints each change; a second run prints `no change`.
3. Add the bureau's agents to the HR listing ([hr-feed.md](hr-feed.md)); the next sync fills `Groupe<code>`.
4. Seed its measure sheets from its existing list ([import-measures.md](import-measures.md)), then let its champion
   complete them before the bureau's group is opened (R19).

Changing a bureau's type moves its group in or out of `GroupeSynthese` on the next provision. A bureau removed from
the registry keeps its spaces; provision lists them as orphans.

## Champion walkthrough

Run once with each pilot bureau's champion and note the date and remarks here.

1. **Fiches mesures:** "Nouvelle fiche", fill the fields, add two provenance blocks, link a sender to its
   who-does-what entry, check the completeness banner, export to Word and PowerPoint, filter the listing on the bureau.
2. **Procédures:** in `Procedures.<code>`, "Créer" with the "Fiche procédure" template, fill it, set the review date.
3. **Glossaire:** add a term, then cite it from a page with the link shown on the term's page.
4. **Qui fait quoi:** complete the bureau's page under `Annuaire.Bureaux.<code>`.
5. **Modèles et diagrammes:** in `Bureaux.<code>`, create meeting minutes from the template and insert a diagram.

| Date | Bureau | Champion | Remarks |
|---|---|---|---|
| | | | |
