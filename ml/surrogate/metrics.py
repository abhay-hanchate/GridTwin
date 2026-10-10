"""Prediction error and screening metrics (requirement 2.8), with every denominator shown."""
from __future__ import annotations

import numpy as np

from ml.surrogate.calibrate import crosses
from ml.surrogate.teacher import Labels

NOMINAL_V = 230.0
CONFIDENCE = 0.95


def truly_unsafe(labels: Labels, vmin_pu: float, vmax_pu: float, vuf_limit: float | None = None) -> np.ndarray:
    """The solver's verdict per state, as engine.violations.evaluate: any limit broken or the solve failed."""
    ext = np.column_stack([labels.extremes(), labels.vuf_pct])
    return ~labels.converged.astype(bool) | crosses(ext, vmin_pu, vmax_pu, vuf_limit)


def miss_bound(misses: int, n: int, confidence: float = CONFIDENCE) -> float | None:
    """One-sided Clopper-Pearson upper bound on the miss rate. With 0 misses in n it is 1 - (1-c)^(1/n) (about 3/n).
    States within a day are correlated, so the bound is optimistic; it is never a guarantee."""
    if n == 0:
        return None
    if misses == 0:
        return float(1 - (1 - confidence) ** (1 / n))
    from scipy.stats import beta
    return float(beta.ppf(confidence, misses + 1, n - misses))


def _err(abs_err: np.ndarray, scale: float = 1.0) -> dict:
    a = np.asarray(abs_err, float)[np.isfinite(abs_err)] * scale
    if not len(a):
        return {"n": 0, "mae": None, "p99": None, "max": None}
    return {"n": int(len(a)), "mae": round(float(a.mean()), 4), "p99": round(float(np.quantile(a, 0.99)), 4),
            "max": round(float(a.max()), 4)}


def regression(pred: np.ndarray, labels: Labels, pred_elements: np.ndarray | None = None,
               n_v: int | None = None) -> dict:
    """Errors on converged states: voltages in volts, loading in percentage points, unbalance in points, neutral in A,
    transformer power in kW."""
    ok = labels.converged.astype(bool)
    true = labels.extremes()[ok]
    p = pred[ok]
    out = {"converged_states": int(ok.sum()),
           "v_max_v": _err(np.abs(p[:, 0] - true[:, 0]), NOMINAL_V), "v_min_v": _err(np.abs(p[:, 1] - true[:, 1]), NOMINAL_V),
           "max_line_loading_pts": _err(np.abs(p[:, 2] - true[:, 2])),
           "trafo_loading_pts": _err(np.abs(p[:, 3] - true[:, 3]))}
    if pred.shape[1] >= 7:
        extras = labels.extras()[ok]
        out.update({"vuf_pts": _err(np.abs(p[:, 4] - extras[:, 0])), "neutral_a": _err(np.abs(p[:, 5] - extras[:, 1])),
                    "trafo_p_kw": _err(np.abs(p[:, 6] - extras[:, 2]))})
    if pred_elements is not None:
        b = int(ok.sum())
        u_true = labels.u_pu[ok].reshape(b, -1)
        out["node_voltage_v"] = _err(np.abs(pred_elements[ok, :n_v] - u_true).ravel(), NOMINAL_V)
        out["line_loading_pts"] = _err(np.abs(pred_elements[ok, n_v:n_v + labels.line_loading_pct.shape[1]]
                                              - labels.line_loading_pct[ok]).ravel())
    return out


def _rate(num: int, den: int):
    return None if den == 0 else round(num / den, 5)


def screening(flagged: np.ndarray, unsafe: np.ndarray) -> dict:
    """`flagged` is the screen's risky (or unsafe) call, `unsafe` the solver's. A false safe is an unsafe state the
    screen let through; a false rejection is a safe state it flagged."""
    flagged, unsafe = np.asarray(flagged, bool), np.asarray(unsafe, bool)
    fs, fr = int((unsafe & ~flagged).sum()), int((~unsafe & flagged).sum())
    tp = int((unsafe & flagged).sum())
    n_unsafe, n_safe, n_pass, n_flag = int(unsafe.sum()), int((~unsafe).sum()), int((~flagged).sum()), int(flagged.sum())
    bound = miss_bound(fs, n_unsafe)
    return {"states": int(len(unsafe)), "truly_unsafe": n_unsafe, "truly_safe": n_safe, "screened_safe": n_pass,
            "screened_risky": n_flag, "unsafe_as_safe": fs, "unsafe_miss_rate": _rate(fs, n_unsafe),
            "miss_rate_upper95": None if bound is None else round(bound, 7),
            "unsafe_among_screened_safe": _rate(fs, n_pass), "false_rejections": fr, "false_rejection_rate": _rate(fr, n_safe),
            "precision": _rate(tp, n_flag), "recall": _rate(tp, n_unsafe)}
