# Edit the wiki applications

The applications (measure sheets, procedures, glossary, who-does-what, templates, export data) are XWiki pages
versioned in `xwiki/app/src/main/resources/` and shipped in the image (KTD3). Pages edited directly on a wiki are
overwritten or merged at the next upgrade, so changes go through the repository.

1. Edit the page XML in the repository (or edit on the **dev** wiki, export the page as XAR from the administration,
   and copy the XML back).
2. `cd xwiki && ./mvnw -q -pl app package` checks the XML format (`xar:verify` runs in the build).
3. To try a change on dev before the image build, import only the spaces you changed (a REST import replaces pages
   wholesale, so never import `WikiDB.Bureaux`, which holds the registry's objects), then rerun
   `wikidb provision`.
4. Run the acceptance suite on dev, commit, push, wait for CI, and deploy the new digest ([deploy.md](deploy.md)).

Velocity pitfalls met so far:

- A method call on a string literal (`"$!x".trim()`) is a parse error; use `$stringtool.trim("$!x")`.
- `##` starts a Velocity comment, even inside wiki monospace; use `{{{verbatim}}}`.
- Leave a blank line before `{{html}}` when text precedes it, or the macro renders inline and fails.
- The request parameter `sheet` is reserved by XWiki (it chooses a display sheet).
- A sheet page must have an empty title, or every page using it shows the sheet's title.
