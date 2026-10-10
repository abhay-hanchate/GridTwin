"""Fit the pre-registered candidates (docs/DECISIONS.md, Addition 2) on identical features, splits and labels."""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from ml.surrogate import schema
from ml.surrogate.dataset import Split
from ml.surrogate.predict import (FailureModel, LgbmModel, MlpModel, RidgeModel, Scaler, elements_from_labels)

RIDGE_ALPHAS = (0.01, 0.1, 1.0, 10.0)
MLP_HIDDEN, MLP_LR, MLP_BATCH, MLP_L2 = (256, 128), 1e-3, 256, 1e-4
MLP_MAX_EPOCHS, MLP_PATIENCE = 200, 15
LGBM_PARAMS = {"objective": "regression", "num_leaves": 63, "learning_rate": 0.05, "min_data_in_leaf": 20,
               "verbosity": -1, "num_threads": 4, "seed": 7}
LGBM_ROUNDS, LGBM_EARLY = 2000, 50
MIN_FAILURES = 20
SEED = 7


@dataclass
class Data:
    x: np.ndarray               # (B, F)
    elements: np.ndarray        # (B, O) every node-phase voltage, line and the transformer; NaN where the solve failed
    extremes: np.ndarray        # (B, 4)
    converged: np.ndarray       # (B,)
    n_v: int
    n_lines: int


def prepare(split: Split) -> Data:
    s, lab = split.states, split.labels
    x = schema.features(s.load_kw, s.pv_kw, s.pv_kwp, s.upstream_pu, s.tap_pos, s.battery_kw, s.mode)
    el = elements_from_labels(lab.u_pu, lab.line_loading_pct, lab.trafo_loading_pct)
    return Data(x, el, lab.extremes(), lab.converged.astype(bool), lab.u_pu.shape[1] * 3, lab.line_loading_pct.shape[1])


def _mode_cols(n_features: int) -> slice:
    return slice(n_features - len(schema.MODES), n_features)


def fit_ridge(train: Data, tune: Data, alphas=RIDGE_ALPHAS) -> tuple[RidgeModel, dict]:
    from sklearn.linear_model import Ridge
    ok, okt = train.converged, tune.converged
    xs, ys = Scaler.fit(train.x[ok]), Scaler.fit(train.elements[ok])
    z, y = xs.apply(train.x[ok]), ys.apply(train.elements[ok])
    zt, yt = xs.apply(tune.x[okt]), ys.apply(tune.elements[okt])
    cols = _mode_cols(train.x.shape[1])
    mode, mode_t = train.x[ok][:, cols].argmax(1), tune.x[okt][:, cols].argmax(1)
    best = None
    scores = {}
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
                   "history": history, "seconds": round(time.perf_counter() - t0, 1), "device": "cpu"}


def fit_lgbm(train: Data, tune: Data) -> tuple[LgbmModel, dict]:
    import lightgbm
    ok, okt = train.converged, tune.converged
    boosters, info = [], {}
    for k, name in enumerate(schema.EXTREMES):
        dtrain = lightgbm.Dataset(train.x[ok], train.extremes[ok, k])
        dtune = lightgbm.Dataset(tune.x[okt], tune.extremes[okt, k], reference=dtrain)
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
