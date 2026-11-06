# Kept for existing shortcuts; same as "timo --watch".
import sys

from timo.cli import main

ARGV = ["--watch"]

if __name__ == "__main__":
    sys.exit(main(ARGV))
