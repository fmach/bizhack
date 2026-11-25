"""Module entrypoint for `python3 -m analysis`."""

import sys

from analysis.cli import main

if __name__ == "__main__":
    sys.exit(main())
