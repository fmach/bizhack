"""Unit and integration tests for the analysis package."""

from __future__ import annotations

import csv
import math
import tempfile
import unittest
import warnings
from pathlib import Path

import pandas as pd

from analysis import (
    CSV_COLUMNS,
    LoadedSeries,
    analyze_series,
    export_results_csv,
    load_series,
    parse_flow_to_liters,
)
from analysis.cli import main as cli_main

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

EXPECTED_SECTIONS = {
    "data_quality",
    "overall_stats",
    "overall_trend",
    "diurnal_profile",
    "daily_stats",
    "daily_trend",
    "week_stats",
    "month_stats",
    "year_stats",
}


def _index_records(records):
    return {
        (r.section, r.period, r.series_column, r.metric): r.value
        for r in records
    }


def _make_loaded_series(name: str, timestamps: list[str], values: list[float]) -> LoadedSeries:
    idx = pd.DatetimeIndex(pd.to_datetime(timestamps), name="Timestamp")
    df = pd.DataFrame({"Flow": values}, index=idx, dtype="float64")
    return LoadedSeries(
        name=name,
        source_path=Path(f"{name}.csv"),
        encoding="utf-8",
        data=df,
        value_columns=("Flow",),
    )


class TestLoader(unittest.TestCase):
    def test_parse_flow_to_liters(self) -> None:
        self.assertEqual(parse_flow_to_liters("10 l"), 10.0)
        self.assertEqual(parse_flow_to_liters("5.30 L"), 5.3)
        self.assertAlmostEqual(parse_flow_to_liters("300 mL"), 0.3)
        self.assertAlmostEqual(parse_flow_to_liters("200 ml"), 0.2)
        self.assertEqual(parse_flow_to_liters("0 L"), 0.0)
        self.assertTrue(math.isnan(parse_flow_to_liters("")))
        self.assertTrue(math.isnan(parse_flow_to_liters("   ")))
        with self.assertRaises(ValueError):
            parse_flow_to_liters("15 gal")

    def test_load_all_repository_series(self) -> None:
        expected = {
            "series-1": ("utf-16", 5759, ("Flow", "Subflow")),
            "series-2": ("utf-16", 7200, ("Flow",)),
            "series-3": ("utf-8", 7199, ("Flow",)),
            "series-4": ("utf-8", 14378, ("Flow",)),
            "series-5": ("utf-8", 9870, ("Flow",)),
        }
        for name, (enc, rows, cols) in expected.items():
            loaded = load_series(name, data_dir=DATA_DIR)
            self.assertEqual(loaded.name, name)
            self.assertEqual(loaded.encoding, enc)
            self.assertEqual(len(loaded.data), rows)
            self.assertEqual(loaded.value_columns, cols)
            self.assertTrue(loaded.data.index.is_monotonic_increasing)

        # Verify series-1 empty Subflow cells and trailing comma handling
        s1 = load_series("series-1", data_dir=DATA_DIR)
        self.assertEqual(int(s1.data["Flow"].isna().sum()), 0)
        self.assertEqual(int(s1.data["Subflow"].isna().sum()), 2)

        # Verify series-3 mL conversion (04.01.2000 14:28:00 -> 200 mL = 0.2 L)
        s3 = load_series("series-3", data_dir=DATA_DIR)
        self.assertAlmostEqual(float(s3.data.loc[pd.Timestamp("2000-01-04 14:28:00"), "Flow"]), 0.2)

        # Verify series-4 decimal L and mL conversion
        s4 = load_series("series-4", data_dir=DATA_DIR)
        self.assertAlmostEqual(float(s4.data.loc[pd.Timestamp("2000-01-01 07:53:00"), "Flow"]), 5.3)
        self.assertAlmostEqual(float(s4.data.loc[pd.Timestamp("2000-01-01 10:04:00"), "Flow"]), 0.3)

    def test_load_by_explicit_csv_path(self) -> None:
        csv_path = DATA_DIR / "series-3" / "data.csv"
        loaded = load_series(str(csv_path))
        self.assertEqual(loaded.name, "series-3")
        self.assertEqual(len(loaded.data), 7199)

    def test_missing_series_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            load_series("series-999", data_dir=DATA_DIR)


class TestAnalyzerSynthetic(unittest.TestCase):
    def test_upward_trend_and_descriptive_stats(self) -> None:
        # 48 hourly points: y = 10 + 2 * hour
        timestamps = pd.date_range("2024-01-01 00:00:00", periods=48, freq="1h")
        values = [10.0 + 2.0 * h for h in range(48)]
        loaded = _make_loaded_series("upward", [t.isoformat() for t in timestamps], values)

        records = analyze_series(loaded)
        lookup = _index_records(records)

        self.assertEqual(lookup[("overall_stats", "all", "Flow", "count")], 48)
        self.assertAlmostEqual(lookup[("overall_stats", "all", "Flow", "total_volume")], sum(values), places=4)
        self.assertAlmostEqual(lookup[("overall_stats", "all", "Flow", "mean")], 57.0, places=4)
        self.assertAlmostEqual(lookup[("overall_stats", "all", "Flow", "min")], 10.0, places=4)
        self.assertAlmostEqual(lookup[("overall_stats", "all", "Flow", "max")], 104.0, places=4)
        self.assertAlmostEqual(lookup[("overall_stats", "all", "Flow", "nonzero_ratio")], 100.0, places=4)

        self.assertAlmostEqual(lookup[("overall_trend", "all", "Flow", "hourly_ols_slope")], 2.0, places=5)
        self.assertAlmostEqual(lookup[("overall_trend", "all", "Flow", "hourly_ols_r_squared")], 1.0, places=5)
        self.assertEqual(lookup[("overall_trend", "all", "Flow", "hourly_ols_trend_direction")], "increasing")
        self.assertAlmostEqual(lookup[("overall_trend", "all", "Flow", "hourly_theil_sen_slope")], 2.0, places=5)
        self.assertAlmostEqual(lookup[("overall_trend", "all", "Flow", "hourly_kendall_tau")], 1.0, places=5)
        self.assertEqual(lookup[("overall_trend", "all", "Flow", "hourly_kendall_trend_direction")], "increasing")
        self.assertAlmostEqual(lookup[("overall_trend", "all", "Flow", "hourly_spearman_rho")], 1.0, places=5)

    def test_downward_trend(self) -> None:
        timestamps = pd.date_range("2024-01-01 00:00:00", periods=48, freq="1h")
        values = [100.0 - 1.5 * h for h in range(48)]
        loaded = _make_loaded_series("downward", [t.isoformat() for t in timestamps], values)

        lookup = _index_records(analyze_series(loaded))
        self.assertAlmostEqual(lookup[("overall_trend", "all", "Flow", "hourly_ols_slope")], -1.5, places=5)
        self.assertEqual(lookup[("overall_trend", "all", "Flow", "hourly_ols_trend_direction")], "decreasing")
        self.assertEqual(lookup[("overall_trend", "all", "Flow", "hourly_kendall_trend_direction")], "decreasing")

    def test_flat_series_emits_no_warnings(self) -> None:
        timestamps = pd.date_range("2024-01-01 00:00:00", periods=48, freq="1h")
        values = [5.0] * 48
        loaded = _make_loaded_series("flat", [t.isoformat() for t in timestamps], values)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            records = analyze_series(loaded)

        self.assertEqual(caught, [])
        lookup = _index_records(records)
        self.assertEqual(lookup[("overall_trend", "all", "Flow", "hourly_ols_slope")], 0.0)
        self.assertEqual(lookup[("overall_trend", "all", "Flow", "hourly_ols_trend_direction")], "no_significant_trend")
        self.assertEqual(lookup[("overall_trend", "all", "Flow", "hourly_kendall_trend_direction")], "no_significant_trend")

    def test_week_month_year_period_boundaries_and_deltas(self) -> None:
        # Spans 2024-12-30 (Mon, 2025-W01), 2024-12-31, 2025-01-01, 2025-01-06 (Mon, 2025-W02), 2025-02-01
        points = [
            ("2024-12-30 01:00:00", 10.0),
            ("2024-12-30 12:00:00", 20.0),
            ("2024-12-31 12:00:00", 30.0),
            ("2025-01-01 12:00:00", 40.0),
            ("2025-01-06 12:00:00", 100.0),
            ("2025-01-06 13:00:00", 100.0),
            ("2025-02-01 12:00:00", 120.0),
        ]
        loaded = _make_loaded_series(
            "multi-period",
            [p[0] for p in points],
            [p[1] for p in points],
        )
        records = analyze_series(loaded)
        lookup = _index_records(records)

        # Data quality coverage counts
        self.assertEqual(lookup[("data_quality", "all", "all", "days_covered")], 5)
        self.assertEqual(lookup[("data_quality", "all", "all", "weeks_covered")], 3)
        self.assertEqual(lookup[("data_quality", "all", "all", "months_covered")], 3)
        self.assertEqual(lookup[("data_quality", "all", "all", "years_covered")], 2)

        # week_stats: 2025-W01 (Dec 30, Dec 31, Jan 1 -> 10+20+30+40 = 100), 2025-W02 (Jan 6 -> 200), 2025-W05 (Feb 1 -> 120)
        self.assertAlmostEqual(lookup[("week_stats", "2025-W01", "Flow", "total_volume")], 100.0)
        self.assertEqual(lookup[("week_stats", "2025-W01", "Flow", "days_covered")], 3)
        self.assertAlmostEqual(lookup[("week_stats", "2025-W02", "Flow", "total_volume")], 200.0)
        self.assertAlmostEqual(lookup[("week_stats", "2025-W02", "Flow", "week_over_week_volume_delta")], 100.0)
        self.assertAlmostEqual(lookup[("week_stats", "2025-W02", "Flow", "week_over_week_volume_change_pct")], 100.0)
        self.assertAlmostEqual(lookup[("week_stats", "2025-W05", "Flow", "total_volume")], 120.0)

        # month_stats: 2024-12 (60), 2025-01 (240), 2025-02 (120)
        self.assertAlmostEqual(lookup[("month_stats", "2024-12", "Flow", "total_volume")], 60.0)
        self.assertAlmostEqual(lookup[("month_stats", "2025-01", "Flow", "total_volume")], 240.0)
        self.assertAlmostEqual(lookup[("month_stats", "2025-01", "Flow", "month_over_month_volume_delta")], 180.0)
        self.assertAlmostEqual(lookup[("month_stats", "2025-01", "Flow", "month_over_month_volume_change_pct")], 300.0)
        self.assertAlmostEqual(lookup[("month_stats", "2025-02", "Flow", "total_volume")], 120.0)
        self.assertAlmostEqual(lookup[("month_stats", "2025-02", "Flow", "month_over_month_volume_change_pct")], -50.0)

        # year_stats: 2024 (60), 2025 (360)
        self.assertAlmostEqual(lookup[("year_stats", "2024", "Flow", "total_volume")], 60.0)
        self.assertAlmostEqual(lookup[("year_stats", "2025", "Flow", "total_volume")], 360.0)
        self.assertAlmostEqual(lookup[("year_stats", "2025", "Flow", "year_over_year_volume_delta")], 300.0)
        self.assertAlmostEqual(lookup[("year_stats", "2025", "Flow", "year_over_year_volume_change_pct")], 500.0)


class TestEndToEndCLI(unittest.TestCase):
    def test_cli_runs_on_all_repository_series(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            for idx in range(1, 6):
                series_name = f"series-{idx}"
                out_csv = tmp_path / f"{series_name}_out.csv"
                rc = cli_main(["--series", series_name, "--data-dir", str(DATA_DIR), "--output", str(out_csv), "--quiet"])
                self.assertEqual(rc, 0)
                self.assertTrue(out_csv.is_file())

                with out_csv.open("r", encoding="utf-8", newline="") as fh:
                    reader = csv.reader(fh)
                    header = next(reader)
                    rows = list(reader)

                self.assertEqual(tuple(header), CSV_COLUMNS)
                self.assertGreater(len(rows), 50)
                sections = {row[1] for row in rows}
                self.assertEqual(sections, EXPECTED_SECTIONS)

                if series_name == "series-1":
                    columns = {row[3] for row in rows}
                    self.assertIn("Flow", columns)
                    self.assertIn("Subflow", columns)
                    metrics = {row[4] for row in rows if row[3] == "Subflow"}
                    self.assertIn("subflow_share_of_flow", metrics)

    def test_data_quality_irregular_and_gaps(self) -> None:
        s2_lookup = _index_records(analyze_series(load_series("series-2", data_dir=DATA_DIR)))
        self.assertGreater(s2_lookup[("data_quality", "all", "all", "irregular_interval_count")], 0)
        self.assertEqual(s2_lookup[("data_quality", "all", "all", "interval_min_s")], 40.0)
        self.assertEqual(s2_lookup[("data_quality", "all", "all", "interval_max_s")], 79.0)

        s4_lookup = _index_records(analyze_series(load_series("series-4", data_dir=DATA_DIR)))
        self.assertEqual(s4_lookup[("data_quality", "all", "all", "gap_interval_count")], 21)

        s5_lookup = _index_records(analyze_series(load_series("series-5", data_dir=DATA_DIR)))
        self.assertEqual(s5_lookup[("data_quality", "all", "all", "gap_interval_count")], 209)

    def test_cli_returns_nonzero_on_invalid_series(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            rc = cli_main(["--series", "does-not-exist", "--data-dir", str(DATA_DIR), "--output", str(Path(tmpdir) / "x.csv")])
            self.assertEqual(rc, 1)

    def test_export_creates_nested_parent_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            nested = Path(tmpdir) / "a" / "b" / "report.csv"
            records = analyze_series(load_series("series-3", data_dir=DATA_DIR))
            written = export_results_csv(records, nested)
            self.assertTrue(written.is_file())


if __name__ == "__main__":
    unittest.main()
