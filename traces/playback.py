"""Replay stored Frame Group traces into the simulation.

A trace written by :mod:`traces.synthetic_generator` is loaded as immutable
:class:`~cowic.models.frame_group.FrameGroup` objects and can be split into
fixed-length AP scheduling cycles.
"""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from cowic.exceptions import ConfigurationError, TraceError
from cowic.models.frame_group import FrameGroup

REQUIRED_COLUMNS: tuple[str, ...] = (
    "fg_id",
    "arrival_time_ms",
    "duration_ms",
    "deadline_ms",
    "original_start_ms",
    "qos_sensitive",
)


@dataclass(frozen=True)
class TraceCycle:
    """Frame Groups whose original start falls in ``[start_ms, end_ms)``."""

    index: int
    start_ms: float
    end_ms: float
    frame_groups: tuple[FrameGroup, ...]


def frame_groups_from_frame(trace: pd.DataFrame) -> list[FrameGroup]:
    """Convert a trace DataFrame to validated Frame Groups sorted by start time."""
    missing = [col for col in REQUIRED_COLUMNS if col not in trace.columns]
    if missing:
        raise TraceError(f"Trace is missing columns: {', '.join(missing)}")
    if trace["fg_id"].duplicated().any():
        raise TraceError("Trace contains duplicate fg_id values")

    ordered = trace.sort_values("original_start_ms", kind="stable")
    fgs = [
        FrameGroup(
            fg_id=int(row.fg_id),
            arrival_time_ms=float(row.arrival_time_ms),
            duration_ms=float(row.duration_ms),
            deadline_ms=float(row.deadline_ms),
            original_start_ms=float(row.original_start_ms),
            qos_sensitive=bool(row.qos_sensitive),
        )
        for row in ordered.itertuples(index=False)
    ]
    for fg in fgs:
        _validate(fg)
    return fgs


def load_trace(path: Path) -> list[FrameGroup]:
    """Load a ``.parquet`` or ``.csv`` trace as Frame Groups."""
    if not path.exists():
        raise TraceError(f"Trace file not found: {path}")
    if path.suffix == ".parquet":
        trace = pd.read_parquet(path)
    elif path.suffix == ".csv":
        trace = pd.read_csv(path)
    else:
        raise TraceError(f"Unsupported trace format {path.suffix!r}")
    return frame_groups_from_frame(trace)


def iter_cycles(
    frame_groups: Sequence[FrameGroup],
    cycle_ms: float,
    horizon_ms: float | None = None,
) -> Iterator[TraceCycle]:
    """Yield consecutive scheduling cycles of length ``cycle_ms``.

    Each FG belongs to the cycle containing its original start, even if it
    runs past the cycle boundary. Empty cycles are yielded too, so cycle
    indices map directly to time. ``horizon_ms`` defaults to the end of the
    last FG.
    """
    if cycle_ms <= 0:
        raise ConfigurationError(f"cycle_ms must be positive, got {cycle_ms}")
    ordered = sorted(frame_groups, key=lambda fg: fg.original_start_ms)
    if horizon_ms is None:
        horizon_ms = max(
            (fg.original_start_ms + fg.duration_ms for fg in ordered), default=0.0
        )

    pos = 0
    index = 0
    start = 0.0
    while start < horizon_ms:
        end = start + cycle_ms
        members: list[FrameGroup] = []
        while pos < len(ordered) and ordered[pos].original_start_ms < end:
            members.append(ordered[pos])
            pos += 1
        yield TraceCycle(index, start, end, tuple(members))
        index += 1
        start = end


def _validate(fg: FrameGroup) -> None:
    if fg.duration_ms <= 0:
        raise TraceError(f"FG {fg.fg_id}: duration must be positive")
    if fg.arrival_time_ms > fg.original_start_ms:
        raise TraceError(f"FG {fg.fg_id}: arrives after its original start")
    if fg.deadline_ms < fg.original_start_ms + fg.duration_ms:
        raise TraceError(f"FG {fg.fg_id}: deadline precedes original completion")
