"""Data loading and normalization for repository water flow time series."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

_VALUE_PATTERN = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*([a-zA-Z]+)?\s*$")
_TIMESTAMP_FORMATS = (
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%d. %m. %Y %H:%M:%S",
    "%d. %m. %Y %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
)


@dataclass(frozen=True)
class LoadedSeries:
    """Container for a parsed and normalized time series."""

    name: str
    source_path: Path
    encoding: str
    data: pd.DataFrame
    value_columns: tuple[str, ...]


def resolve_series_path(series: str, data_dir: Path | str = "data") -> tuple[str, Path]:
    """Resolve a series name (e.g. 'series-1') or CSV path to (series_name, path)."""
    candidate = Path(series)
    if candidate.is_file():
        name = candidate.parent.name if candidate.name.lower() == "data.csv" else candidate.stem
        return name, candidate.resolve()

    if candidate.is_dir() and (candidate / "data.csv").is_file():
        return candidate.name, (candidate / "data.csv").resolve()

    base_dir = Path(data_dir)
    named_csv = base_dir / series / "data.csv"
    if named_csv.is_file():
        return series, named_csv.resolve()

    direct_csv = base_dir / series
    if direct_csv.is_file():
        name = direct_csv.parent.name if direct_csv.name.lower() == "data.csv" else direct_csv.stem
        return name, direct_csv.resolve()

    available = sorted(
        p.parent.name for p in base_dir.glob("*/data.csv") if p.is_file()
    ) if base_dir.is_dir() else []
    hint = f" Available series in '{base_dir}': {', '.join(available)}." if available else ""
    raise FileNotFoundError(f"Could not locate time series '{series}'.{hint}")


def detect_encoding(raw_bytes: bytes) -> str:
    """Detect UTF-16 BOM vs UTF-8 encoding from raw file bytes."""
    if raw_bytes.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    return "utf-8"


def parse_flow_to_liters(raw_value: str) -> float:
    """Parse a unit-suffixed flow string ('10 l', '5.30 L', '300 mL') into liters."""
    cleaned = raw_value.strip()
    if not cleaned:
        return np.nan

    match = _VALUE_PATTERN.match(cleaned)
    if not match:
        raise ValueError(f"Unrecognized flow value format: {raw_value!r}")

    numeric_value = float(match.group(1))
    unit = (match.group(2) or "l").lower()

    if unit == "l":
        return numeric_value
    if unit == "ml":
        return numeric_value / 1000.0
    if unit == "kl":
        return numeric_value * 1000.0

    raise ValueError(f"Unsupported flow unit {unit!r} in value {raw_value!r}")


def _parse_timestamps(raw_timestamps: list[str]) -> pd.DatetimeIndex:
    """Parse repository timestamps while avoiding month/day ambiguity."""
    series = pd.Series(raw_timestamps, dtype="object")
    for fmt in _TIMESTAMP_FORMATS:
        parsed = pd.to_datetime(series, format=fmt, errors="coerce")
        if parsed.notna().all():
            return pd.DatetimeIndex(parsed, name="Timestamp")

    parsed = pd.to_datetime(series, dayfirst=True, format="mixed", errors="raise")
    return pd.DatetimeIndex(parsed, name="Timestamp")


def load_series(series: str, data_dir: Path | str = "data") -> LoadedSeries:
    """Load, decode, and normalize a repository water flow CSV into a DataFrame.

    All flow columns are converted to liters (float) with empty fields as NaN,
    trailing empty columns stripped, and rows sorted by Timestamp.
    """
    series_name, csv_path = resolve_series_path(series, data_dir=data_dir)
    raw_bytes = csv_path.read_bytes()
    encoding = detect_encoding(raw_bytes)
    text = raw_bytes.decode(encoding)

    reader = csv.reader(io.StringIO(text))
    try:
        raw_header = next(reader)
    except StopIteration as exc:
        raise ValueError(f"CSV file '{csv_path}' is empty.") from exc

    keep_indices = [idx for idx, col in enumerate(raw_header) if col.strip() != ""]
    headers = [raw_header[idx].strip() for idx in keep_indices]
    if len(headers) < 2:
        raise ValueError(f"CSV file '{csv_path}' must have at least a timestamp and one value column.")

    ts_col_idx = 0
    for idx, col in enumerate(headers):
        if col.lower() == "timestamp":
            ts_col_idx = idx
            break

    value_col_positions = [idx for idx in range(len(headers)) if idx != ts_col_idx]
    value_columns = tuple(headers[idx] for idx in value_col_positions)

    raw_timestamps: list[str] = []
    parsed_columns: dict[str, list[float]] = {col: [] for col in value_columns}

    for row in reader:
        if not row or all(cell.strip() == "" for cell in row):
            continue
        selected = [row[idx] if idx < len(row) else "" for idx in keep_indices]
        raw_timestamps.append(selected[ts_col_idx].strip())
        for pos, col_name in zip(value_col_positions, value_columns):
            parsed_columns[col_name].append(parse_flow_to_liters(selected[pos]))

    if not raw_timestamps:
        raise ValueError(f"CSV file '{csv_path}' contains no data rows.")

    index = _parse_timestamps(raw_timestamps)
    df = pd.DataFrame(parsed_columns, index=index, dtype="float64")
    df = df.sort_index()

    return LoadedSeries(
        name=series_name,
        source_path=csv_path,
        encoding=encoding,
        data=df,
        value_columns=value_columns,
    )
