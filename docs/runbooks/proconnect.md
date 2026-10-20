# ProConnect sign-in

Agents sign in with ProConnect through the OpenID Connect Authenticator, patched to send a `nonce` (KTD9). Each
platform has its own client:

| Platform | ProConnect environment | Redirect URI |
|---|---|---|
| SSPCloud (dev) | Integration (`fca.integ01.dev-agentconnect.fr`) | `https://<dev host>/oidc/authenticator/callback` |
| Nubonyxia | Integration for now, production later, both reached through the lab proxy | in `paquitopg/wikidb-rie` |

## Current status (2026-10-16)

ProConnect sign-in does not work yet on SSPCloud. On Nubonyxia it works since 2026-10-20, sign-in and logout, through
the lab proxy, with a client borrowed from another ministry application (obtained through the démarches numériques
form) until WikiDB has its own. Until it does, only the local administrator account can sign in, at
`https://<host>/bin/login/XWiki/XWikiLogin?oidc.skipped=true`.

- **Done on the wiki side.** The client ID and secret are read from the `wikidb-app` Secret, and the authorize request
  goes to Integration with the right `client_id`, redirect URI and scopes. The request also carries the `nonce` that
  ProConnect requires: the stock authenticator sends none in the code flow, so the image ships a patched one,
  `wikidb-oidc-authenticator` (KTD9, PR #5). `tests/acceptance/test_proconnect.py` checks the request.
- **Blocking.** Integration answers `invalid_client` ("client is invalid") to all three clients created so far
  (`8939fb…`, `5221a3…`, `53a98d…`), exactly as it answers a made-up `client_id`, so it does not know them. Another
  ministry application signs in on the same Integration server with a client obtained through the démarches
  numériques form ("Demande de création d'un Fournisseur de Services ProConnect", network "Internet"), not through the
  partner portal. Next step: a client requested that way, or ProConnect support with the client IDs and error IDs.
- **To check on the first real sign-in.** That the callback accepts the `nonce` in the `id_token`. That ProConnect
  accepts the PKCE parameters (`code_challenge`) the authenticator also sends: its documentation does not list them,
  and answers unknown parameters with `Y000400`. If it rejects them, make PKCE optional in the patched authenticator.
- **After that.** Integration only knows ProConnect test accounts: put the test account's email in `GroupeDirection`
  through the HR listing, or it signs in and sees nothing.

To tell an unknown client from other errors, send the same authorize request with a made-up `client_id`: an identical
`invalid_client` page means ProConnect does not know the client.

## Register a client

1. Request a client for the platform through the démarches numériques form, network "Internet", with the redirect URI
   above and the scopes `openid email given_name usual_name` (clients created in the partner portal were refused, see
   Current status). Start the production request early: it has its own lead time.
2. Store the identifiers in the `wikidb-app` Secret without echo:

   ```bash
   read -rsp "OIDC client id: " ID && echo && read -rsp "OIDC secret: " SECRET && echo
   kubectl create secret generic wikidb-app -n user-<id> --from-literal=OIDC_CLIENT_ID="$ID" \
     --from-literal=OIDC_SECRET="$SECRET" --dry-run=client -o yaml | kubectl apply -f -
   unset ID SECRET
   ```

3. Restart the pod (`kubectl rollout restart deploy/wikidb`).

## Check

- Opening the wiki redirects to ProConnect, and the authorize URL carries the real `client_id` (not
  `${env:OIDC_CLIENT_ID}`): `curl -sI https://<host>/bin/view/Main/ | grep -i location`.
- After sign-in, the user page is `XWiki.<email with every character outside [a-z0-9] replaced by ->`; this is the
  name the HR sync uses ([hr-feed.md](hr-feed.md)).
- An agent absent from the HR listing signs in but sees nothing (AE9).

## Nubonyxia

The RIE has no direct internet access, and ProConnect RIE does not accept calls from it yet. The Nubonyxia wiki
therefore uses ProConnect Integration (Internet) for now, through the lab proxy. Its host, the proxy and the redirect
URI are in the private repository `paquitopg/wikidb-rie`.

- The JVM sends every outbound call through the proxy (chart values `oidc.proxyHost`, `oidc.proxyPort`). Calls to
  `*.svc` go direct.
- The proxy filters on `User-Agent`: Java's default is refused, `curl/8.5.0` passes (`oidc.userAgent`, measured on
  2026-10-16).
- A `403` after `CONNECT` comes from the proxy, not from ProConnect. Test from the pod, then write to
  nubonyxia@finances.gouv.fr with the results.
- The client ID and secret come from the Gitlab-runner's application secrets, mounted at `/secrets/app`. On the first
  install they come from the hand-made `wikidb-app` Secret.
- Logout: register the wiki's root (`https://<host>/`) as a post-logout redirect URI on the client. The chart sets
  `oidc.afterLogoutURL` to it; ProConnect does not require a `state` on logout.
- A ProConnect `invalid_client` page means the server does not know the client: a `client_id` exists only on the
  server where it was declared (Internet or RIE, Integration or production).
- Production ProConnect will need its own client, registered as above.
