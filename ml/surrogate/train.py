"""Fit the pre-registered candidates (docs/DECISIONS.md, Addition 2) on identical features, splits and labels."""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from ml.surrogate import calibrate, schema
from ml.surrogate.dataset import Split
from ml.surrogate.predict import (FailureModel, LgbmModel, MlpModel, Novelty, RidgeModel, Scaler, elements_from_labels,
                                  outputs_from_elements)

RIDGE_ALPHAS = (0.01, 0.1, 1.0, 10.0)
# Round 4 (docs/DECISIONS.md): wider and longer than round 1 (256/128, 200 epochs, patience 15), which hit its cap.
MLP_HIDDEN, MLP_LR, MLP_BATCH, MLP_L2 = (512, 256, 256), 1e-3, 256, 1e-4
MLP_MAX_EPOCHS, MLP_PATIENCE = 400, 20
LGBM_PARAMS = {"objective": "regression", "num_leaves": 63, "learning_rate": 0.05, "min_data_in_leaf": 20,
               "verbosity": -1, "num_threads": 4, "seed": 7}
LGBM_ROUNDS, LGBM_EARLY = 2000, 50
MIN_FAILURES = 20
NOVELTY_VARIANCE, NOVELTY_QUANTILE = 0.99, 0.999
SEED = 7


@dataclass
class Data:
    x: np.ndarray               # (B, F)
    elements: np.ndarray        # (B, O) every node-phase voltage, line, the transformer and the extras; NaN if failed
    outputs: np.ndarray         # (B, 7) extremes and extras
    converged: np.ndarray       # (B,)
    n_v: int
    n_lines: int
    mode_cols: slice

    @property
    def extremes(self) -> np.ndarray:
        return self.outputs[:, :4]


def mode_slice(n_homes: int, n_battery_nodes: int) -> slice:
    start = 3 * n_homes + 2 + n_battery_nodes
    return slice(start, start + len(schema.MODES))


def battery_slot(nodes: np.ndarray, street_nodes) -> np.ndarray:
    """Index of each state's battery node among the street's declared nodes; -1 for no battery or an unknown node."""
    lookup = {int(n): k for k, n in enumerate(street_nodes)}
    return np.array([lookup.get(int(n), -1) if n >= 0 else -1 for n in nodes], int)


def state_features(states, street: str) -> np.ndarray:
    nodes = schema.battery_nodes(street)
    return schema.features(states.load_kw, states.pv_kw, states.pv_kwp, states.upstream_pu, states.tap_pos,
                           states.battery_kw, battery_slot(states.battery_node, nodes), states.mode, states.topology,
                           len(nodes))


def prepare(split: Split, street: str) -> Data:
    s, lab = split.states, split.labels
    el = elements_from_labels(lab)
    n_v, n_lines = lab.u_pu.shape[1] * 3, lab.line_loading_pct.shape[1]
    return Data(state_features(s, street), el, outputs_from_elements(el, n_v, n_lines), lab.converged.astype(bool),
                n_v, n_lines, mode_slice(s.load_kw.shape[1], len(schema.battery_nodes(street))))


def fit_ridge(train: Data, tune: Data, alphas=RIDGE_ALPHAS) -> tuple[RidgeModel, dict]:
    from sklearn.linear_model import Ridge
    ok, okt = train.converged, tune.converged
    xs, ys = Scaler.fit(train.x[ok]), Scaler.fit(train.elements[ok])
    z, y = xs.apply(train.x[ok]), ys.apply(train.elements[ok])
    zt, yt = xs.apply(tune.x[okt]), ys.apply(tune.elements[okt])
    cols = train.mode_cols
    mode, mode_t = train.x[ok][:, cols].argmax(1), tune.x[okt][:, cols].argmax(1)
    best, scores = None, {}
    for alpha in alphas:
        coef = np.zeros((len(schema.MODES), z.shape[1], y.shape[1]))
        icpt = np.zeros((len(schema.MODES), y.shape[1]))
        for m in range(len(schema.MODES)):
            rows = mode == m
            if rows.sum() < 2:
                continue
            r = Ridge(alpha=alpha).fit(z[rows], y[rows])
            coef[m], icpt[m] = r.coef_.T, r.intercept_
        pred = np.empty_like(yt)
        for m in range(len(schema.MODES)):
            rows = mode_t == m
            pred[rows] = zt[rows] @ coef[m] + icpt[m]
        scores[alpha] = float(np.mean((pred - yt) ** 2))
        if best is None or scores[alpha] < best[0]:
            best = (scores[alpha], RidgeModel(coef, icpt, xs, ys, cols, train.n_v, train.n_lines, alpha))
    return best[1], {"alpha": best[1].alpha, "tune_mse_standardised": scores}


def fit_mlp(train: Data, tune: Data, *, hidden=MLP_HIDDEN, max_epochs=MLP_MAX_EPOCHS, patience=MLP_PATIENCE,
            seed=SEED) -> tuple[MlpModel, dict]:
    import warnings

    from sklearn.exceptions import ConvergenceWarning
    from sklearn.neural_network import MLPRegressor
    ok, okt = train.converged, tune.converged
    xs, ys = Scaler.fit(train.x[ok]), Scaler.fit(train.elements[ok])
    z, y = xs.apply(train.x[ok]), ys.apply(train.elements[ok])
    zt, yt = xs.apply(tune.x[okt]), ys.apply(tune.elements[okt])
    mlp = MLPRegressor(hidden_layer_sizes=hidden, activation="relu", solver="adam", learning_rate_init=MLP_LR,
                       batch_size=MLP_BATCH, alpha=MLP_L2, random_state=seed, shuffle=True)
    best, best_epoch, history, t0 = None, 0, [], time.perf_counter()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConvergenceWarning)
        for epoch in range(1, max_epochs + 1):
            mlp.partial_fit(z, y)
            loss = float(np.mean((mlp.predict(zt) - yt) ** 2))
            history.append(round(loss, 6))
            if best is None or loss < best[0]:
                best, best_epoch = (loss, [w.copy() for w in mlp.coefs_], [b.copy() for b in mlp.intercepts_]), epoch
            elif epoch - best_epoch >= patience:
                break
    model = MlpModel(best[1], best[2], xs, ys, train.n_v, train.n_lines)
    return model, {"best_epoch": best_epoch, "epochs_run": len(history), "tune_mse_standardised": best[0],
                   "history": history, "seconds": round(time.perf_counter() - t0, 1), "device": "cpu",
                   "hidden": list(hidden), "stopped_early": len(history) < max_epochs}


def fit_lgbm(train: Data, tune: Data) -> tuple[LgbmModel, dict]:
    import lightgbm
    ok, okt = train.converged, tune.converged
    boosters, info = [], {}
    for k, name in enumerate(schema.EXTREMES + schema.EXTRAS):
        dtrain = lightgbm.Dataset(train.x[ok], train.outputs[ok, k])
        dtune = lightgbm.Dataset(tune.x[okt], tune.outputs[okt, k], reference=dtrain)
        b = lightgbm.train(LGBM_PARAMS, dtrain, LGBM_ROUNDS, valid_sets=[dtune],
                           callbacks=[lightgbm.early_stopping(LGBM_EARLY, verbose=False)])
        boosters.append(b)
        info[name] = {"trees": b.best_iteration or b.current_iteration()}
    return LgbmModel(boosters), info


def fit_failure(train: Data, tune: Data) -> tuple[FailureModel | None, dict]:
    n_fail = int((~train.converged).sum())
    if n_fail < MIN_FAILURES:
        return None, {"train_failures": n_fail, "model": None,
                      "note": f"fewer than {MIN_FAILURES} solver failures in train: no failure model"}
    import lightgbm
    params = {**LGBM_PARAMS, "objective": "binary"}
    b = lightgbm.train(params, lightgbm.Dataset(train.x, (~train.converged).astype(int)), LGBM_ROUNDS,
                       valid_sets=[lightgbm.Dataset(tune.x, (~tune.converged).astype(int))],
                       callbacks=[lightgbm.early_stopping(LGBM_EARLY, verbose=False)])
    return FailureModel(b), {"train_failures": n_fail, "model": "lightgbm"}


def fit_novelty(train: Data, calibrate_data: Data, variance: float = NOVELTY_VARIANCE,
                quantile: float = NOVELTY_QUANTILE) -> Novelty:
    """Principal components of the standardised train features holding `variance` of their variance; the threshold is
    the `quantile` of the calibrate split's distances (a state farther than that is unsupported)."""
    xs = Scaler.fit(train.x)
    z = xs.apply(train.x)
    _, sing, vt = np.linalg.svd(z - z.mean(axis=0), full_matrices=False)
    var = sing ** 2 / (len(z) - 1)
    k = int(np.searchsorted(np.cumsum(var) / var.sum(), variance) + 1)
    nov = Novelty(xs, vt[:k], np.maximum(var[:k], 1e-12), np.inf)
    nov.threshold = float(np.quantile(nov.distance(calibrate_data.x), quantile))
    return nov


def guard(model, cal: Data) -> dict:
    """Round 4 margins: Mondrian, centred on the decision limits, on converged calibrate states."""
    ok = cal.converged
    return calibrate.fit_guard(model.outputs(cal.x[ok]), cal.outputs[ok], edges=calibrate.limit_edges())


def select(scores: dict[str, dict]) -> tuple[str, str]:
    """The pre-registered rule on development (tune) data: fewest guarded unsafe-as-safe, then the lowest
    false-rejection rate, then the lowest latency; the MLP ships only if it beats ridge on the first two."""
    key = lambda k: (scores[k]["false_safe"], scores[k]["false_rejection_rate"], scores[k]["latency_s"])  # noqa: E731
    best = min(scores, key=key)
    if best == "mlp" and "ridge" in scores and key("mlp")[:2] >= key("ridge")[:2]:
        return "ridge", "the MLP ranked first only on latency and does not beat ridge on the first two criteria"
    return best, "lowest (unsafe-as-safe, false-rejection rate, latency) on tune"
