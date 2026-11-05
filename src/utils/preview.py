import sys
import json
import os

from utils import generate_otp  # run as a script, so utils.py is a sibling module

# ANSI colors
RESET = "\033[0m"
RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
BOLD = "\033[1m"

def get_color(seconds):
    if seconds > 20:
        return GREEN
    elif seconds > 10:
        return YELLOW
    else:
        return RED

script_dir = os.path.dirname(os.path.abspath(__file__))
json_path = os.path.abspath(os.path.join(script_dir, "../../json/secrets.json"))

with open(json_path, "r") as f:
    accounts = json.load(f)

# fzf passes the account's index in secrets.json, so duplicate labels resolve correctly
try:
    acc = accounts[int(sys.argv[1])]
except (IndexError, ValueError):
    sys.exit(0)

code, seconds_left = generate_otp(acc)
color = get_color(seconds_left)

print(f"{BOLD}Code:{RESET} {color}{code}{RESET} - {BOLD}Expires in:{RESET} {color}{seconds_left} seconds{RESET}")
