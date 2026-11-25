#!/usr/bin/env python3
"""CLI entrypoint for analyzing a repository water flow time series."""

import sys

from analysis.cli import main

if __name__ == "__main__":
    sys.exit(main())
