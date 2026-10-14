#!/bin/bash
# WikiDB wrapper around the official XWiki entrypoint.
# 1. Secrets: read each setting from the environment, otherwise from /secrets/app/<NAME> (KTD11).
# 2. Extensions: seed the bundled offline repository into the permanent directory (KTD3).
# 3. Superadmin: enabled only when SUPERADMIN_PASSWORD is provided, for the one-off bootstrap (U4).
set -euo pipefail

SECRETS_DIR="${SECRETS_DIR:-/secrets/app}"
BUNDLED_REPOSITORY="${BUNDLED_REPOSITORY:-/usr/local/wikidb/extension-repository}"
PERMANENT_DIR="${PERMANENT_DIR:-/usr/local/xwiki/data}"
WEBINF="${WEBINF:-/usr/local/tomcat/webapps/ROOT/WEB-INF}"

# Point the official entrypoint's NAME_FILE convention at the mounted secret when NAME is unset.
for name in DB_USER DB_PASSWORD DB_HOST DB_PORT DB_DATABASE; do
  file_var="${name}_FILE"
  if [[ -z "${!name:-}" && -z "${!file_var:-}" && -f "$SECRETS_DIR/$name" ]]; then
    export "$file_var=$SECRETS_DIR/$name"
  fi
done

# Values XWiki reads through ${env:...}: export them from the mounted file when unset.
for name in OIDC_CLIENT_ID OIDC_SECRET SUPERADMIN_PASSWORD; do
  if [[ -z "${!name:-}" && -f "$SECRETS_DIR/$name" ]]; then
    value="$(< "$SECRETS_DIR/$name")"
    export "$name=${value%$'\n'}"
  fi
done

# Copy every bundled extension the permanent directory does not have yet; never overwrite what is there.
if [[ -d "$BUNDLED_REPOSITORY" ]]; then
  target="$PERMANENT_DIR/extension/repository"
  (cd "$BUNDLED_REPOSITORY" && find . -type f -print0) | while IFS= read -r -d '' file; do
    if [[ ! -e "$target/$file" ]]; then
      mkdir -p "$(dirname "$target/$file")"
      cp -p "$BUNDLED_REPOSITORY/$file" "$target/$file"
    fi
  done
fi

# xwiki.cfg has no variable substitution, so the bootstrap superadmin password is written here, and removed again
# as soon as the variable is gone.
if [[ -f "$WEBINF/xwiki.cfg" ]]; then
  sed -i '/^xwiki\.superadminpassword=/d' "$WEBINF/xwiki.cfg"
  if [[ -n "${SUPERADMIN_PASSWORD:-}" ]]; then
    printf 'xwiki.superadminpassword=%s\n' "$SUPERADMIN_PASSWORD" >> "$WEBINF/xwiki.cfg"
  fi
fi
unset SUPERADMIN_PASSWORD

exec /usr/local/bin/docker-entrypoint.sh "$@"
