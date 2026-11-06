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

export TIMO_PASSPHRASE="demo-passphrase"
export PATH="$(cd "$timo_bin" && pwd):$PATH"
unset TIMO_HOME XDG_CONFIG_HOME

for tape in assets/demo/dark.tape assets/demo/light.tape; do
    # a fresh vault for each recording, since the demo adds an account; HOME (not
    # TIMO_HOME) so paths show as ~/.config/timo, like a real install
    demo_home="$(mktemp -d)"
    trap 'rm -rf "$demo_home"' EXIT
    HOME="$demo_home" "$python" assets/demo/seed.py "$demo_home/.config/timo" "$TIMO_PASSPHRASE"
    HOME="$demo_home" vhs "$tape"
    rm -rf "$demo_home"
done
