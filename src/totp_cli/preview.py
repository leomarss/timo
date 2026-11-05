"""fzf preview: show the code for the highlighted account.

Runs as a separate process, so it never sees the secrets or the passphrase.
otpcli hands it the upcoming codes for each account in TOTP_CLI_PREVIEW
(an environment variable, readable only by the same user), and this script
picks the one for the current 30-second window.
"""
import json
import os
import sys
import time

RESET = "\033[0m"
RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
BOLD = "\033[1m"


def get_color(seconds):
    if seconds > 20:
        return GREEN
    if seconds > 10:
        return YELLOW
    return RED


def main(argv, environ, now):
    try:
        data = json.loads(environ["TOTP_CLI_PREVIEW"])
        codes = data["codes"][argv[1]]
    except (KeyError, IndexError, ValueError):
        return ""
    window = (int(now) - data["start"]) // data["interval"]
    if not 0 <= window < len(codes):
        return "Codes expired: close and reopen otpcli."
    seconds_left = data["start"] + (window + 1) * data["interval"] - int(now)
    color = get_color(seconds_left)
    code = codes[window]
    shown = f"{code[:len(code) // 2]} {code[len(code) // 2:]}"  # 482 913, like the main output
    return (f"{BOLD}Code:{RESET} {color}{shown}{RESET} - "
            f"{BOLD}Expires in:{RESET} {color}{seconds_left} seconds{RESET}")


if __name__ == "__main__":
    print(main(sys.argv, os.environ, time.time()))
