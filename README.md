# CoWiC-MAC Case Study

Software-only simulation and evaluation of the **CoWiC-MAC** protocol (Cheng et al., _Computer Networks_ 2026).

## Overview

This project studies wireless coexistence between IEEE 802.11 (WiFi) and IEEE 802.15.4 (ZigBee) on the shared 2.4 GHz ISM band. The WiFi Access Point (AP) reschedules WiFi Frame Groups (FGs) using Mixed-Integer Linear Programming (MILP). The ZigBee Coordinator (ZC) adapts its superframe structure using the Lightweight Window-Scaling Algorithm (L-WSA). The two networks communicate over a Cross-Technology Communication (CTC) link.

## Team

| Name            | Registration Number | GitHub             |
| --------------- | ------------------- | ------------------ |
| Upayan Mazumder | 24BDS0367           | `upayanmazumder`   |
| Nitesh Pandey   | 24BCB0141           | `Nitesh050`        |
| Divyansh Saxena | 24BCB0108           | `DIVYANSHSAXENA23` |

See [Contributors](CONTRIBUTORS.md) for module and presentation ownership.

## Repository Structure

```text
cowicmac-case-study/
├── pyproject.toml              # Build system, dependencies, tool configuration
├── README.md                   # Project overview and quickstart guide
├── CONTRIBUTORS.md             # Contributor roles and module ownership
├── IMPLEMENTATION_PLAN.md      # Detailed system specification and formulas
├── configs/                    # Experiment configuration presets (Exp 1 to Exp 6)
├── traces/                     # Trace generators and data storage
├── scripts/                    # Benchmark sweep runner
├── src/cowic/                  # Core protocol and simulation package
│   ├── models/                 # Dataclass models (FrameGroup, SuperframeConfig)
│   ├── wifi/                   # AP orchestrator and MILP scheduler
│   ├── zigbee/                 # ZigBee coordinator and L-WSA adapter
│   ├── ctc/                    # Cross-technology signaling channel model
│   ├── sim/                    # SimPy simulation engine and collision medium
│   └── analysis/               # Metrics calculator and figure plotter
├── tests/                      # Automated unit and integration test suite
└── reviews/                    # Course review documents and base paper PDF
```

Read the [project document](reviews/project_document.md) and the [presentation guides](reviews/README.md).

## Quickstart

### Installation

Install dependencies using Python 3.11 or newer:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Running Tests

Run the full test suite:

```bash
pytest
```

Run linter and type checks:

```bash
ruff check .
mypy src/ tests/
```

### Running Experiments

Generate a synthetic traffic trace:

```bash
python -m traces.synthetic_generator --profile Traffic_I --output traces/data/traffic1.parquet
```

Run a specific experiment:

```bash
python -m cowic.sim.simulation_engine --config configs/exp4_cowic_full.yaml
```

Run the benchmark sweep (quick smoke run):

```bash
python scripts/run_benchmark_sweep.py --quick
```

Run the full benchmark sweep:

```bash
python scripts/run_benchmark_sweep.py --output-csv results/benchmark_results.csv
```

### Evaluation Results

After running the benchmark sweep, generate figures:

```bash
python -m cowic.analysis.plotter --results-dir results/ --output-dir figures/
```

## Base Paper

Cheng, T., Li, S., and Pan, Y. "CoWiC-MAC: A Coordinated WiFi-Centric MAC Mechanism in Heterogeneous Wireless Networks." _Computer Networks_, Vol. 287, Art. 112479, Sept. 2026. DOI: [10.1016/j.comnet.2026.112479](https://doi.org/10.1016/j.comnet.2026.112479)
