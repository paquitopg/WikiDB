# ProConnect sign-in

Agents sign in with ProConnect through the OpenID Connect Authenticator (KTD9). Each platform has its own client:

| Platform | ProConnect environment | Redirect URI |
|---|---|---|
| SSPCloud (dev) | Integration (`fca.integ01.dev-agentconnect.fr`) | `https://<dev host>/oidc/authenticator/callback` |
| Nubonyxia (production) | Production, reached through the lab proxy | in the private Forge project |

## Register a client

1. Request a client from the ProConnect partner portal for the platform, with the redirect URI above and the scopes
   `openid email given_name usual_name`. Start the production request early: it has its own lead time.
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

On Nubonyxia, the JVM reaches ProConnect through the lab proxy with the `User-Agent` recorded by the feasibility
probe (chart values `oidc.proxyHost`, `oidc.proxyPort`, `oidc.userAgent`).
