#!/bin/bash
# Shell tests for xwiki/entrypoint-wikidb.sh and xwiki/config/apply-overrides.sh.
# Runs anywhere bash is available: the official entrypoint is replaced by a stub that records the environment.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENTRYPOINT="$ROOT/xwiki/entrypoint-wikidb.sh"
APPLY="$ROOT/xwiki/config/apply-overrides.sh"
failures=0

fail() { echo "FAIL: $*"; failures=$((failures + 1)); }
pass() { echo "ok: $*"; }

# Each test gets a sandbox with a fake secrets dir, bundled repository, permanent dir and WEB-INF.
setup() {
  SANDBOX="$(mktemp -d)"
  mkdir -p "$SANDBOX/secrets" "$SANDBOX/bundled/ext-a/1.0" "$SANDBOX/data" "$SANDBOX/webinf" "$SANDBOX/bin"
  echo "bundled-a" > "$SANDBOX/bundled/ext-a/1.0/ext-a.xed"
  printf '# xwiki.cfg\n#xwiki.superadminpassword=system\n' > "$SANDBOX/webinf/xwiki.cfg"
  # Stub of the official entrypoint: dump the environment variables we care about.
  cat > "$SANDBOX/bin/official.sh" <<'STUB'
#!/bin/bash
env | grep -E '^(DB_[A-Z_]+|OIDC_[A-Z_]+|SUPERADMIN_PASSWORD)=' | sort > "$SANDBOX_OUT"
STUB
  chmod +x "$SANDBOX/bin/official.sh"
  # The wrapper execs a fixed path; run a copy pointing at the stub.
  sed "s#/usr/local/bin/docker-entrypoint.sh#$SANDBOX/bin/official.sh#" "$ENTRYPOINT" > "$SANDBOX/bin/wrapper.sh"
  chmod +x "$SANDBOX/bin/wrapper.sh"
}

run_wrapper() {
  env -i PATH="$PATH" HOME="$SANDBOX" SANDBOX_OUT="$SANDBOX/out.env" \
    SECRETS_DIR="$SANDBOX/secrets" BUNDLED_REPOSITORY="$SANDBOX/bundled" \
    PERMANENT_DIR="$SANDBOX/data" WEBINF="$SANDBOX/webinf" "$@" "$SANDBOX/bin/wrapper.sh" xwiki
}

teardown() { rm -rf "$SANDBOX"; }

# --- secrets from files ---------------------------------------------------------------------------------------------

setup
printf 's3cret\n' > "$SANDBOX/secrets/DB_PASSWORD"
run_wrapper
if grep -qx "DB_PASSWORD_FILE=$SANDBOX/secrets/DB_PASSWORD" "$SANDBOX/out.env"; then
  pass "DB_PASSWORD unset: the official entrypoint is pointed at the mounted file"
else
  fail "DB_PASSWORD_FILE not exported from mounted secret: $(cat "$SANDBOX/out.env")"
fi
teardown

setup
printf 'from-file\n' > "$SANDBOX/secrets/DB_PASSWORD"
run_wrapper DB_PASSWORD=from-env
if grep -qx "DB_PASSWORD=from-env" "$SANDBOX/out.env" && ! grep -q "DB_PASSWORD_FILE" "$SANDBOX/out.env"; then
  pass "DB_PASSWORD set in the environment: the file is ignored"
else
  fail "environment value did not win: $(cat "$SANDBOX/out.env")"
fi
teardown

setup
printf 'client-secret\n' > "$SANDBOX/secrets/OIDC_SECRET"
run_wrapper
if grep -qx "OIDC_SECRET=client-secret" "$SANDBOX/out.env"; then
  pass "OIDC_SECRET is exported from the mounted file without its trailing newline"
else
  fail "OIDC_SECRET not exported cleanly: $(cat "$SANDBOX/out.env")"
fi
teardown

# --- extension repository seeding --------------------------------------------------------------------------------------

setup
run_wrapper
if [[ -f "$SANDBOX/data/extension/repository/ext-a/1.0/ext-a.xed" ]]; then
  pass "empty permanent directory: bundled extensions are copied"
else
  fail "bundled extension not seeded"
fi
echo "installed-state" > "$SANDBOX/data/extension/repository/ext-a/1.0/ext-a.xed"
run_wrapper
if [[ "$(cat "$SANDBOX/data/extension/repository/ext-a/1.0/ext-a.xed")" == "installed-state" ]]; then
  pass "second start: files already in the permanent directory are not overwritten"
else
  fail "existing repository entry was overwritten"
fi
mkdir -p "$SANDBOX/bundled/ext-b/2.0" && echo "bundled-b" > "$SANDBOX/bundled/ext-b/2.0/ext-b.xed"
run_wrapper
if [[ -f "$SANDBOX/data/extension/repository/ext-b/2.0/ext-b.xed" ]]; then
  pass "newer image: extensions added to the bundle are seeded on the next start"
else
  fail "new bundled extension not seeded"
fi
teardown

# --- superadmin bootstrap ----------------------------------------------------------------------------------------------

setup
run_wrapper SUPERADMIN_PASSWORD=bootstrap-pw
if grep -qx "xwiki.superadminpassword=bootstrap-pw" "$SANDBOX/webinf/xwiki.cfg" \
  && ! grep -q SUPERADMIN_PASSWORD "$SANDBOX/out.env"; then
  pass "SUPERADMIN_PASSWORD set: written to xwiki.cfg and not passed on to Tomcat's environment"
else
  fail "superadmin bootstrap not applied: $(grep superadmin "$SANDBOX/webinf/xwiki.cfg")"
fi
run_wrapper
if ! grep -q "^xwiki.superadminpassword=" "$SANDBOX/webinf/xwiki.cfg"; then
  pass "SUPERADMIN_PASSWORD gone: superadmin is disabled again"
else
  fail "superadmin password left in xwiki.cfg"
fi
teardown

# --- apply-overrides.sh ------------------------------------------------------------------------------------------------

setup
cat > "$SANDBOX/target.properties" <<'TARGET'
# Comment
#extension.repositories = maven-xwiki:maven:https://nexus.xwiki.org
distribution.job.interactive=true
other.key=keep
TARGET
cat > "$SANDBOX/overrides" <<'OVR'
# ignored comment

extension.repositories=
distribution.job.interactive=false
oidc.clientid=${env:OIDC_CLIENT_ID}
OVR
"$APPLY" "$SANDBOX/target.properties" "$SANDBOX/overrides"
expected="# Comment
extension.repositories=
distribution.job.interactive=false
other.key=keep
oidc.clientid=\${env:OIDC_CLIENT_ID}"
if [[ "$(cat "$SANDBOX/target.properties")" == "$expected" ]]; then
  pass "apply-overrides replaces commented and active keys, appends new ones, keeps the rest"
else
  fail "apply-overrides result unexpected:"; cat "$SANDBOX/target.properties"
fi
teardown

echo
if (( failures > 0 )); then echo "$failures failure(s)"; exit 1; fi
echo "all passed"
