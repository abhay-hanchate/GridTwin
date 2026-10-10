# Power-flow surrogate: model card (Addition 2)

Every number below comes from `ml/reports/surrogate_bakeoff.json` and `ml/reports/surrogate_evaluation.json`.
All states are **simulated**: inputs from the app's own scenario generator (modelled forecasts, CEEW-based demand
analogs), labels from the power-grid-model solver. The method and its three rounds were pre-registered in
`docs/DECISIONS.md` ("Addition 2").

## What it is

One model per street (`benchmark_250/`, `rural_weak_63/`): a scikit-learn MLP (256/128, ReLU), exported to NumPy
(`model.npz`), that predicts every LV node-phase voltage (96 × 3), every line loading (95) and the transformer
loading for one quarter hour. The screen uses the highest and lowest voltage and the worst line and transformer
loading, plus a calibrated margin. The benchmark artifact also carries a LightGBM solver-failure classifier (125
failures in its train split). The weak feeder has none (11 failures, under the pre-registered 20).

**It is a screen, not a verdict.** `ml/surrogate/api.py` returns predictions only. Every action called safe anywhere in
GridTwin is solved by the real solver, and a "no safe action" verdict is never based on the screen.

## Inputs and supported range (`manifest.json`)

- **Inputs:** each home's demand kW, delivered solar kW (before any Volt/Watt cut) and installed kWp; grid voltage
  (pu); tap; battery kW (+ charging, three-phase, unity power factor, at the street's worst node); inverter mode
  (unity power factor, Volt/VAR, Volt/Watt, or both).
- **Supported:** the trained street (street hash and solver hash checked), its line layout and phase map, taps 0–2,
  the four modes, the battery at the trained node, each input inside its trained min–max, and one of the three trained
  solar layouts (25/50/100% adoption, spread as `planning_street` does).
- **Everything else:** `unsupported`, risky, sent to the solver. This covers another street, switching, moved
  phases, an ambient correction, a non-unity fixed power factor or changed inverter rating, a battery elsewhere or
  larger, grid voltage or kWp outside the range, and an untrained solar layout.
- **Never predicted:** voltage unbalance, neutral current, reverse flow.

## Data and splits (`data/surrogate/<street>/manifest.json`, `data/surrogate/splits.json`)

Families are (date, adoption, tap, mode), 6 scenarios × 96 steps each, plus about 30% boundary states (Illinois
bisection to within 2 V of a ±6%/±10% limit, or 95–105% loading). Battery power and curtailment are drawn per state.

| Split | Months (2025) | States per street | Use |
| --- | --- | --- | --- |
| train | Jan Feb Apr May Jul Aug Oct Nov, days 5 and 15 | about 45,000 | fitting |
| tune | Jan Apr Jul Oct, day 25 | about 11,000 | early stopping, selection |
| calibrate | Feb May Aug Nov, day 25 | about 11,000 | margins |
| test | Mar Jun Sep Dec, days 10 and 20 | about 22,400 | rounds 1–2, scored once |
| test_fresh | Mar Jun Sep Dec, days 3 and 27 | about 22,400 | round 3 (shipped), scored once |
| out of range | 8 kinds × 250 | 2,000 | routing check |

Tap 2 with Volt/VAR+Volt/Watt, and tap 1 with Volt/Watt, never appear in development data.

## Rounds

1. **One margin per extreme.** On tune it was safe but rejected most safe states, because the margin was set by
   deep under-voltage errors far from any limit.
2. **Margins by predicted value (Mondrian, 8 bins).** Shipped margins at the ±6% limits:
   - benchmark: 2.6 V (upper), 3.9 V (lower);
   - weak feeder: 1.2 V and 1.6 V.

   At the ±10% lower limit, and at 100% loading, the margins stay wide (15–71 V, 31–43 points), so those decisions
   mostly go to the solver.
3. **Trained solar layouts only.** The first test set showed the per-feature box let an unseen 75% adoption layout
   through. The weak feeder's guarded screen then called 585 of 7,152 unsafe states safe (±6%). Round 3 refuses such
   layouts and was scored on a fresh test set.

## Results on the fresh test set (shipped configuration, as deployed)

| | Benchmark | Weak feeder |
| --- | --- | --- |
| Unsafe states called safe, unseen months (±6%) | 0 of 10,158 | 0 of 7,789 |
| Unsafe states called safe, unseen months (±10%) | 0 of 3,397 | 0 of 2,892 |
| Unsafe states called safe, near a limit (±6% / ±10%) | 0 of 2,929 / 0 of 907 | 0 of 2,954 / 0 of 1,218 |
| Safe states sent to the solver anyway (±6%) | 5,462 of 8,274 | 5,946 of 10,643 |
| Test states the screen accepts | 11,205 of 22,393 | 11,099 of 22,455 |
| Unseen tap/mode combinations accepted | 2,806 | 0 (all fell on the refused 75% layout) |

Accuracy targets: node-voltage MAE ≤ 0.5 V and 99th percentile ≤ 2 V; loading MAE ≤ 2 and 99th percentile ≤ 5 points.

- **On the states the screen accepts, all 4 are met on both streets:**
  - benchmark: 0.31 V MAE, 1.89 V 99th percentile; 0.44 and 2.9 loading points;
  - weak feeder: 0.17 V, 1.00 V; 0.21 and 2.3 points.
- **Over all test states,** including the refused 75% layout, the MLP meets 1 of 4 on each street.

On accepted states alone, safe states the screen still sent to the solver were:

| Street | ±6% | ±10% |
| --- | --- | --- |
| Benchmark | 1,189 of 4,001 | 1,717 of 7,611 |
| Weak feeder | 1,104 of 5,801 | 1,542 of 7,367 |

**Out of range:** every set was refused in full except "demand × 4". There, 169 (benchmark) and 164 (weak feeder) of
250 states were refused. The other 81 and 86 stayed inside the trained range, because light-load hours times four
look like normal evening demand, and they were screened.

## Speed (`latency` in the evaluation file)

Per state, on the CPU:

| Mode | Screen (batch 1,024) | Solver (batch 1,024) | Ratio |
| --- | --- | --- | --- |
| Fixed power factor | about 0.1 ms | about 1 ms | about 10× |
| Volt/VAR | about 0.1 ms | 17–24 ms | about 180–240× |

**End to end it did not pay off in the tested runs.** In the controller-style battery and curtailment search, no
permitted action was safe in 30 of 32 runs, so every action had to be solved anyway. Screen-then-verify was 0.9×
the speed of the solver in cost order. In one weak-feeder run it set aside the cheapest safe action (a false
rejection) and the verified choice curtailed more. Zero unsafe actions passed the screen. The whole-day fix tournament
comparison, with every candidate solved both ways in 8 runs per street (16 in all):

- **Speed:** 1.04× overall (benchmark) and 1.02× (weak feeder).
- **Quality:** 0 false rejections, and the same best fix in all 16 runs.
- **When a safe fix existed:** skipping clearly unsafe candidates saved up to 37% (145 s to 92 s).
- **When none existed:** the skipped candidates were solved as a fallback, which was up to 10% slower.
- **The ceiling:** building the candidate catalogue (envelopes, switching probes) takes 60–100 s per run and cannot be
  screened.

## Disagreement and the solver's response

`ml/reports/surrogate_disagreements.json` logs examples from the held-out states where the bare prediction said safe
and the solver did not. In every logged example the margin had already flagged the state as risky. For instance, on
the benchmark under ±6%:

- predicted highest voltage 243.5 V, just under the 243.8 V limit;
- with the margin, 246.1 V, so risky;
- the solver gave 243.9 V: unsafe and rejected.

No guarded screen let an unsafe state or action through on the fresh test set, in the controller-style runs or in the
tournaments. The overrule path is covered by a labelled fault-injection test (`tests/test_surrogate_fixes.py`).

## Not built

- **A graph neural network:** every street here shares one layout, so its strength, new layouts, could not be tested
  honestly.
- **Physics-informed refinement:** it adds latency to approach what the solver gives in about 2 ms.
- **PyTorch and the GPU:** the MLP trains on the CPU in 4–5 minutes per street.

## Reproduce

```
python -m scripts.surrogate_generate            # ~10 min per street on 8 workers
python -m scripts.surrogate_generate --fresh-test
python -m scripts.surrogate_train               # round 1
python -m scripts.surrogate_train --round2      # round 2 margins, trained layouts in the manifest
python -m scripts.surrogate_evaluate            # held-out, out of range, latency, end-to-end
```
