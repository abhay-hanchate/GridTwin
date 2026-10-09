# Bringing your own feeder into GridTwin

GridTwin's planning tools (headroom, connection check, hosting capacity, fix tournament) run on any low-voltage
feeder described by three CSV files, plus optional meter readings. Put them in one folder under `data/onboarding/`
(gitignored) and run:

```bash
python -m scripts.onboard data/onboarding/my_feeder            # validate and summarise
python -m scripts.onboard data/onboarding/my_feeder --purge    # delete the files when done
```

Every problem is reported with its file and line number, all at once.

## Files

| File | Columns | Notes |
| --- | --- | --- |
| `feeder.csv` | `node_id, parent_id, length_m, conductor` | One row per wire segment. The segment leaving the transformer has `parent_id` `DT`. Conductor: `squirrel`, `weasel`, `rabbit`, `racoon` or `dog` (IS 398 Part II ACSR). The feeder must be one radial tree: no loops, no islands. |
| `homes.csv` | `home_id, node_id, phase, kwp` | `phase` is `A`, `B` or `C`; `kwp` is installed rooftop solar (0 for none). |
| `transformer.csv` | `kva, uk_percent` | One row: rating and impedance from the nameplate. |
| `meters.csv` (optional) | `timestamp, home_id, kwh, volts` | Checked for shape only in this version. |

Example `feeder.csv`:

```text
node_id,parent_id,length_m,conductor
n1,DT,40,rabbit
n2,n1,60,rabbit
n3,n2,50,weasel
```

## What is assumed

- Conductor resistance and current rating come from the IS 398 Part II (1996) table.
- Reactance is an estimate (0.29 ohm/km), as in the archetypes.
- Zero-sequence impedance is 3 times positive sequence (unsourced; gate G5 reports the sensitivity).
- Transformer losses are assumed: 1.2% copper, 0.25% iron, with taps of 2.5% per step from -2 to +2.

## Data handling

Files are limited to 10 MB, parsed by pandas only and never executed. They stay on local disk, are never logged,
and `--purge` deletes them. Meter ids are never printed in reports.
