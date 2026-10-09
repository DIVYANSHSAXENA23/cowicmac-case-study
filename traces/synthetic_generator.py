"""Synthetic WiFi Frame Group trace generator matching Table 5."""

from pathlib import Path


def generate_trace(
    traffic_profile: str,
    duration_s: float,
    output_path: Path,
    seed: int = 42,
) -> Path:
    """Generate Frame Groups matching statistical distributions in Table 5."""
    raise NotImplementedError(
        "synthetic_generator implementation planned for Sprint Day 1"
    )
