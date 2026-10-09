"""Publication figure generator reproducing base paper evaluations."""

from pathlib import Path


class ResultPlotter:
    """Generates figures matching Figures 11 through 17."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def plot_benchmark(self, results_csv: Path) -> Path:
        """Generate Fig 11 benchmark comparison plot."""
        raise NotImplementedError(
            "ResultPlotter implementation planned for Sprint Day 2"
        )
