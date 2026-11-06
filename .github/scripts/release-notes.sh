#!/usr/bin/env bash
# Print the CHANGELOG.md section of one version, for its GitHub release.
#
#   .github/scripts/release-notes.sh 1.0.3
#
# Exits with an error when the version has no section or the section is empty.
set -euo pipefail

version="${1#v}"
notes="$(awk -v v="$version" '
    /^## \[/ { if (on) exit; on = index($0, "## [" v "]") == 1; next }
    /^\[[^]]+\]: / { if (on) exit }
    on
' "$(dirname "$0")/../../CHANGELOG.md")"

# drop leading and trailing blank lines
notes="$(printf '%s\n' "$notes" | sed -e '/./,$!d')"
if [ -z "$notes" ]; then
    echo "CHANGELOG.md has no notes for $version: add a '## [$version] - YYYY-MM-DD' section" >&2
    exit 1
fi

printf '%s\n\nUpgrade with `pipx upgrade timo-otp`.\n' "$notes"
