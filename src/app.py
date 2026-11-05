import sys
import os
import subprocess
import pyperclip
import shutil

from utils.utils import load_accounts, generate_otp, fzf_args
from utils.commands import handle_commands

env_user = os.environ.get("SUDO_USER") or os.environ.get("USER")
user_home = os.path.expanduser(f"~{env_user}") if env_user else os.path.expanduser("~")

fzf_env = os.environ.get("FZF_PATH")
fallback_fzf = os.path.join(user_home, ".fzf/bin")
FZF_PATH = fzf_env or fallback_fzf

# check if fzf is installed
if shutil.which("fzf") is None:
    os.environ["PATH"] += os.pathsep + FZF_PATH
    if shutil.which("fzf") is None:
        print("fzf not found in PATH.")
        print("If you don't have it, install it with:")
        print("   sudo apt install fzf            # Debian/Ubuntu")
        print("   brew install fzf                # macOS (Homebrew)")
        print("If you already have it, export its path:")
        print("   export FZF_PATH=$(dirname $(which fzf))")
        sys.exit(1)

def set_terminal_title(title):
    sys.stdout.write(f"\33]0;{title}\a")
    sys.stdout.flush()

set_terminal_title("TOTP CLI - Terminal One-Time Password")

# === Paths ===
script_dir = os.path.dirname(os.path.abspath(__file__))
json_path = os.path.join(script_dir, "../json/secrets.json")
backup_dir = os.path.join(script_dir, "../json/backups")
preview_script = os.path.join(script_dir, "utils/preview.py")
python_path = os.path.join(script_dir, "../env/bin/python")

if not os.path.exists(json_path) and '--initialize' not in sys.argv:
    print("\nNo secrets.json found. Initialize it with:")
    print("  otpcli --initialize")
    sys.exit(1)

accounts = load_accounts(json_path)

handle_commands(sys.argv, accounts, json_path, backup_dir, script_dir)

# === Filter accounts by args ===
# keep each account's position in secrets.json so duplicate labels stay distinct
query = [q.lower() for q in sys.argv[1:] if not q.startswith("--")]
filtered = [
    (i, acc) for i, acc in enumerate(accounts)
    if all(q in f"{acc['issuer']} {acc['name']}".lower() for q in query)
]

if not filtered:
    print("No matching accounts found.")
    sys.exit(1)

if len(filtered) == 1:
    _, acc = filtered[0]
    label = f"{acc['issuer']} ({acc['name']})"
    code, remaining = generate_otp(acc)
    pyperclip.copy(code)
    print(f"\nOTP code for {label}: {code}")
    print(f"Valid for another {remaining} seconds (copied to clipboard)")
    sys.exit(0)

# === fzf interactive ===
# each line is "<index>\t<label>"; fzf shows and searches only the label
choices = [f"{i}\t{acc['issuer']} ({acc['name']})" for i, acc in filtered]

fzf_command = fzf_args(python_path, preview_script)

try:
    fzf = subprocess.run(
        fzf_command,
        input="\n".join(choices),
        text=True,
        capture_output=True,
        check=True
    )
except subprocess.CalledProcessError:
    print("No selection made.")
    sys.exit(1)

index_str, _, selected = fzf.stdout.rstrip("\n").partition("\t")
try:
    match = accounts[int(index_str)]
except (ValueError, IndexError):
    print("Account not found.")
    sys.exit(1)

code, remaining = generate_otp(match)
pyperclip.copy(code)
print(f"\nOTP code for {selected}: {code}")
print(f"Valid for another {remaining} seconds (copied to clipboard)")
