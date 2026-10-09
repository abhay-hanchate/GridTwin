# Model card: power-flow engine

**Status: in use** for every number on the dashboard that describes the street (`engine.solver.DaySolver`, features
A5, C3, C4). Owner: Person A.

**Purpose.** Given a street, a set of scenarios and a set of controls (tap, smart-inverter curves, export limits,
battery, phase moves), compute every home's voltage, every wire's and the transformer's loading, neutral current and
voltage unbalance for all 96 quarter hours, and name the limit that is broken.

**Data.** The street is a benchmark, not a surveyed feeder: SimBench `1-LV-rural2` (96 low-voltage buses, 99 homes,
one 250 kVA transformer) with Indian overhead conductors from IS 398 Part II. Homes are single-phase, spread over
phases A, B and C. `/networks` states what is real and what is assumed for each street.

**Method.** power-grid-model's batch solver: all scenarios and all 96 steps are one batch, solved asymmetrically
(three phases and neutral, as a sequence model). Smart inverters (IEEE 1547 Category B Volt/VAR and Volt/Watt) are a
damped fixed point over whole batches. pandapower runs the same day as a cross-check (gate G1).

**Measured scores** (`data/results/results.json`; reference day 15 May 2019, ±10% rule)

| Gate | Measured | Needed | Result |
|---|---|---|---|
| G1: parity with pandapower | largest voltage difference 0.0005% (0.001 V), transformer loading identical; one day in 0.026 s against 10.49 s (403.6 times faster in the latest run; the factor varies with machine load) | at most 0.1% difference and at least 10 times faster | passed |
| G5: convergence and zero-sequence sensitivity | every step converged in every phase layout and every r0/x0 ratio from 2 to 4; peak voltage 268.4 to 272.6 V across those ratios | at least 99% of steps converge | passed |

What the phase layout does to the peak voltage on that day (`data/results/engine_sensitivity.json`):

| Layout | Peak voltage | Unsafe quarter hours |
|---|---|---|
| Balanced three-phase model (Round 1) | 263.1 V | 26 |
| Homes round-robin over A, B, C (the API default) | 268.9 V | 31 |
| Homes on random phases | 270.5 V | 32 |
| Every home on phase A | 294.1 V | 75 |

The balanced model of Round 1 understated the peak; single-phase homes are the main reason v2 sees more risk.

**Limitations and failure modes.**
- The street is a benchmark adapted to Indian conductors. Line reactance and the zero-sequence ratios are estimates;
  G5 shows how much they move the answer (about 4 V across the tested range).
- Real phase assignments are unknown; the API uses round-robin. A utility's own phase data would replace it
  (onboarding, `docs/ONBOARDING.md`).
- A step that does not converge counts as unsafe ("solver failure"), never as safe.

**Monitoring.** The parity and performance tests run every night (`.github/workflows/nightly.yml`, job
`parity-and-perf`); `/metrics` reports the solver convergence rate.
