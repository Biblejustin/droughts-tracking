"""Drought analysis plots — mirrors the pattern of pandemics/cyclones/etc.

Conventions:
- Pre-1850 entries kept in the catalog as research index but excluded from
  trend fits (paleoclimate + civilization records are uneven).
- 1850+ used as the 'global meteorological-records' detection-clean span.
- 1950+ used as the modern EM-DAT-comparable era.
- 1979+ marks the satellite-era full-coverage period (Palmer Drought Severity
  Index, MODIS, etc.).
- Severity is mostly measured by people-affected rather than deaths, because
  modern droughts kill few people directly but displace tens of millions.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

HERE = Path(__file__).parent
PLOTS = HERE / "plots"
PLOTS.mkdir(exist_ok=True)

CATALOG_START = 1850
GREAT_DROUGHT_THRESHOLD = 1_000_000  # people affected
PARTIAL_DECADE_START = 2020

plt.rcParams.update({
    "figure.dpi": 110, "savefig.dpi": 150, "savefig.bbox": "tight",
    "font.size": 10, "axes.titlesize": 12,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.25, "grid.linestyle": "--",
})


def load_events() -> pd.DataFrame:
    df = pd.read_csv(HERE / "droughts.csv")
    df["start_year"] = pd.to_numeric(df["start_year"], errors="coerce")
    df["end_year"] = pd.to_numeric(df["end_year"], errors="coerce")
    df["deaths_estimate"] = pd.to_numeric(df["deaths_estimate"], errors="coerce").fillna(0)
    df["people_affected"] = pd.to_numeric(df["people_affected"], errors="coerce").fillna(0)
    df["end_year"] = df["end_year"].fillna(df["start_year"])
    df["midpoint"] = (df["start_year"] + df["end_year"]) / 2
    df["duration"] = df["end_year"] - df["start_year"] + 1
    df["intensity"] = df[["deaths_estimate", "people_affected"]].max(axis=1)
    return df


def fmt_thousands(x, _):
    return f"{int(x):,}"


def plot_01_history(df: pd.DataFrame):
    """Drought intensity over time — bubble sized by max(deaths, people_affected)."""
    fig, ax = plt.subplots(figsize=(11, 5.5))
    plot_df = df[df["intensity"] > 0].copy()
    sizes = np.clip(np.sqrt(plot_df["intensity"]) / 30, 30, 1500)
    colors = np.where(plot_df["intensity"] >= GREAT_DROUGHT_THRESHOLD, "#cc3322", "#aa7733")
    ax.scatter(plot_df["midpoint"], plot_df["intensity"], s=sizes, c=colors,
                alpha=0.65, edgecolor="black", linewidth=0.5)
    ax.set_yscale("log")
    ax.set_ylabel("max(deaths, people affected) — log")
    ax.set_xlabel("Year (negative = BCE)")
    ax.set_title("Drought intensity over time — bubble ∝ intensity, red = ≥1M people affected/killed")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(fmt_thousands))
    for _, row in plot_df.nlargest(8, "intensity").iterrows():
        ax.annotate(row["name"].split("(")[0][:24], (row["midpoint"], row["intensity"]),
                    xytext=(5, 5), textcoords="offset points", fontsize=8, alpha=0.85)
    plt.tight_layout()
    plt.savefig(PLOTS / "01_drought_history.png")
    plt.close()


def plot_02_decadal_counts_by_band(df: pd.DataFrame):
    """Stacked bars: droughts per decade by intensity band, multi-era trend lines."""
    bands = [(100_000, 1_000_000, "100k–1M affected", "#dddd99"),
             (1_000_000, 10_000_000, "1M–10M", "#cc8844"),
             (10_000_000, np.inf, "≥10M", "#cc3322")]
    modern = df[df["start_year"] >= CATALOG_START].copy()
    modern["decade"] = (modern["start_year"] // 10) * 10

    fig, ax = plt.subplots(figsize=(11, 5))
    decades = np.arange(CATALOG_START, 2030, 10)
    bottom = np.zeros(len(decades))
    for lo, hi, label, color in bands:
        counts = []
        for d in decades:
            n = ((modern["decade"] == d) &
                  (modern["intensity"] >= lo) &
                  (modern["intensity"] < hi)).sum()
            counts.append(n)
        ax.bar(decades, counts, width=8, bottom=bottom, label=label,
                color=color, edgecolor="black", linewidth=0.4)
        bottom += counts

    ax.axvspan(PARTIAL_DECADE_START, PARTIAL_DECADE_START + 10,
                color="grey", alpha=0.18, label="partial decade")

    # Multi-era trend lines
    totals = np.array(bottom, dtype=float)
    eras = [
        (CATALOG_START, "Full catalog (1850+)", "#222222", "--"),
        (1950, "EM-DAT era (1950+)", "#33aa66", ":"),
        (1979, "Satellite era (1979+)", "#3366cc", "-."),
    ]
    fits = []
    rng = np.random.default_rng(42)
    for era_start, label, color, ls in eras:
        mask = (decades >= era_start) & (decades < PARTIAL_DECADE_START)
        if mask.sum() < 3:
            fits.append((label, np.nan, np.nan, np.nan)); continue
        x_fit = decades[mask].astype(float); y_fit = totals[mask]
        slope, intercept = np.polyfit(x_fit, y_fit, 1)
        boots = []
        for _ in range(2000):
            idx = rng.integers(0, len(x_fit), len(x_fit))
            s, _ = np.polyfit(x_fit[idx], y_fit[idx], 1)
            boots.append(s)
        lo, hi = np.percentile(boots, [2.5, 97.5])
        line_x = np.linspace(era_start, decades.max(), 50)
        ax.plot(line_x, slope * line_x + intercept, ls, color=color,
                  linewidth=1.6,
                  label=f"{label}: {slope:+.3f}/dec [CI {lo:+.3f}, {hi:+.3f}]")
        fits.append((label, slope, lo, hi))

    ax.set_xlabel("Decade")
    ax.set_ylabel("Droughts per decade")
    ax.set_title(f"Droughts per decade by severity (catalog ≥{CATALOG_START}; intensity = max(deaths, affected))")
    ax.legend(loc="upper left", fontsize=8)
    plt.tight_layout()
    plt.savefig(PLOTS / "02_decadal_counts_by_band.png")
    plt.close()
    return fits


def plot_03_great_drought_timing(df: pd.DataFrame):
    """Cumulative ≥1M-affected droughts vs constant rate + inter-event intervals."""
    great = df[df["intensity"] >= GREAT_DROUGHT_THRESHOLD].sort_values("start_year").reset_index(drop=True)
    great_modern = great[great["start_year"] >= CATALOG_START].reset_index(drop=True)
    great_modern["n"] = np.arange(1, len(great_modern) + 1)
    if len(great_modern) < 2:
        return
    span_yr = great_modern["start_year"].iloc[-1] - CATALOG_START
    rate = len(great_modern) / span_yr
    yrs = np.arange(CATALOG_START, 2026)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    ax = axes[0]
    ax.step(great_modern["start_year"], great_modern["n"], where="post",
            color="#cc3322", linewidth=2, label="Observed cumulative ≥1M-affected droughts")
    ax.plot(yrs, rate * (yrs - CATALOG_START), color="gray", linestyle="--",
            label=f"Constant rate ({rate:.3f}/yr ≈ once per {1/rate:.1f}yr)")
    for _, row in great_modern.iterrows():
        ax.annotate(row["name"].split(" (")[0][:14], (row["start_year"], row["n"]),
                     xytext=(3, -10), textcoords="offset points", fontsize=7, alpha=0.7)
    ax.set_xlabel("Year")
    ax.set_ylabel("Cumulative ≥1M-affected droughts")
    ax.set_title(f"Cumulative vs constant-rate ({CATALOG_START}+)")
    ax.legend()

    ax = axes[1]
    intervals = np.diff(great_modern["start_year"].values)
    if len(intervals) > 0:
        ax.bar(range(len(intervals)), intervals,
                color="#cc3322", alpha=0.7, edgecolor="black", linewidth=0.4)
        ax.axhline(intervals.mean(), color="gray", linestyle="--",
                    label=f"mean = {intervals.mean():.1f} yr")
        labels = [f"{a}→{b}" for a, b in zip(great_modern["start_year"].values[:-1],
                                              great_modern["start_year"].values[1:])]
        ax.set_xticks(range(len(intervals)))
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
        ax.set_ylabel("Years between great droughts")
        ax.set_title("Inter-event intervals")
        ax.legend()
    plt.tight_layout()
    plt.savefig(PLOTS / "03_great_drought_timing.png")
    plt.close()


def plot_04_distribution(df: pd.DataFrame):
    """Log-log survival function of intensity, power-law fit."""
    intensity = df["intensity"].values
    intensity = intensity[intensity > 0]
    intensity = np.sort(intensity)[::-1]
    survival = np.arange(1, len(intensity) + 1)

    tail_mask = intensity >= 100_000
    if tail_mask.sum() >= 5:
        x_tail = np.log10(intensity[tail_mask])
        y_tail = np.log10(survival[tail_mask])
        slope, intercept = np.polyfit(x_tail, y_tail, 1)
        alpha = -slope
    else:
        alpha = None

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.loglog(intensity, survival, "o", color="#cc3322", alpha=0.7,
                markeredgecolor="black", markersize=6, label="Droughts (intensity = max deaths or affected)")
    if alpha is not None:
        xs = np.logspace(np.log10(100_000), np.log10(intensity.max()), 50)
        ys = 10 ** intercept * xs ** slope
        ax.loglog(xs, ys, "--", color="gray",
                    label=f"Power-law fit α={alpha:.2f} (tail ≥100k)")
    ax.set_xlabel("Intensity (max deaths or affected)")
    ax.set_ylabel("Survival count")
    ax.set_title("Drought intensity distribution (power-law tail)")
    ax.legend()
    plt.tight_layout()
    plt.savefig(PLOTS / "04_intensity_distribution.png")
    plt.close()


def main():
    df = load_events()
    print(f"Loaded {len(df)} droughts; "
            f"{int(df['start_year'].min())}–{int(df['end_year'].max())}")
    print(f"With deaths estimate: {(df['deaths_estimate'] > 0).sum()}")
    print(f"With people-affected estimate: {(df['people_affected'] > 0).sum()}")
    print(f"≥1M intensity (deaths OR affected): {(df['intensity'] >= 1_000_000).sum()}")
    plot_01_history(df)
    fits = plot_02_decadal_counts_by_band(df)
    for label, slope, lo, hi in fits:
        print(f"  {label:<40} {slope:+.3f}/dec  [CI {lo:+.3f}, {hi:+.3f}]")
    plot_03_great_drought_timing(df)
    plot_04_distribution(df)
    print(f"Wrote 4 plots to {PLOTS}/")


if __name__ == "__main__":
    main()
