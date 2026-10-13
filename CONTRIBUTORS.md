# Contributors

## Team

| Name            | Registration Number | GitHub             |
| --------------- | ------------------- | ------------------ |
| Upayan Mazumder | 24BDS0367           | `upayanmazumder`   |
| Nitesh Pandey   | 24BCB0141           | `Nitesh050`        |
| Divyansh Saxena | 24BCB0108           | `DIVYANSHSAXENA23` |

---

## Presentation Ownership

This distribution matches Review 2.

| Presenter       | Domain               | Focus                                                                  |
| --------------- | -------------------- | ---------------------------------------------------------------------- |
| Upayan Mazumder | Central architecture | System model, CTC link, SimPy engine, shared channel medium, data flow |
| Nitesh Pandey   | WiFi side            | Frame Groups, MILP scheduler, AP orchestrator, baseline Exp 1–3        |
| Divyansh Saxena | ZigBee side          | IEEE 802.15.4 superframe, L-WSA, ZigBee Coordinator                    |

---

## Module Ownership

### Upayan Mazumder — Integration Lead / Central Architecture

- `src/cowic/sim/simulation_engine.py` — SimPy discrete-event simulation engine
- `src/cowic/sim/channel_medium.py` — Shared 2.4 GHz channel collision medium
- `src/cowic/wifi/milp_scheduler.py` — MILP scheduler (Equations 11–17)
- `src/cowic/zigbee/lwsa_adapter.py` — L-WSA discrete search (Algorithm 2)
- `src/cowic/zigbee/coordinator.py` — ZigBee Coordinator state machine
- `src/cowic/analysis/plotter.py` — Publication figure plotter
- Integration: PR review, branch merging, CI maintenance

### Nitesh Pandey — WiFi Side

- `traces/synthetic_generator.py` — Synthetic WiFi Frame Group traces (Table 5)
- `traces/playback.py` — Trace replay and caching
- `src/cowic/wifi/ap_orchestrator.py` — WiFi AP orchestrator state machine
- `src/cowic/wifi/baselines.py` — Baseline schedulers (Exp 1, Exp 2, Exp 3)
- `src/cowic/wifi/fallback.py` — Whitespace fallback expansion
- `src/cowic/ctc/channel.py` — CTC channel model (WBeacon, ZBeacon, PER)
- `src/cowic/analysis/metrics.py` — Performance metrics ($G_z$, $PDR_w$, $U_\text{eff}$)
- `scripts/run_benchmark_sweep.py` — Benchmark experiment sweep runner

### Divyansh Saxena — ZigBee Side

- Architecture review and ZigBee specification input
- Superframe and L-WSA design review
- Test suite design and verification planning
