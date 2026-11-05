# Kept for existing shortcuts; same as "otpcli --watch".
import sys

from totp_cli.cli import main

ARGV = ["--watch"]

if __name__ == "__main__":
    sys.exit(main(ARGV))
