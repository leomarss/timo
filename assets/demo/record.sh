#!/usr/bin/env bash
# Record the README demo GIFs (dark and light) with vhs: https://github.com/charmbracelet/vhs
#
#   brew install vhs
#   assets/demo/record.sh
#
# Runs on a throwaway vault with fake accounts: your secrets and keychain are never touched.
# Each recording waits for a fresh 30-second code window, so it takes about a minute.
set -euo pipefail

cd "$(dirname "$0")/../.."
python="${PYTHON:-env/bin/python}"
timo_bin="$(dirname "$python")"

demo_home="$(mktemp -d)"
trap 'rm -rf "$demo_home"' EXIT

export TIMO_HOME="$demo_home"
export TIMO_PASSPHRASE="demo-passphrase"
export PATH="$timo_bin:$PATH"
"$python" assets/demo/seed.py "$TIMO_HOME" "$TIMO_PASSPHRASE"

for tape in assets/demo/dark.tape assets/demo/light.tape; do
    vhs "$tape"
done
