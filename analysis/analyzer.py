"""Statistical and trend analysis for normalized water flow time series."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from analysis.loader import LoadedSeries

SIGNIFICANCE_ALPHA = 0.05
ROBUST_Z_THRESHOLD = 2.0


@dataclass(frozen=True)
class AnalysisRecord:
    """Single tidy row in the exported analysis CSV."""

    series: str
    section: str
    period: str
    series_column: str
    metric: str
    value: Any
    unit: str


def _format_value(value: Any) -> Any:
    """Normalize numpy/float values for consistent tabular export."""
    if value is None:
        return ""
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        if not np.isfinite(value):
            return ""
        return round(float(value), 6)
    return value


def _trend_direction(slope: float, p_value: float, alpha: float = SIGNIFICANCE_ALPHA) -> str:
    if not (np.isfinite(slope) and np.isfinite(p_value)) or p_value >= alpha or slope == 0.0:
        return "no_significant_trend"
    return "increasing" if slope > 0 else "decreasing"


def _safe_linregress(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float, float, float] | None:
    """Compute OLS linear regression without warnings on constant inputs."""
    mask = np.isfinite(x) & np.isfinite(y)
    xv = x[mask]
    yv = y[mask]
    if len(xv) < 2 or np.ptp(xv) == 0.0:
        return None
    if np.ptp(yv) == 0.0:
        return 0.0, float(yv[0]), 0.0, 0.0, 1.0
    res = stats.linregress(xv, yv)
    return (
        float(res.slope),
        float(res.intercept),
        float(res.rvalue),
        float(res.rvalue ** 2),
        float(res.pvalue),
    )


def _safe_theilslopes(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float] | None:
    """Compute Theil-Sen robust slope and 95% confidence interval."""
    mask = np.isfinite(x) & np.isfinite(y)
    xv = x[mask]
    yv = y[mask]
    if len(xv) < 2 or np.ptp(xv) == 0.0:
        return None
    if np.ptp(yv) == 0.0:
        return 0.0, 0.0, 0.0
    res = stats.theilslopes(yv, xv, alpha=1.0 - SIGNIFICANCE_ALPHA)
    return float(res.slope), float(res.low_slope), float(res.high_slope)


def _safe_kendall(x: np.ndarray, y: np.ndarray) -> tuple[float, float] | None:
    """Compute Kendall's tau (Mann-Kendall monotonic trend) without constant-input warnings."""
    mask = np.isfinite(x) & np.isfinite(y)
    xv = x[mask]
    yv = y[mask]
    if len(xv) < 3 or np.ptp(xv) == 0.0:
        return None
    if np.ptp(yv) == 0.0:
        return 0.0, 1.0
    res = stats.kendalltau(xv, yv)
    return float(res.statistic), float(res.pvalue)


def _safe_spearman(x: np.ndarray, y: np.ndarray) -> tuple[float, float] | None:
    """Compute Spearman rank correlation without constant-input warnings."""
    mask = np.isfinite(x) & np.isfinite(y)
    xv = x[mask]
    yv = y[mask]
    if len(xv) < 3 or np.ptp(xv) == 0.0:
        return None
    if np.ptp(yv) == 0.0:
        return 0.0, 1.0
    res = stats.spearmanr(xv, yv)
    return float(res.statistic), float(res.pvalue)


def _safe_skew(values: np.ndarray) -> float | None:
    if len(values) < 3 or np.ptp(values) == 0.0:
        return 0.0 if len(values) >= 3 else None
    return float(stats.skew(values, bias=False))


def _safe_kurtosis(values: np.ndarray) -> float | None:
    if len(values) < 4 or np.ptp(values) == 0.0:
        return 0.0 if len(values) >= 4 else None
    return float(stats.kurtosis(values, bias=False))


def _hourly_slope(series: pd.Series) -> tuple[float, float] | None:
    """Compute OLS slope (L/interval/hour) and R^2 on 1-hour resampled means."""
    hourly = series.resample("1h").mean().dropna()
    if len(hourly) < 2:
        return None
    hours = (hourly.index - hourly.index[0]).total_seconds().to_numpy(dtype=float) / 3600.0
    reg = _safe_linregress(hours, hourly.to_numpy(dtype=float))
    if reg is None:
        return None
    return reg[0], reg[3]


def _robust_zscores(values: np.ndarray) -> np.ndarray:
    """Compute robust z-scores using median and MAD (falling back to std if MAD is zero)."""
    if len(values) == 0:
        return np.array([], dtype=float)
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    if mad > 0.0:
        scale = 1.4826 * mad
        return (values - median) / scale
    std = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
    if std > 0.0:
        return (values - median) / std
    return np.zeros_like(values, dtype=float)


def _add(
    records: list[AnalysisRecord],
    series_name: str,
    section: str,
    period: str,
    series_column: str,
    metric: str,
    value: Any,
    unit: str,
) -> None:
    records.append(
        AnalysisRecord(
            series=series_name,
            section=section,
            period=period,
            series_column=series_column,
            metric=metric,
            value=_format_value(value),
            unit=unit,
        )
    )


def _compute_data_quality(loaded: LoadedSeries, records: list[AnalysisRecord]) -> None:
    df = loaded.data
    idx = df.index
    name = loaded.name
    section = "data_quality"

    diffs = idx.to_series().diff().dropna().dt.total_seconds().to_numpy(dtype=float)
    duration_seconds = float((idx[-1] - idx[0]).total_seconds()) if len(idx) > 1 else 0.0
    iso = idx.isocalendar()
    unique_weeks = len(set(zip(iso.year, iso.week)))

    _add(records, name, section, "all", "all", "source_encoding", loaded.encoding, "text")
    _add(records, name, section, "all", "all", "row_count", len(df), "count")
    _add(records, name, section, "all", "all", "start_timestamp", idx[0].isoformat(sep=" "), "timestamp")
    _add(records, name, section, "all", "all", "end_timestamp", idx[-1].isoformat(sep=" "), "timestamp")
    _add(records, name, section, "all", "all", "duration_hours", duration_seconds / 3600.0, "hours")
    _add(records, name, section, "all", "all", "duration_days", duration_seconds / 86400.0, "days")
    _add(records, name, section, "all", "all", "days_covered", int(idx.normalize().nunique()), "count")
    _add(records, name, section, "all", "all", "weeks_covered", unique_weeks, "count")
    _add(records, name, section, "all", "all", "months_covered", int(idx.to_period("M").nunique()), "count")
    _add(records, name, section, "all", "all", "years_covered", int(idx.year.nunique()), "count")
    _add(records, name, section, "all", "all", "duplicate_timestamp_count", int(idx.duplicated().sum()), "count")

    if len(diffs) > 0:
        _add(records, name, section, "all", "all", "interval_median_s", float(np.median(diffs)), "seconds")
        _add(records, name, section, "all", "all", "interval_mean_s", float(np.mean(diffs)), "seconds")
        _add(records, name, section, "all", "all", "interval_min_s", float(np.min(diffs)), "seconds")
        _add(records, name, section, "all", "all", "interval_max_s", float(np.max(diffs)), "seconds")
        _add(records, name, section, "all", "all", "irregular_interval_count", int(np.sum(diffs != 60.0)), "count")
        _add(records, name, section, "all", "all", "gap_interval_count", int(np.sum(diffs > 90.0)), "count")


def _compute_overall_stats(loaded: LoadedSeries, records: list[AnalysisRecord]) -> None:
    df = loaded.data
    name = loaded.name
    section = "overall_stats"

    for col in loaded.value_columns:
        s = df[col]
        valid = s.dropna()
        vals = valid.to_numpy(dtype=float)
        n = len(vals)
        missing = int(s.isna().sum())

        _add(records, name, section, "all", col, "count", n, "count")
        _add(records, name, section, "all", col, "missing_count", missing, "count")
        if n == 0:
            continue

        total_volume = float(np.sum(vals))
        mean = float(np.mean(vals))
        std = float(np.std(vals, ddof=1)) if n > 1 else 0.0
        var = float(np.var(vals, ddof=1)) if n > 1 else 0.0
        cv = (std / mean) if mean != 0.0 else np.nan
        q10, q25, q50, q75, q90, q95, q99 = np.percentile(vals, [10, 25, 50, 75, 90, 95, 99])
        iqr = float(q75 - q25)
        zero_count = int(np.sum(vals == 0.0))
        nonzero_vals = vals[vals > 0.0]
        nonzero_count = int(len(nonzero_vals))
        nonzero_ratio = 100.0 * nonzero_count / n
        mean_nonzero = float(np.mean(nonzero_vals)) if nonzero_count > 0 else 0.0

        metrics: list[tuple[str, Any, str]] = [
            ("total_volume", total_volume, "L"),
            ("mean", mean, "L/interval"),
            ("std", std, "L/interval"),
            ("variance", var, "L^2/interval^2"),
            ("cv", cv, "ratio"),
            ("min", float(np.min(vals)), "L/interval"),
            ("p10", float(q10), "L/interval"),
            ("p25", float(q25), "L/interval"),
            ("median", float(q50), "L/interval"),
            ("p75", float(q75), "L/interval"),
            ("p90", float(q90), "L/interval"),
            ("p95", float(q95), "L/interval"),
            ("p99", float(q99), "L/interval"),
            ("max", float(np.max(vals)), "L/interval"),
            ("iqr", iqr, "L/interval"),
            ("skewness", _safe_skew(vals), "dimensionless"),
            ("kurtosis", _safe_kurtosis(vals), "dimensionless"),
            ("zero_count", zero_count, "count"),
            ("nonzero_count", nonzero_count, "count"),
            ("nonzero_ratio", nonzero_ratio, "percent"),
            ("mean_nonzero", mean_nonzero, "L/interval"),
        ]
        for metric_name, metric_val, unit in metrics:
            _add(records, name, section, "all", col, metric_name, metric_val, unit)

    # Cross-column summary when Flow and Subflow are both present (e.g. series-1)
    if "Flow" in df.columns and "Subflow" in df.columns:
        paired = df[["Flow", "Subflow"]].dropna()
        if len(paired) >= 2:
            flow_sum = float(paired["Flow"].sum())
            subflow_sum = float(paired["Subflow"].sum())
            share = (100.0 * subflow_sum / flow_sum) if flow_sum > 0.0 else np.nan
            _add(records, name, section, "all", "Subflow", "subflow_share_of_flow", share, "percent")

            fv = paired["Flow"].to_numpy(dtype=float)
            sv = paired["Subflow"].to_numpy(dtype=float)
            if np.ptp(fv) > 0.0 and np.ptp(sv) > 0.0:
                pearson_r = float(stats.pearsonr(fv, sv).statistic)
                spearman_r = float(stats.spearmanr(fv, sv).statistic)
            else:
                pearson_r = 0.0
                spearman_r = 0.0
            _add(records, name, section, "all", "Subflow", "flow_subflow_pearson_r", pearson_r, "dimensionless")
            _add(records, name, section, "all", "Subflow", "flow_subflow_spearman_r", spearman_r, "dimensionless")


def _compute_overall_trend(loaded: LoadedSeries, records: list[AnalysisRecord]) -> None:
    df = loaded.data
    name = loaded.name
    section = "overall_trend"

    for col in loaded.value_columns:
        s = df[col].dropna()
        if len(s) < 2:
            continue

        hourly = s.resample("1h").mean().dropna()
        if len(hourly) >= 2:
            hours = (hourly.index - hourly.index[0]).total_seconds().to_numpy(dtype=float) / 3600.0
            y_hourly = hourly.to_numpy(dtype=float)

            reg = _safe_linregress(hours, y_hourly)
            if reg is not None:
                slope, intercept, r_val, r_sq, p_val = reg
                _add(records, name, section, "all", col, "hourly_ols_slope", slope, "L/interval/hour")
                _add(records, name, section, "all", col, "hourly_ols_slope_per_day", slope * 24.0, "L/interval/day")
                _add(records, name, section, "all", col, "hourly_ols_intercept", intercept, "L/interval")
                _add(records, name, section, "all", col, "hourly_ols_r_value", r_val, "dimensionless")
                _add(records, name, section, "all", col, "hourly_ols_r_squared", r_sq, "dimensionless")
                _add(records, name, section, "all", col, "hourly_ols_p_value", p_val, "p_value")
                _add(
                    records,
                    name,
                    section,
                    "all",
                    col,
                    "hourly_ols_trend_direction",
                    _trend_direction(slope, p_val),
                    "category",
                )

            theil = _safe_theilslopes(hours, y_hourly)
            if theil is not None:
                ts_slope, ts_low, ts_high = theil
                _add(records, name, section, "all", col, "hourly_theil_sen_slope", ts_slope, "L/interval/hour")
                _add(records, name, section, "all", col, "hourly_theil_sen_ci_low", ts_low, "L/interval/hour")
                _add(records, name, section, "all", col, "hourly_theil_sen_ci_high", ts_high, "L/interval/hour")

            kendall = _safe_kendall(hours, y_hourly)
            if kendall is not None:
                tau, kp = kendall
                _add(records, name, section, "all", col, "hourly_kendall_tau", tau, "dimensionless")
                _add(records, name, section, "all", col, "hourly_kendall_p_value", kp, "p_value")
                _add(
                    records,
                    name,
                    section,
                    "all",
                    col,
                    "hourly_kendall_trend_direction",
                    _trend_direction(tau, kp),
                    "category",
                )

            spearman = _safe_spearman(hours, y_hourly)
            if spearman is not None:
                rho, sp = spearman
                _add(records, name, section, "all", col, "hourly_spearman_rho", rho, "dimensionless")
                _add(records, name, section, "all", col, "hourly_spearman_p_value", sp, "p_value")

            # Rolling mean peaks (6h and 24h)
            for window_h in (6, 24):
                min_periods = max(1, window_h // 2)
                rolling = hourly.rolling(window=window_h, min_periods=min_periods).mean().dropna()
                if not rolling.empty:
                    peak_ts = rolling.idxmax()
                    peak_val = float(rolling.loc[peak_ts])
                    _add(records, name, section, "all", col, f"rolling_{window_h}h_peak_mean", peak_val, "L/interval")
                    _add(
                        records,
                        name,
                        section,
                        "all",
                        col,
                        f"rolling_{window_h}h_peak_timestamp",
                        peak_ts.isoformat(sep=" "),
                        "timestamp",
                    )

        # Daily total volume trend
        daily_sums = s.groupby(s.index.normalize()).sum()
        if len(daily_sums) >= 2:
            day_x = (daily_sums.index - daily_sums.index[0]).days.to_numpy(dtype=float)
            day_y = daily_sums.to_numpy(dtype=float)
            d_reg = _safe_linregress(day_x, day_y)
            if d_reg is not None:
                d_slope, _, _, d_r_sq, d_p_val = d_reg
                _add(records, name, section, "all", col, "daily_volume_ols_slope", d_slope, "L/day")
                _add(records, name, section, "all", col, "daily_volume_ols_r_squared", d_r_sq, "dimensionless")
                _add(records, name, section, "all", col, "daily_volume_ols_p_value", d_p_val, "p_value")
                _add(
                    records,
                    name,
                    section,
                    "all",
                    col,
                    "daily_volume_trend_direction",
                    _trend_direction(d_slope, d_p_val),
                    "category",
                )

        # First-half vs second-half comparison
        midpoint = len(s) // 2
        if midpoint > 0:
            first_mean = float(s.iloc[:midpoint].mean())
            second_mean = float(s.iloc[midpoint:].mean())
            change_pct = (100.0 * (second_mean - first_mean) / first_mean) if first_mean > 0.0 else np.nan
            _add(records, name, section, "all", col, "first_half_mean", first_mean, "L/interval")
            _add(records, name, section, "all", col, "second_half_mean", second_mean, "L/interval")
            _add(records, name, section, "all", col, "half_period_change_pct", change_pct, "percent")


def _compute_diurnal_profile(loaded: LoadedSeries, records: list[AnalysisRecord]) -> None:
    df = loaded.data
    name = loaded.name
    section = "diurnal_profile"

    bands = (
        ("night_00_05", (0, 5)),
        ("daytime_06_17", (6, 17)),
        ("evening_18_23", (18, 23)),
    )

    hours = df.index.hour
    for col in loaded.value_columns:
        s = df[col]
        band_means: dict[str, float] = {}

        for band_name, (h_start, h_end) in bands:
            subset = s[(hours >= h_start) & (hours <= h_end)].dropna()
            if subset.empty:
                continue
            vals = subset.to_numpy(dtype=float)
            b_mean = float(np.mean(vals))
            band_means[band_name] = b_mean
            _add(records, name, section, band_name, col, "mean", b_mean, "L/interval")
            _add(records, name, section, band_name, col, "median", float(np.median(vals)), "L/interval")
            _add(records, name, section, band_name, col, "total_volume", float(np.sum(vals)), "L")
            _add(records, name, section, band_name, col, "nonzero_ratio", 100.0 * float(np.mean(vals > 0.0)), "percent")

        if "night_00_05" in band_means and "daytime_06_17" in band_means:
            day_mean = band_means["daytime_06_17"]
            ratio = (band_means["night_00_05"] / day_mean) if day_mean > 0.0 else np.nan
            _add(records, name, section, "all", col, "night_to_day_mean_ratio", ratio, "ratio")

        hourly_means = s.dropna().groupby(s.dropna().index.hour).mean()
        if not hourly_means.empty:
            peak_hour = int(hourly_means.idxmax())
            min_hour = int(hourly_means.idxmin())
            _add(records, name, section, "all", col, "peak_hour", peak_hour, "hour_of_day")
            _add(records, name, section, "all", col, "peak_hour_mean", float(hourly_means.loc[peak_hour]), "L/interval")
            _add(records, name, section, "all", col, "min_hour", min_hour, "hour_of_day")
            _add(records, name, section, "all", col, "min_hour_mean", float(hourly_means.loc[min_hour]), "L/interval")


def _group_by_granularity(df: pd.DataFrame, granularity: str) -> list[tuple[str, pd.DataFrame]]:
    """Partition DataFrame chronologically into (period_label, sub_df) pairs."""
    idx = df.index
    if granularity == "day":
        keys = idx.strftime("%Y-%m-%d")
        ordered_keys = sorted(set(keys))
        return [(k, df.loc[keys == k]) for k in ordered_keys]

    if granularity == "week":
        iso = idx.isocalendar()
        tuples = list(zip(iso.year.to_numpy(), iso.week.to_numpy()))
        unique_sorted = sorted(set(tuples))
        labels = pd.Index([f"{y:04d}-W{w:02d}" for y, w in tuples])
        ordered_labels = [f"{y:04d}-W{w:02d}" for y, w in unique_sorted]
        return [(lbl, df.loc[labels == lbl]) for lbl in ordered_labels]

    if granularity == "month":
        keys = idx.strftime("%Y-%m")
        ordered_keys = sorted(set(keys))
        return [(k, df.loc[keys == k]) for k in ordered_keys]

    if granularity == "year":
        keys = idx.strftime("%Y")
        ordered_keys = sorted(set(keys))
        return [(k, df.loc[keys == k]) for k in ordered_keys]

    raise ValueError(f"Unsupported granularity: {granularity!r}")


def _compute_period_stats(
    loaded: LoadedSeries,
    records: list[AnalysisRecord],
    granularity: str,
    section: str,
    delta_prefix: str,
    slope_metric: str,
    include_days_covered: bool,
    emit_daily_trend_section: bool = False,
) -> None:
    df = loaded.data
    name = loaded.name
    groups = _group_by_granularity(df, granularity)

    for col in loaded.value_columns:
        period_volumes: list[tuple[str, float, float, pd.Series]] = []

        for period_label, group_df in groups:
            s = group_df[col]
            valid = s.dropna()
            vals = valid.to_numpy(dtype=float)
            n = len(vals)
            missing = int(s.isna().sum())

            _add(records, name, section, period_label, col, "sample_count", n, "count")
            _add(records, name, section, period_label, col, "missing_count", missing, "count")
            if include_days_covered:
                days_covered = int(group_df.index.normalize().nunique())
                _add(records, name, section, period_label, col, "days_covered", days_covered, "count")

            if n == 0:
                continue

            total_vol = float(np.sum(vals))
            mean = float(np.mean(vals))
            median = float(np.median(vals))
            std = float(np.std(vals, ddof=1)) if n > 1 else 0.0
            vmin = float(np.min(vals))
            vmax = float(np.max(vals))
            p95 = float(np.percentile(vals, 95))
            nonzero_ratio = 100.0 * float(np.mean(vals > 0.0))

            overnight = valid[valid.index.hour <= 5]
            if not overnight.empty:
                on_vals = overnight.to_numpy(dtype=float)
                overnight_mean = float(np.mean(on_vals))
                overnight_nz = 100.0 * float(np.mean(on_vals > 0.0))
            else:
                overnight_mean = np.nan
                overnight_nz = np.nan

            for metric_name, val, unit in (
                ("total_volume", total_vol, "L"),
                ("mean", mean, "L/interval"),
                ("median", median, "L/interval"),
                ("std", std, "L/interval"),
                ("min", vmin, "L/interval"),
                ("max", vmax, "L/interval"),
                ("p95", p95, "L/interval"),
                ("nonzero_ratio", nonzero_ratio, "percent"),
                ("overnight_mean", overnight_mean, "L/interval"),
                ("overnight_nonzero_ratio", overnight_nz, "percent"),
            ):
                _add(records, name, section, period_label, col, metric_name, val, unit)

            period_volumes.append((period_label, total_vol, overnight_mean, valid))

        if not period_volumes:
            continue

        # Period-over-period deltas, within-period hourly slope, and daily anomaly flags
        target_section = "daily_trend" if emit_daily_trend_section else section
        vols_arr = np.array([item[1] for item in period_volumes], dtype=float)
        vol_zscores = _robust_zscores(vols_arr) if emit_daily_trend_section else None

        on_means_arr = np.array(
            [item[2] if np.isfinite(item[2]) else 0.0 for item in period_volumes],
            dtype=float,
        )
        on_zscores = _robust_zscores(on_means_arr) if emit_daily_trend_section else None

        prev_vol: float | None = None
        for idx_p, (period_label, total_vol, overnight_mean, valid_series) in enumerate(period_volumes):
            if prev_vol is not None:
                delta = total_vol - prev_vol
                pct = (100.0 * delta / prev_vol) if prev_vol > 0.0 else np.nan
                _add(records, name, target_section, period_label, col, f"{delta_prefix}_volume_delta", delta, "L")
                _add(
                    records,
                    name,
                    target_section,
                    period_label,
                    col,
                    f"{delta_prefix}_volume_change_pct",
                    pct,
                    "percent",
                )
            prev_vol = total_vol

            h_slope = _hourly_slope(valid_series)
            if h_slope is not None:
                slope_val, r2_val = h_slope
                _add(records, name, target_section, period_label, col, slope_metric, slope_val, "L/interval/hour")
                if emit_daily_trend_section:
                    _add(records, name, target_section, period_label, col, "intraday_hourly_r_squared", r2_val, "dimensionless")

            if emit_daily_trend_section and vol_zscores is not None and on_zscores is not None:
                z_vol = float(vol_zscores[idx_p])
                z_on = float(on_zscores[idx_p])
                _add(records, name, target_section, period_label, col, "daily_volume_robust_zscore", z_vol, "zscore")
                _add(
                    records,
                    name,
                    target_section,
                    period_label,
                    col,
                    "elevated_day_flag",
                    bool(z_vol >= ROBUST_Z_THRESHOLD),
                    "boolean",
                )
                elevated_on = bool(np.isfinite(overnight_mean) and overnight_mean > 0.0 and z_on >= ROBUST_Z_THRESHOLD)
                _add(
                    records,
                    name,
                    target_section,
                    period_label,
                    col,
                    "elevated_overnight_flag",
                    elevated_on,
                    "boolean",
                )


def analyze_series(loaded: LoadedSeries) -> list[AnalysisRecord]:
    """Run full statistical and trend analysis on a loaded time series."""
    records: list[AnalysisRecord] = []

    _compute_data_quality(loaded, records)
    _compute_overall_stats(loaded, records)
    _compute_overall_trend(loaded, records)
    _compute_diurnal_profile(loaded, records)

    _compute_period_stats(
        loaded=loaded,
        records=records,
        granularity="day",
        section="daily_stats",
        delta_prefix="day_over_day",
        slope_metric="intraday_hourly_slope",
        include_days_covered=False,
        emit_daily_trend_section=True,
    )
    _compute_period_stats(
        loaded=loaded,
        records=records,
        granularity="week",
        section="week_stats",
        delta_prefix="week_over_week",
        slope_metric="within_week_hourly_slope",
        include_days_covered=True,
    )
    _compute_period_stats(
        loaded=loaded,
        records=records,
        granularity="month",
        section="month_stats",
        delta_prefix="month_over_month",
        slope_metric="within_month_hourly_slope",
        include_days_covered=True,
    )
    _compute_period_stats(
        loaded=loaded,
        records=records,
        granularity="year",
        section="year_stats",
        delta_prefix="year_over_year",
        slope_metric="within_year_hourly_slope",
        include_days_covered=True,
    )

    return records
