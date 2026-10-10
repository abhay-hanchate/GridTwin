# Power-flow surrogate: model card (Addition 2, round 4)

Every number below comes from `ml/reports/surrogate_bakeoff.json` and `ml/reports/surrogate_evaluation.json`.
Rounds 1-3 are kept in `ml/reports/surrogate_rounds1-3/`. All states are **simulated**: inputs from the app's own
scenario generator (modelled forecasts, CEEW-based demand analogs), labels from the power-grid-model solver. Every
method change was pre-registered in `docs/DECISIONS.md` ("Addition 2") before it was scored, each round on a test set
never used before.

## What it is

One model per street, for all five streets. The model kind was chosen on tune data by the pre-registered rule:

| Street | Model |
| --- | --- |
| benchmark_250, rural_long_100, rural_weak_63 | MLP 512/256/256, scikit-learn, run in NumPy |
| urban_short_160, suburban_100 | Ridge: there the MLP and LightGBM let unsafe tune states through |

Each model predicts every LV node-phase voltage, every line loading and the transformer loading. It also predicts
voltage unbalance (VUF %), neutral current (A) and transformer power (kW; negative means reverse flow). Each output
gets a calibrated margin.

**It is a screen, not a verdict.** `ml/surrogate/api.py` returns predictions only. Every action called safe anywhere in
GridTwin is solved by the real solver, and a "no safe action" verdict never rests on the screen.

## Supported range (`manifest.json`)

- **The street:** street hash and solver hash checked; the line layout as built plus its first three switching
  candidates (the ones the controller permits); the phase map as built.
- **Battery:** up to 100 kW at any of the street's declared nodes. These are the nodes that were its highest-voltage
  node on 24 sampled days.
- **Settings:** taps 0-2 and the four inverter modes.
- **Values:** each input inside its trained min-max, and a Mahalanobis novelty distance below the 99.9th percentile
  of the calibrate split.
- **Everything else** is `unsupported` and goes to the solver: moved phases, other switched layouts, an ambient
  correction, a battery elsewhere or larger, out-of-range or novel states.
- **Optional VUF limit:** the screen can apply one (`screen(..., vuf_limit=2.0)`).

## Data (`data/surrogate/<street>/manifest.json`, `data/surrogate/splits.json`)

Per street: 160 families of (date, solar layout, tap, mode, line layout). Each has 6 scenarios × 96 quarter hours plus
about 40% near-limit states found by bisection. A quarter of families use the planning solar layouts; the rest use
random homes with 1.5-5 kWp panels. Battery power, battery node and curtailment are drawn per state.

| Split | Months (2025) | States per street |
| --- | --- | --- |
| train | Jan Feb Apr May Jul Aug Oct Nov, days 5 and 15 | about 60,000 |
| tune | Jan Apr Jul Oct, day 25 | about 15,000 |
| calibrate | Feb May Aug Nov, day 25 | about 15,000 |
| test (round 4) | Mar Jun Sep Dec, days 7 and 17 (never used before) | about 30,000 |
| out of range | 8 kinds × 250 | 2,000 |

## Results on the round 4 test set (as deployed: a refused state counts as risky)

**Unsafe states called safe (unseen months):**

| | Benchmark | Rural long | Rural weak | Urban | Suburban |
| --- | --- | --- | --- | --- | --- |
| ±6% | 0 of 12,907 | 0 of 9,939 | 0 of 10,309 | 0 of 8,620 | 13 of 9,299 |
| ±10% | 0 of 4,422 | 0 of 2,967 | 1 of 3,888 | 2 of 2,271 | 0 of 3,380 |
| Near a limit, ±6% | 0 | 2 of 4,958 | 0 | 0 | 8 of 4,945 |

Each count has a one-sided 95% upper bound on the miss rate in the evaluation file. For example, the benchmark's 0 of
12,907 means below 2.3 per 10,000. States within a day are correlated, so the bound is optimistic, and none of this is a
guarantee. Round 3 had zero misses on its two streets, so **round 4 lost that record**.

**Coverage and caution:**

| | Benchmark | Rural long | Rural weak | Urban | Suburban |
| --- | --- | --- | --- | --- | --- |
| Test states accepted | 34% | 72% | 60% | 64% | 49% |
| New solar layouts accepted | 10% | 60% | 47% | 55% | 33% |
| Safe states sent to the solver anyway (±6%) | 90% | 54% | 69% | about 99% | about 99% |
| Accuracy targets met (accepted states) | 2 of 4 | 1 of 4 | 1 of 4 | 0 of 4 | 0 of 4 |
| Node-voltage MAE (accepted) | 0.48 V | 0.64 V | 0.78 V | 3.5 V | 2.6 V |

Unbalance error on accepted states is 0.08-0.25 points. Out-of-range sets were refused in full except "demand × 4"
(160-200 of 250 refused).

## Speed

Per state, on the CPU (`latency`):

| Mode | Screen | Solver | Ratio |
| --- | --- | --- | --- |
| Fixed power factor | about 0.2 ms | about 1.3 ms | about 6-8× |
| Volt/VAR | about 0.2 ms | about 25 ms | about 100-140× |

**End to end it does not pay off yet:**

- **Controller-style battery and curtailment search:** 0.85-0.90× the solver in cost order (slower). Only 2 of 16 runs
  per street had any safe action, and proving "nothing is safe" needs the solver. The chosen action matched solving
  everything in all 80 runs, because the three cheapest actions are always solved.
- **Fix tournament:** 0.99-1.05×, the same best fix in all 40 runs, and no false rejections. The phase optimiser (about
  40 s) and Volt/VAR candidates (about 9 s each) dominate.

## What changed from round 3, honestly

- **Met:** all five streets; switched layouts; seasonal battery nodes; unbalance, neutral and reverse-flow outputs;
  miss bounds; the cheapest actions always solved.
- **Partly met:** accepting new solar layouts (from 10% to 60% depending on the street).
- **Not met:**
  - fewer safe states sent to the solver;
  - tight margins at every limit;
  - an end-to-end speed-up;
  - and zero misses, which round 3 had on its narrower support.

Learning far more variety cost precision.

## Not built

- **A graph neural network:** every street shares one base layout, and only three switched variants are trained.
- **Physics-informed refinement.**
- **PyTorch and the GPU:** the solver behind every label and every check runs only on the CPU.

## Reproduce

```
python -m scripts.surrogate_generate            # about 16 min per street on 10 workers
python -m scripts.surrogate_train               # bake-off and selection on tune; 15-35 min per street
python -m scripts.surrogate_evaluate            # held-out, out of range, latency, end-to-end
```
