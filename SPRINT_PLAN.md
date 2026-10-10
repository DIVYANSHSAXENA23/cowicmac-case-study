# Sprint Plan: CoWiC-MAC Implementation

**Dates:** October 10, 2026 – October 11, 2026  
**Goal:** Deliver a working software-only simulation of the CoWiC-MAC protocol with automated evaluation and figures.

---

## Team Roles and Ownership

- **Upayan Mazumder (`upayanmazumder`) [Lead]:**
  - Optimization engine and MILP formulation (`src/cowic/wifi/milp_scheduler.py`).
  - Discrete-event simulation engine (`src/cowic/sim/simulation_engine.py`).
  - Shared channel collision medium (`src/cowic/sim/channel_medium.py`).
  - Reassigned from Divyansh: ZigBee L-WSA adapter (`src/cowic/zigbee/lwsa_adapter.py`,
    `src/cowic/zigbee/coordinator.py`, issue #4) and the figure plotter
    (`src/cowic/analysis/plotter.py`, issue #10).
  - Integration lead, code review, and branch merging.

- **Nitesh Pandey (`Nitesh050`):**
  - WiFi AP orchestrator state machine (`src/cowic/wifi/ap_orchestrator.py`).
  - Synthetic traffic generator and trace parser (`traces/synthetic_generator.py`).
  - Baseline coexistence implementations (`Exp 1`, `Exp 2`, `Exp 3`).
  - Reassigned from Divyansh: Cross-Technology Communication channel model
    (`src/cowic/ctc/channel.py`, issue #3) and the metrics calculator
    (`src/cowic/analysis/metrics.py`, issue #9).

- **Divyansh Saxena (`DIVYANSHSAXENA23`):** Temporarily unavailable. His 4 open
  issues (#3, #4, #9, #10) are reassigned above, split 2/2 between Upayan and
  Nitesh by domain overlap with their existing work.

---

## Day 1: October 10, 2026 — Core Engine and Modules

### Milestone 1 (Morning: 09:00 – 13:00) — Foundations and Traffic Engine
- **Task 1.1 (`Nitesh050`):** Implement `traces/synthetic_generator.py`.
  - Deliverable: Generate synthetic WiFi Frame Group traces matching Table 5 parameters (Traffic I and III).
  - Verification: `pytest tests/test_trace_generator.py`.
- **Task 1.2 (`Nitesh050`):** Implement `src/cowic/ctc/channel.py`.
  - Deliverable: WBeacon and ZBeacon frame exchange with configurable packet error rates.
  - Verification: Unit tests in `tests/test_ctc_channel.py`.
- **Task 1.3 (`upayanmazumder`):** Implement `src/cowic/wifi/milp_scheduler.py`.
  - Deliverable: PuLP formulation of Equations 11 through 17 with HiGHS solver backend.
  - Verification: `pytest tests/test_milp_solver.py`.

### Milestone 2 (Afternoon: 14:00 – 18:00) — Protocol State Machines
- **Task 2.1 (`upayanmazumder`):** Implement `src/cowic/zigbee/lwsa_adapter.py` and `coordinator.py`.
  - Deliverable: L-WSA discrete search algorithm and superframe configuration broadcaster.
  - Verification: `pytest tests/test_lwsa_algorithm.py`.
- **Task 2.2 (`Nitesh050`):** Implement `src/cowic/wifi/ap_orchestrator.py`.
  - Deliverable: AP scheduling loop and fallback whitespace expansion logic.
  - Verification: Unit tests verifying state machine transitions.
- **Task 2.3 (`upayanmazumder`):** Implement `src/cowic/sim/channel_medium.py`.
  - Deliverable: Shared 2.4 GHz channel overlap and collision detection.
  - Verification: `pytest tests/test_collision_detector.py`.

### Day 1 Evening Sync (18:30 – 19:30)
- Review open Pull Requests against `main`.
- Merge verified components into the shared integration branch.

---

## Day 2: October 11, 2026 — Integration, Evaluation, and Figures

### Milestone 3 (Morning: 09:00 – 13:00) — End-to-End Simulation Pipeline
- **Task 3.1 (`upayanmazumder`):** Implement `src/cowic/sim/simulation_engine.py`.
  - Deliverable: Complete SimPy closed-loop coordination engine.
  - Verification: `pytest tests/test_end_to_end.py`.
- **Task 3.2 (`Nitesh050`):** Implement baseline execution drivers.
  - Deliverable: Run scripts for Exp 1 (Static) and Exp 2 (Opportunistic).
  - Verification: Assert non-zero packet drop rates for baseline configurations.
- **Task 3.3 (`Nitesh050`):** Implement `src/cowic/analysis/metrics.py`.
  - Deliverable: Compute $G_z$, $PDR_w$, $U_\text{eff}$, jitter, and maximum delay.
  - Verification: Unit tests with precomputed mock transmission records.

### Milestone 4 (Afternoon: 14:00 – 18:00) — Benchmark Runs and Plotting
- **Task 4.1 (`Nitesh050` & `upayanmazumder`):** Execute full experimental sweeps.
  - Deliverable: Run Exp 1 through Exp 6 across Traffic I and Traffic III.
  - Verification: Result CSV files stored under `results/`.
- **Task 4.2 (`upayanmazumder`):** Implement `src/cowic/analysis/plotter.py`.
  - Deliverable: Generate evaluation figures reproducing Figures 11, 14, and 16.
  - Verification: Rendered figures stored in `figures/`.

### Milestone 5 (Evening: 18:30 – 20:00) — Final QA and Delivery
- Execute complete test suite with coverage report: `pytest --cov=src/cowic`.
- Execute static analysis checks: `ruff check .` and `mypy src/ tests/`.
- Verify reproducibility of all figures from scratch.
- Create release tag `v0.1.0`.

---

## Branch and Pull Request Conventions

1. Work in isolated feature branches:
   - `feat/wifi-milp`
   - `feat/zigbee-lwsa`
   - `feat/trace-generator`
   - `feat/sim-engine`
   - `feat/metrics-plotter`
2. Open Pull Requests against `main`.
3. Require at least one peer approval before merging.
4. Keep commits atomic with descriptive commit messages.
