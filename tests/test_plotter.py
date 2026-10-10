"""Tests for ResultPlotter (base paper Figs. 11, 14, 16)."""

from pathlib import Path

import pandas as pd
import pytest

from cowic.analysis.plotter import METRIC_COLUMNS, ResultPlotter
from cowic.exceptions import ConfigurationError


def _benchmark_rows(
    experiments: list[str], x_column: str, x_values: list[float]
) -> list[dict[str, float | str]]:
    rows: list[dict[str, float | str]] = []
    for exp in experiments:
        for i, x_value in enumerate(x_values):
            rows.append(
                {
                    "experiment_id": exp,
                    "d_free_ms": 62.0,
                    "d_sensing_ms": 10.0,
                    x_column: x_value,
                    "zigbee_gain_ratio": 0.5 + 0.05 * i,
                    "wifi_drop_rate": 0.1 - 0.01 * i,
                    "spectrum_utilization": 0.7 + 0.02 * i,
                    "wifi_jitter_ms": 2.0 + 0.1 * i,
                    "moved_fg_count": 5 + i,
                    "max_fg_delay_ms": 40.0 + i,
                }
            )
    return rows


@pytest.fixture
def benchmark_csv(tmp_path: Path) -> Path:
    """Sample Fig. 11-style benchmark CSV: Exp 1-6 across a D_free sweep."""
    rows = _benchmark_rows(
        [f"Exp_{n}" for n in range(1, 7)], "d_free_ms", [31.0, 62.0, 123.0]
    )
    csv_path = tmp_path / "benchmark.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    return csv_path


@pytest.fixture
def sensing_sweep_csv(tmp_path: Path) -> Path:
    """Sample Fig. 16-style CSV: Exp 4-1..4-4 across a D_sensing sweep."""
    rows = _benchmark_rows(
        [f"Exp_4-{n}" for n in range(1, 5)], "d_sensing_ms", [10.0, 20.0, 50.0, 100.0]
    )
    csv_path = tmp_path / "sensing.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    return csv_path


def test_plot_benchmark_saves_png_under_output_dir(
    tmp_path: Path, benchmark_csv: Path
) -> None:
    figures_dir = tmp_path / "figures"
    plotter = ResultPlotter(figures_dir)
    output_path = plotter.plot_benchmark(benchmark_csv)
    assert output_path.exists()
    assert output_path.suffix == ".png"
    assert output_path.parent == figures_dir
    assert output_path.stat().st_size > 0


def test_plot_benchmark_creates_output_dir_if_missing(
    tmp_path: Path, benchmark_csv: Path
) -> None:
    figures_dir = tmp_path / "nested" / "figures"
    assert not figures_dir.exists()
    ResultPlotter(figures_dir)
    assert figures_dir.exists()


def test_plot_d_free_sweep_fig11_and_fig14_use_distinct_filenames(
    tmp_path: Path, benchmark_csv: Path
) -> None:
    plotter = ResultPlotter(tmp_path / "figures")
    fig11 = plotter.plot_d_free_sweep(
        benchmark_csv,
        title="Traffic I, T_ZB=1000ms",
        filename="fig11_traffic1",
    )
    fig14 = plotter.plot_d_free_sweep(
        benchmark_csv,
        title="Traffic III, T_ZB=1000ms",
        filename="fig14_traffic3",
    )
    assert fig11 != fig14
    assert fig11.exists()
    assert fig14.exists()


def test_plot_sensing_sensitivity_fig16(
    tmp_path: Path, sensing_sweep_csv: Path
) -> None:
    plotter = ResultPlotter(tmp_path / "figures")
    output_path = plotter.plot_sensing_sensitivity(
        sensing_sweep_csv,
        title="Sensing Window Sensitivity, Traffic I",
        filename="fig16_sensing",
    )
    assert output_path.exists()
    assert output_path.name == "fig16_sensing.png"


def test_plot_benchmark_rejects_missing_csv(tmp_path: Path) -> None:
    plotter = ResultPlotter(tmp_path / "figures")
    with pytest.raises(ConfigurationError):
        plotter.plot_benchmark(tmp_path / "does_not_exist.csv")


def test_plot_benchmark_rejects_missing_required_columns(tmp_path: Path) -> None:
    incomplete_csv = tmp_path / "incomplete.csv"
    pd.DataFrame({"experiment_id": ["Exp_1"], "d_free_ms": [62.0]}).to_csv(
        incomplete_csv, index=False
    )
    plotter = ResultPlotter(tmp_path / "figures")
    with pytest.raises(ConfigurationError):
        plotter.plot_benchmark(incomplete_csv)


def test_plot_benchmark_rejects_empty_csv(tmp_path: Path) -> None:
    empty_csv = tmp_path / "empty.csv"
    columns = ["experiment_id"] + [col for col, _ in METRIC_COLUMNS] + ["d_free_ms"]
    pd.DataFrame(columns=columns).to_csv(empty_csv, index=False)
    plotter = ResultPlotter(tmp_path / "figures")
    with pytest.raises(ConfigurationError):
        plotter.plot_benchmark(empty_csv)


def test_plot_d_free_sweep_rejects_missing_sweep_column(
    tmp_path: Path, benchmark_csv: Path
) -> None:
    plotter = ResultPlotter(tmp_path / "figures")
    with pytest.raises(ConfigurationError):
        plotter.plot_d_free_sweep(
            benchmark_csv,
            title="Bad sweep",
            filename="fig_bad",
            x_column="not_a_real_column",
        )


def test_metric_columns_match_simulation_metrics_fields() -> None:
    """The six plotted metrics must stay in sync with SimulationMetrics."""
    from cowic.analysis.metrics import SimulationMetrics

    metric_field_names = {col for col, _ in METRIC_COLUMNS}
    simulation_metrics_fields = set(SimulationMetrics.__dataclass_fields__)
    assert metric_field_names <= simulation_metrics_fields
    assert len(METRIC_COLUMNS) == 6
