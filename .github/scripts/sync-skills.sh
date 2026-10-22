#!/usr/bin/env bash
# Copies each skill in .github/skill-sources.txt from where its product
# serves it into skills/<name>. A skill whose fetch fails, or that comes
# back without a SKILL.md named after it, is left as it was.
set -euo pipefail

root="$(cd "$(dirname "$0")/../.." && pwd)"

while read -r name base || [[ -n "${name:-}" ]]; do
  [[ -z "${name:-}" || "$name" == \#* ]] && continue

  if [[ ! "$name" =~ ^[a-z0-9][a-z0-9-]*$ || -z "${base:-}" ]]; then
    echo "Can't read the line for '$name' in skill-sources.txt" >&2
    exit 1
  fi

  staging="$(mktemp -d)"
  trap 'rm -rf "$staging"' EXIT

  curl -fsSL --retry 3 "$base/files.txt" -o "$staging/files.txt"

  while IFS= read -r path || [[ -n "$path" ]]; do
    [[ -z "$path" ]] && continue

    if [[ ! "$path" =~ ^[A-Za-z0-9._/-]+$ || "$path" == /* || "$path" == *..* ]]; then
      echo "$name: refusing the path '$path'" >&2
      exit 1
    fi

    mkdir -p "$staging/skill/$(dirname "$path")"
    curl -fsSL --retry 3 "$base/$path" -o "$staging/skill/$path"
  done < "$staging/files.txt"

  if [[ ! -s "$staging/skill/SKILL.md" ]] || ! grep -qx "name: $name" "$staging/skill/SKILL.md"; then
    echo "$name: SKILL.md is missing or isn't named '$name'" >&2
    exit 1
  fi

  mkdir -p "$root/skills/$name"
  rsync -a --delete "$staging/skill/" "$root/skills/$name/"
  echo "$name: $(grep -c . "$staging/files.txt") files from $base"

  rm -rf "$staging"
  trap - EXIT
done < "$root/.github/skill-sources.txt"
