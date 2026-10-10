"""Solver-labelled operating states (requirements 2.1, 2.6, 2.7), as pre-registered in docs/DECISIONS.md, Addition 2
(round 4).

A family is (date, solar layout, tap, inverter mode, line layout). Its states are every quarter hour of a few
scenarios that the app's own generator draws for that date, with battery power, battery node and curtailment drawn
per state. Development and test families differ in month, layouts and two held-out (tap, mode) combinations, never
only in the random seed. Boundary states are found by bisection near a limit; the out-of-range sets leave the trained
range on purpose. Everything here is simulated: the inputs are modelled scenarios and the labels are the solver's.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass

import numpy as np

from backend.v2 import compute
from engine.fixes import switching
from engine.rules import get_rule
from engine.types import Network
from ml.surrogate import schema
from ml.surrogate.teacher import Labels, StateArrays, solve_states

SPLITS = ("train", "tune", "calibrate", "test")
DEV_MONTHS, DEV_DAYS = (1, 2, 4, 5, 7, 8, 10, 11), (5, 15, 25)
TUNE_MONTHS, CALIBRATE_MONTHS = (1, 4, 7, 10), (2, 5, 8, 11)
TEST_MONTHS, TEST_DAYS = (3, 6, 9, 12), (7, 17)        # round 4: days never used by an earlier test set
YEAR = 2025
TAPS = (0, 1, 2)
HELD_OUT = {(2, "volt_var_watt"), (1, "volt_watt")}
FAMILIES_PER_DATE = 5
N_SCENARIOS = 6
TOPOLOGY_DEAL = (0, 1, 0, 2, 0, 3)                     # half the families on the street as built
PLANNING_LAYOUTS = (0.25, 0.5, 0.75, 1.0)
PLANNING_SHARE = 0.25
ADOPTION_RANGE, KWP_RANGE = (0.2, 1.0), (1.5, 5.0)
BATTERY_SHARE, BATTERY_KW = 0.5, 100.0
CURTAIL_SHARE, KEEP_RANGE = 0.3, (0.2, 1.0)
BOUNDARY_SHARE = 0.4
BOUNDARY_KINDS = ("vmax_up_2005", "vmax_pm10", "vmin_up_2005", "vmin_pm10", "loading")
BOUNDARY_V = 2.0                            # volts either side of a voltage limit
BOUNDARY_LOADING = (95.0, 105.0)            # percent
UPSTREAM_BRACKET = (0.85, 1.15)             # knob range for voltage boundaries, pu
LOAD_SCALE_BRACKET = (0.3, 2.0)             # knob range for loading boundaries
ILLINOIS_STEPS = 5
UPSTREAM_LIMITS = (0.80, 1.20)              # engine.upstream clips every sampled path to this range
OOD_KINDS = ("kwp_double", "load_x4", "upstream_out", "tap_negative", "battery_150", "battery_other_node",
             "phase_map", "layout")


@dataclass(frozen=True)
class Family:
    id: str
    street: str
    split: str
    date: str
    layout: str          # "random" or "planning:<adoption>"
    tap: int
    mode: str
    topology: int
    seed: int


def _seed(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)


def _split_of(month: int, day: int) -> str:
    if month in TEST_MONTHS:
        return "test"
    if day != DEV_DAYS[-1]:
        return "train"
    return "tune" if month in TUNE_MONTHS else "calibrate"


def families(street: str) -> list[Family]:
    """Every family of a street, deterministic. Settings are dealt round-robin from seeded shuffles so each
    (tap, mode) combination, line layout and planning layout appears in its split."""
    combos_all = [(t, m) for t in TAPS for m in schema.MODES]
    out = []
    for part, months, days in (("dev", DEV_MONTHS, DEV_DAYS), ("test", TEST_MONTHS, TEST_DAYS)):
        rng = np.random.default_rng(_seed(street, part, "round4"))
        combos = [c for c in combos_all if part == "test" or c not in HELD_OUT]
        combos = [combos[i] for i in rng.permutation(len(combos))]
        k = 0
        for month in months:
            for day in days:
                date = f"{YEAR}-{month:02d}-{day:02d}"
                for j in range(FAMILIES_PER_DATE):
                    tap, mode = combos[k % len(combos)]
                    planning = rng.random() < PLANNING_SHARE
                    layout = f"planning:{PLANNING_LAYOUTS[k % len(PLANNING_LAYOUTS)]}" if planning else "random"
                    out.append(Family(f"{street}_{date}_{j}", street, _split_of(month, day), date, layout, tap, mode,
                                      TOPOLOGY_DEAL[k % len(TOPOLOGY_DEAL)], _seed(street, date, j, "round4")))
                    k += 1
    return out


def adoption_kwp(net: Network, adoption: float) -> np.ndarray:
    """The street with `adoption` of its homes on solar, spread evenly along it (as compute.planning_street)."""
    chosen = np.zeros(net.n_homes, dtype=bool)
    chosen[np.round(np.linspace(0, net.n_homes - 1, int(round(adoption * net.n_homes)))).astype(int)] = True
    return net.house_kwp * chosen


def layout_kwp(net: Network, layout: str, rng: np.random.Generator) -> np.ndarray:
    """Installed kWp per home: a planning layout, or random homes with random panel sizes."""
    if layout.startswith("planning:"):
        return adoption_kwp(net, float(layout.split(":")[1]))
    n_on = max(1, int(round(rng.uniform(*ADOPTION_RANGE) * net.n_homes)))
    kwp = np.zeros(net.n_homes)
    homes = rng.choice(net.n_homes, size=n_on, replace=False)
    kwp[homes] = rng.uniform(*KWP_RANGE, n_on)
    return kwp


def _value(labels: Labels, kind: np.ndarray) -> np.ndarray:
    """The monitored quantity of each boundary row; a failed solve counts as beyond the limit."""
    ext = labels.extremes()
    vmin_row = (kind == 2) | (kind == 3)
    value = np.where(kind <= 1, ext[:, 0], np.where(vmin_row, ext[:, 1], np.fmax(ext[:, 2], ext[:, 3])))
    return np.where(np.isfinite(value), value, np.where(vmin_row, -np.inf, np.inf))


def _limit(name: str) -> tuple[float, float]:
    rule = get_rule(name.split("_", 1)[1])
    return (rule.vmax_pu if name.startswith("vmax") else rule.vmin_pu), rule.nominal_v


def _targets(kind: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    target = np.empty(len(kind))
    for k, name in enumerate(BOUNDARY_KINDS):
        rows = kind == k
        if name == "loading":
            target[rows] = rng.uniform(*BOUNDARY_LOADING, rows.sum())
        else:
            limit, nominal = _limit(name)
            target[rows] = limit + rng.uniform(-BOUNDARY_V, BOUNDARY_V, rows.sum()) / nominal
    return target


def _in_band(value: np.ndarray, kind: np.ndarray) -> np.ndarray:
    ok = np.zeros(len(kind), bool)
    for k, name in enumerate(BOUNDARY_KINDS):
        rows = kind == k
        if name == "loading":
            ok[rows] = (value[rows] >= BOUNDARY_LOADING[0]) & (value[rows] <= BOUNDARY_LOADING[1])
        else:
            limit, nominal = _limit(name)
            ok[rows] = np.abs(value[rows] - limit) * nominal <= BOUNDARY_V
    return ok


def boundary_states(net: Network, states: StateArrays, rng: np.random.Generator, n: int):
    """States moved to within BOUNDARY_V of a voltage limit or into 95-105% loading, by Illinois bisection on the
    grid voltage (voltage limits) or a demand scale (loading). Rows whose bracket does not straddle the target, or
    that end outside the band, are dropped."""
    if n <= 0:
        return None
    idx = rng.choice(len(states), size=min(n, len(states)), replace=False)
    base = states.take(idx)
    kind = rng.integers(len(BOUNDARY_KINDS), size=len(idx))
    target = _targets(kind, rng)
    volt = kind < 4

    def apply(rows, x):
        s = base.take(rows)
        up = np.where(volt[rows], x, s.upstream_pu)
        scale = np.where(volt[rows], 1.0, x)
        return StateArrays(s.load_kw * scale[:, None], s.pv_kw, s.pv_kwp, up, s.battery_kw, s.tap_pos, s.mode,
                           s.battery_node, s.topology)

    def f(rows, x):
        st = apply(rows, x)
        lab = solve_states(net, st)
        return _value(lab, kind[rows]) - target[rows], st, lab

    rows = np.arange(len(idx))
    lo = np.where(volt, UPSTREAM_BRACKET[0], LOAD_SCALE_BRACKET[0])
    hi = np.where(volt, UPSTREAM_BRACKET[1], LOAD_SCALE_BRACKET[1])
    f_lo, _, _ = f(rows, lo)
    f_hi, _, _ = f(rows, hi)
    ok = np.isfinite(f_lo) & np.isfinite(f_hi) & (np.sign(f_lo) != np.sign(f_hi))
    rows, lo, hi, f_lo, f_hi = rows[ok], lo[ok], hi[ok], f_lo[ok], f_hi[ok]
    if not len(rows):
        return None
    side = np.zeros(len(rows), int)
    for _ in range(ILLINOIS_STEPS):
        x = (lo * f_hi - hi * f_lo) / (f_hi - f_lo)
        fx, st, lab = f(rows, x)
        fx = np.where(np.isfinite(fx), fx, np.sign(fx) * 1e3)
        same_lo = np.sign(fx) == np.sign(f_lo)
        lo, f_lo = np.where(same_lo, x, lo), np.where(same_lo, fx, f_lo)
        hi, f_hi = np.where(same_lo, hi, x), np.where(same_lo, f_hi, fx)
        # Illinois: halve the stale end's value when the same end is kept twice in a row.
        f_hi = np.where(same_lo & (side == 1), f_hi / 2, f_hi)
        f_lo = np.where(~same_lo & (side == -1), f_lo / 2, f_lo)
        side = np.where(same_lo, 1, -1)
    keep = np.flatnonzero(_in_band(_value(lab, kind[rows]), kind[rows]))
    if not len(keep):
        return None
    return st.take(keep), lab.take(keep), kind[rows][keep]


def run_family(net: Network, fam: Family, *, n_scenarios: int = N_SCENARIOS,
               boundary_share: float = BOUNDARY_SHARE) -> dict:
    rng = np.random.default_rng(fam.seed)
    scn = compute.scenarios(fam.date, net, n=n_scenarios, seed=fam.seed % (2 ** 31))
    s, t = scn.shape
    b, h = s * t, net.n_homes
    kwp = layout_kwp(net, fam.layout, rng)
    load = scn.load_kw.reshape(b, h)
    avail = np.minimum(scn.pv_per_kwp.reshape(b, 1) * kwp[None, :], kwp[None, :])
    keep = np.ones((b, 3))
    curtailed = rng.random(b) < CURTAIL_SHARE
    keep[curtailed] = rng.uniform(*KEEP_RANGE, (curtailed.sum(), 3))
    battery, node = np.zeros(b), np.full(b, -1)
    if fam.mode == "fixed_pf":
        on = rng.random(b) < BATTERY_SHARE
        battery[on] = rng.uniform(-BATTERY_KW, BATTERY_KW, on.sum())
        node[on] = rng.choice(schema.battery_nodes(fam.street), size=on.sum())
    states = StateArrays(load, avail * keep[:, net.house_phase], np.tile(kwp, (b, 1)), scn.upstream_pu.reshape(b),
                         battery, np.full(b, fam.tap), np.full(b, schema.MODES.index(fam.mode)), node,
                         np.full(b, fam.topology))
    labels = solve_states(net, states)
    parts_s, parts_l, kinds = [states], [labels], [np.full(b, -1)]
    found = boundary_states(net, states, rng, int(round(boundary_share * b)))
    if found is not None:
        parts_s.append(found[0])
        parts_l.append(found[1])
        kinds.append(found[2])
    kind = np.concatenate(kinds)
    return {"family": asdict(fam), "states": StateArrays.concat(parts_s), "labels": Labels.concat(parts_l),
            "boundary": kind >= 0, "boundary_kind": kind, "step": np.r_[np.tile(np.arange(t), s), np.full(len(kind) - b, -1)]}


def out_of_range(net: Network, street: str, base: StateArrays, rng: np.random.Generator, per_kind: int = 250) -> dict:
    """One set per kind of input the surrogate must refuse; each is labelled by the solver on the network it describes."""
    nodes = schema.battery_nodes(street)
    out = {}
    for kind in OOD_KINDS:
        s = base.take(rng.choice(len(base), size=per_kind, replace=len(base) < per_kind))
        n = len(s)
        f = {k: getattr(s, k) for k in ("load_kw", "pv_kw", "pv_kwp", "upstream_pu", "battery_kw", "tap_pos", "mode",
                                         "battery_node", "topology")}
        layouts, use_net = None, net
        if kind == "kwp_double":
            f["pv_kwp"], f["pv_kw"] = f["pv_kwp"] * 2, f["pv_kw"] * 2
        elif kind == "load_x4":
            f["load_kw"] = f["load_kw"] * 4
        elif kind == "upstream_out":
            high = np.arange(n) % 2 == 0
            f["upstream_pu"] = np.where(high, rng.uniform(1.21, 1.25, n), rng.uniform(0.70, 0.78, n))
        elif kind == "tap_negative":
            f["tap_pos"] = np.where(np.arange(n) % 2 == 0, -1, -2)
        elif kind in ("battery_150", "battery_other_node"):
            f["mode"] = np.zeros(n, int)
            size = 150.0 if kind == "battery_150" else 30.0
            f["battery_kw"] = np.where(np.arange(n) % 2 == 0, size, -size)
            other = next(int(x) for x in net.house_node if int(x) not in nodes)
            f["battery_node"] = np.full(n, other if kind == "battery_other_node" else nodes[0])
        elif kind == "phase_map":
            phases = net.house_phase.copy()
            while phases.tolist() == net.house_phase.tolist():
                phases = rng.permutation(net.house_phase)
            use_net = net.with_phases(phases)
            layouts, f["topology"] = [use_net], np.zeros(n, int)
        elif kind == "layout":
            recs = switching.candidates(net)[schema.N_SWITCHED:]
            use_net = next(n2 for rec in recs if (n2 := switching.apply(net, rec)).is_radial())
            layouts, f["topology"] = [use_net], np.zeros(n, int)
        st = StateArrays(**f)
        out[kind] = {"states": st, "labels": solve_states(net, st, layouts=layouts), "network": use_net}
    return out
