"""CSV exporter for tidy time-series analysis results."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path

from analysis.analyzer import AnalysisRecord

CSV_COLUMNS = (
    "series",
    "section",
    "period",
    "series_column",
    "metric",
    "value",
    "unit",
)


def export_results_csv(records: Iterable[AnalysisRecord], output_path: Path | str) -> Path:
    """Write analysis records to a tidy UTF-8 CSV file."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with destination.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(CSV_COLUMNS)
        for rec in records:
            writer.writerow(
                (
                    rec.series,
                    rec.section,
                    rec.period,
                    rec.series_column,
                    rec.metric,
                    rec.value,
                    rec.unit,
                )
            )

    return destination.resolve()
