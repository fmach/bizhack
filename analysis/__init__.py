"""Water flow time-series statistical and trend analysis package."""

from analysis.analyzer import AnalysisRecord, analyze_series
from analysis.exporter import CSV_COLUMNS, export_results_csv
from analysis.loader import LoadedSeries, load_series, parse_flow_to_liters, resolve_series_path

__all__ = [
    "AnalysisRecord",
    "CSV_COLUMNS",
    "LoadedSeries",
    "analyze_series",
    "export_results_csv",
    "load_series",
    "parse_flow_to_liters",
    "resolve_series_path",
]
