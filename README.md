# CoWiC-MAC Case Study

Software-only simulation and evaluation of the **CoWiC-MAC** protocol (Cheng et al., *Computer Networks* 2026).

## Overview

This project investigates wireless coexistence between IEEE 802.11 (WiFi) and IEEE 802.15.4 (ZigBee) on the shared 2.4 GHz ISM band. The WiFi Access Point (AP) reschedules WiFi Frame Groups (FGs) via Mixed-Integer Linear Programming (MILP). The ZigBee Coordinator (ZC) dynamically adapts its superframe structure via the Lightweight Window-Scaling Algorithm (L-WSA). Coordination occurs over Cross-Technology Communication (CTC).

## Repository Structure

```
cowicmac-case-study/
├── pyproject.toml              # Build system, dependencies, tool configuration
├── README.md                   # Project overview and quickstart guide
├── IMPLEMENTATION_PLAN.md      # Detailed system specification and formulas
├── SPRINT_PLAN.md              # 2-day implementation sprint plan (Oct 10-11)
├── configs/                    # Experiment configuration presets (Exp 1 to Exp 6)
├── traces/                     # Trace generators and data storage
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

## Quickstart

### Installation

Install dependencies using Python 3.11+:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Running Tests

Run the test suite with pytest:

```bash
pytest
```

Run linter and type checks:

```bash
ruff check .
mypy src/ tests/
```

## Sprint Plan

See `SPRINT_PLAN.md` for the two-day development breakdown across October 10 and October 11, 2026.
