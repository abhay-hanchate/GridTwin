"""Surrogate models at inference time: NumPy for ridge and the MLP, LightGBM for the tree model. No PyTorch.

Every model maps features (B, F) to the four extremes (B, 4) in EXTREMES order: highest and lowest voltage (pu), worst
line and transformer loading (%). Ridge and the MLP predict every element (all node-phase voltages, every line, the
transformer) and take the extremes from those.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np


def extremes_from_elements(elements: np.ndarray, n_v: int, n_lines: int) -> np.ndarray:
    v, line, trafo = elements[:, :n_v], elements[:, n_v:n_v + n_lines], elements[:, n_v + n_lines]
    return np.stack([v.max(axis=1), v.min(axis=1), line.max(axis=1), trafo], axis=1)


def elements_from_labels(u_pu: np.ndarray, line_loading_pct: np.ndarray, trafo_loading_pct: np.ndarray) -> np.ndarray:
    b = len(u_pu)
    return np.hstack([u_pu.reshape(b, -1), line_loading_pct, np.asarray(trafo_loading_pct).reshape(b, 1)])


class Scaler:
    def __init__(self, mean: np.ndarray, std: np.ndarray):
        self.mean, self.std = np.asarray(mean, float), np.maximum(np.asarray(std, float), 1e-6)

    @classmethod
    def fit(cls, x: np.ndarray) -> "Scaler":
        """A column that never varies in training is centred only, so an unseen value cannot blow up by 1/std."""
        std = x.std(axis=0)
        return cls(x.mean(axis=0), np.where(std < 1e-9, 1.0, std))

    def apply(self, x):
        return (x - self.mean) / self.std

    def invert(self, z):
        return z * self.std + self.mean


class RidgeModel:
    """One linear map per inverter mode (a learned sensitivity model), on standardised inputs and outputs."""
    kind = "ridge"

    def __init__(self, coef: np.ndarray, intercept: np.ndarray, xs: Scaler, ys: Scaler, mode_cols: slice,
                 n_v: int, n_lines: int, alpha: float):
        self.coef, self.intercept, self.xs, self.ys = coef, intercept, xs, ys      # coef (M, F, O), intercept (M, O)
        self.mode_cols, self.n_v, self.n_lines, self.alpha = mode_cols, n_v, n_lines, alpha

    def elements(self, x: np.ndarray) -> np.ndarray:
        z = self.xs.apply(x)
        mode = x[:, self.mode_cols].argmax(axis=1)
        out = np.empty((len(x), self.coef.shape[2]))
        for m in np.unique(mode):
            rows = mode == m
            out[rows] = z[rows] @ self.coef[m] + self.intercept[m]
        return self.ys.invert(out)

    def extremes(self, x: np.ndarray) -> np.ndarray:
        return extremes_from_elements(self.elements(x), self.n_v, self.n_lines)

    def arrays(self) -> dict:
        return {"coef": self.coef, "intercept": self.intercept, "x_mean": self.xs.mean, "x_std": self.xs.std,
                "y_mean": self.ys.mean, "y_std": self.ys.std, "mode_cols": [self.mode_cols.start, self.mode_cols.stop],
                "n_v": self.n_v, "n_lines": self.n_lines, "alpha": self.alpha}

    @classmethod
    def from_arrays(cls, a) -> "RidgeModel":
        return cls(a["coef"], a["intercept"], Scaler(a["x_mean"], a["x_std"]), Scaler(a["y_mean"], a["y_std"]),
                   slice(*map(int, a["mode_cols"])), int(a["n_v"]), int(a["n_lines"]), float(a["alpha"]))


class MlpModel:
    """A ReLU multi-layer perceptron exported from scikit-learn: weights and biases run in NumPy."""
    kind = "mlp"

    def __init__(self, weights: list[np.ndarray], biases: list[np.ndarray], xs: Scaler, ys: Scaler, n_v: int, n_lines: int):
        self.weights, self.biases, self.xs, self.ys, self.n_v, self.n_lines = weights, biases, xs, ys, n_v, n_lines

    def elements(self, x: np.ndarray) -> np.ndarray:
        a = self.xs.apply(x)
        for i, (w, b) in enumerate(zip(self.weights, self.biases)):
            a = a @ w + b
            if i < len(self.weights) - 1:
                np.maximum(a, 0.0, out=a)
        return self.ys.invert(a)

    def extremes(self, x: np.ndarray) -> np.ndarray:
        return extremes_from_elements(self.elements(x), self.n_v, self.n_lines)

    def arrays(self) -> dict:
        out = {"n_layers": len(self.weights), "x_mean": self.xs.mean, "x_std": self.xs.std, "y_mean": self.ys.mean,
               "y_std": self.ys.std, "n_v": self.n_v, "n_lines": self.n_lines}
        for i, (w, b) in enumerate(zip(self.weights, self.biases)):
            out[f"w{i}"], out[f"b{i}"] = w.astype(np.float32), b.astype(np.float32)
        return out

    @classmethod
    def from_arrays(cls, a) -> "MlpModel":
        n = int(a["n_layers"])
        return cls([a[f"w{i}"].astype(float) for i in range(n)], [a[f"b{i}"].astype(float) for i in range(n)],
                   Scaler(a["x_mean"], a["x_std"]), Scaler(a["y_mean"], a["y_std"]), int(a["n_v"]), int(a["n_lines"]))


class LgbmModel:
    """Four LightGBM regressors, one per extreme (extremes only, no node-level output)."""
    kind = "lgbm"

    def __init__(self, boosters: list):
        self.boosters = boosters

    def extremes(self, x: np.ndarray) -> np.ndarray:
        return np.stack([b.predict(x, num_threads=1) for b in self.boosters], axis=1)

    def arrays(self) -> dict:
        return {f"tree{i}": np.array(b.model_to_string()) for i, b in enumerate(self.boosters)}

    @classmethod
    def from_arrays(cls, a) -> "LgbmModel":
        import lightgbm
        return cls([lightgbm.Booster(model_str=str(a[f"tree{i}"])) for i in range(4)])


class FailureModel:
    """Probability that the solver fails to converge (LightGBM classifier)."""

    def __init__(self, booster):
        self.booster = booster

    def proba(self, x: np.ndarray) -> np.ndarray:
        return self.booster.predict(x, num_threads=1)


KINDS = {"ridge": RidgeModel, "mlp": MlpModel, "lgbm": LgbmModel}


def save(path: Path, model, failure: FailureModel | None = None) -> None:
    arrays = {f"m_{k}": v for k, v in model.arrays().items()}
    if failure is not None:
        arrays["failure_tree"] = np.array(failure.booster.model_to_string())
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:                          # a file handle keeps the exact name (no added .npz)
        np.savez_compressed(fh, kind=np.array(model.kind), **arrays)


def load(path: Path):
    with np.load(path, allow_pickle=False) as d:
        kind = str(d["kind"])
        model = KINDS[kind].from_arrays({k[2:]: d[k] for k in d.files if k.startswith("m_")})
        failure = None
        if "failure_tree" in d.files:
            import lightgbm
            failure = FailureModel(lightgbm.Booster(model_str=str(d["failure_tree"])))
    return model, failure
