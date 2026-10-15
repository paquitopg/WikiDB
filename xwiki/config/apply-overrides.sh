#!/bin/bash
# Apply "key=value" override lines to an XWiki configuration file: replace the key when it is present (commented or
# not), append it otherwise. Comment and blank lines in the overrides file are ignored.
# usage: apply-overrides.sh <target-file> <overrides-file>
set -euo pipefail

target="$1"
overrides="$2"

while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" || "$line" == \#* ]] && continue
  key="${line%%=*}"
  # Literal match on the key: escape regex metacharacters (dots in XWiki keys).
  key_re="$(printf '%s' "$key" | sed -e 's/[][\.*^$/]/\\&/g')"
  if grep -qE "^#? ?${key_re} ?=" "$target"; then
    tmp="$(mktemp)"
    awk -v re="^#? ?${key_re} ?=" -v repl="$line" '!done && $0 ~ re { print repl; done=1; next } { print }' \
      "$target" > "$tmp"
    cat "$tmp" > "$target"
    rm -f "$tmp"
  else
    printf '%s\n' "$line" >> "$target"
  fi
done < "$overrides"
