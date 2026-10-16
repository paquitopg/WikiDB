---
title: Restyling XWiki 17 Flamingo from a wiki skin page
date: 2026-10-16
category: best-practices
module: xwiki skin (WikiDB.Code.Skin)
problem_type: best_practice
component: frontend
severity: medium
applies_when:
  - Changing the look of the wiki through WikiDB.Code.Skin or another wiki skin page inheriting Flamingo
  - Adding a stylesheet, script or head tag that must apply on every page, including the guest login page
  - Upgrading XWiki, the DSFR or the Standard flavor
  - Checking the wiki's look in a headless browser
tags: [xwiki, flamingo, skin, dsfr, css, webjar, xar, playwright]
retire_when: "An XWiki upgrade moves the skin-extension link placeholder after stylesheets.vm in Flamingo's htmlheader.vm (check that upstream file at the new xwiki-platform tag)"
---

# Restyling XWiki 17 Flamingo from a wiki skin page

## Context

The DSFR look (PRs #3 and #4) is a wiki skin page, `WikiDB.Code.Skin`, inheriting Flamingo and overriding two templates, plus a bridge stylesheet in the offline DSFR webjar. Each trap below showed up only on the deployed dev wiki, after the build and the unit tests had passed. The code comments name the resulting rules; this doc keeps the evidence and the dead ends behind them.

## Guidance

**1. The wiki preference picks the skin, not `xwiki.cfg`.** The Standard flavor's `XWiki.XWikiPreferences` sets `skin = XWiki.DefaultSkin` (read on dev through REST), and that beats `xwiki.defaultskin`. The skin is set by `wikidb provision` instead (`tools/wikidb/provision.py:143-145`). Setting it in `xwiki.cfg.overrides`, as the DSFR plan first assumed, has no effect.

**2. Stylesheets added with `$xwiki.linkx.use` load before Flamingo's.** In Flamingo's htmlheader.vm (upstream xwiki-platform 17.10.13, not in this repo), the skin-extension placeholder `<!-- com.xpn.xwiki.plugin.skinx.LinkExtensionPlugin -->` comes before `#template("stylesheets.vm")`. So `cssVariablesInit.css` and `style.css` override any rule of equal specificity, `:root` variables included. On dev this left Open Sans as the body font and Flamingo's colours on the footer. The bridge therefore prefixes every rule with `html body`, or `html:root` for variables (`xwiki/dsfr/src/main/webjar/wikidb/dsfr-bridge.css:3-4`). Flamingo also scopes top-bar rules to `#xwikimainmenu`, which the DSFR header keeps for XWiki's scripts (`xwiki/app/src/main/skin/menus_view.vm:32`). Rules there need the id in the selector, as the 360 px dropdown fix did.

**3. Ship files that every viewer needs in a webjar, not as skin-page attachments.** Guests see nothing on this wiki and the `WikiDB` space is admin-only. Webjar files are served without a page-rights check: the guest login page loads the DSFR CSS, the bridge and the favicons (acceptance tests `test_login_page_and_outsiders_get_the_dsfr_layout` and `test_head_carries_the_dsfr_favicons_and_theme_colour_for_guests_too`). The webjar takes the build revision as its version, so a release never reuses a cached stylesheet (`xwiki/dsfr/pom.xml:16-17`). The skin page itself can stay admin-only: its templates render on the server, and agents, outsiders and guests all get the DSFR layout. A code review claimed the opposite (fallback to the default skin without view right); the deployed tests contradict it.

**4. Keep templates as plain files and let the XAR plugin insert them.** `xwiki-commons-tool-xar-plugin` transformations (`xwiki/app/pom.xml:22-40`) put `INSERT_TEXT` into an object property and `INSERT_ATTACHMENT_CONTENT` into an attachment. Two facts from the plugin's `XARMojo` at xwiki-commons 17.10.0:
- the target `<attachment>` must already contain a `<filesize>` element, because the plugin sets it without a null check (`xwiki/app/src/main/resources/WikiDB/Code/Skin.xml:25`);
- a transformation whose XPath matches nothing is skipped silently, so check the built XAR, not the source.

Templates the `XWiki.XWikiSkins` class has no field for (only `style.css`, `header.vm`, `footer.vm`, `viewheader.vm`, `view.vm` and `edit.vm` have one) go in as attachments named after the template.

**5. Head tags go through `org.xwiki.platform.html.head`.** Flamingo's `meta.vm` renders that extension point inside `<head>`, after XWiki's own favicon links. A UI extension object on the skin page adds tags there with no third template override (`xwiki/app/src/main/skin/html_head.xwiki`). It cannot change attributes of `<html>`.

**6. Two misleading signals when checking an install:**
- The REST attachment listing of `WikiDB.Code.Skin` came back empty, while a direct GET of `…/attachments/menus_view.vm` returned the file.
- Pages installed by the distribution job have `superadmin` as author, not the `xwiki:XWiki.Admin` written in the XAR.

## Why This Matters

Each trap fails silently: the build passes, the XAR installs, and the page simply keeps Flamingo's look, or keeps it only for some viewers. Traps 1 and 2 cost two deploy rounds in this session before the cause was found by listing `<head>` in order and reading the preferences through REST.

## When to Apply

Any change to `xwiki/app/src/main/skin/`, `xwiki/dsfr/src/main/webjar/`, `WikiDB.Code.Skin` or the skin preference. Re-read trap 2 and diff `htmlheader.vm`, `menus_view.vm` and `footer.vm` on every XWiki upgrade (`docs/runbooks/deploy.md`, "DSFR skin").

## Examples

Checking the look in a headless browser: XWiki with the OIDC authenticator answers an unauthenticated request with a redirect to ProConnect, not a 401, so Playwright's `http_credentials` never send the password. Send the header preemptively, on the wiki's host only, so it cannot reach ProConnect:

```python
def authenticate(route):
    if urlsplit(route.request.url).netloc == wiki_host:
        route.continue_(headers={**route.request.headers, "authorization": f"Basic {token}"})
    else:
        route.continue_()

context.route("**/*", authenticate)
```

The same route can `route.fulfill(path=local_css)` for the bridge stylesheet's URL. That way you can try CSS against the deployed wiki without a CI build per change.

Listing the order of stylesheets in `<head>` is what showed trap 2:

```python
head = html[:html.index("</head>")]
for m in re.finditer(r'<link\b[^>]*rel=.stylesheet[^>]*>|<style\b[^>]*>', head):
    print(m.start(), re.search(r'href="([^"]+)"', m.group(0)))
```
