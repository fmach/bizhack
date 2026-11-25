"""Command-line interface for running time-series analysis."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from analysis.analyzer import analyze_series
from analysis.exporter import export_results_csv
from analysis.loader import load_series


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="analyze_series",
        description="Analyze statistics and trends for a selected water flow time series and export to CSV.",
    )
    parser.add_argument(
        "--series",
        required=True,
        help="Series name under --data-dir (e.g. series-1..series-5) or path to a data.csv file.",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output CSV file path (default: output/<series>_analysis.csv).",
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Base directory containing series-* subdirectories (default: data).",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress stdout summary output.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        loaded = load_series(args.series, data_dir=args.data_dir)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    records = analyze_series(loaded)
    output_path = Path(args.output) if args.output else Path("output") / f"{loaded.name}_analysis.csv"
    written_path = export_results_csv(records, output_path)

    if not args.quiet:
        print(
            f"Analyzed '{loaded.name}' ({len(loaded.data)} rows, columns={list(loaded.value_columns)}) "
            f"-> {len(records)} metrics written to {written_path}"
        )

    return 0
