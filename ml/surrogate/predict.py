"""Surrogate models at inference time: NumPy for ridge and the MLP, LightGBM for the tree model. No PyTorch.

Every model maps features (B, F) to seven outputs (B, 7) in EXTREMES + EXTRAS order: highest and lowest voltage (pu),
worst line and transformer loading (%), voltage unbalance (%), neutral current (A) and transformer power (kW, negative =
reverse flow). Ridge and the MLP predict every element (all node-phase voltages, every line, the transformer and the
three extras) and take the extremes from those. A novelty detector (Mahalanobis distance in the principal components of
the train features) tells the screener when a state is unlike anything it was trained on.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

N_EXTRAS = 3


def outputs_from_elements(elements: np.ndarray, n_v: int, n_lines: int) -> np.ndarray:
    v, line = elements[:, :n_v], elements[:, n_v:n_v + n_lines]
    rest = elements[:, n_v + n_lines:]                       # transformer loading, then the extras
    return np.column_stack([v.max(axis=1), v.min(axis=1), line.max(axis=1), rest[:, 0], rest[:, 1:1 + N_EXTRAS]])


def elements_from_labels(labels) -> np.ndarray:
    b = len(labels.u_pu)
    return np.hstack([labels.u_pu.reshape(b, -1), labels.line_loading_pct, np.asarray(labels.trafo_loading_pct).reshape(b, 1),
                      labels.extras()])


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


class _ElementModel:
    n_v: int
    n_lines: int

    def outputs(self, x: np.ndarray) -> np.ndarray:
        return outputs_from_elements(self.elements(x), self.n_v, self.n_lines)

    def extremes(self, x: np.ndarray) -> np.ndarray:
        return self.outputs(x)[:, :4]


class RidgeModel(_ElementModel):
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

    def arrays(self) -> dict:
        return {"coef": self.coef, "intercept": self.intercept, "x_mean": self.xs.mean, "x_std": self.xs.std,
                "y_mean": self.ys.mean, "y_std": self.ys.std, "mode_cols": [self.mode_cols.start, self.mode_cols.stop],
                "n_v": self.n_v, "n_lines": self.n_lines, "alpha": self.alpha}

    @classmethod
    def from_arrays(cls, a) -> "RidgeModel":
        return cls(a["coef"], a["intercept"], Scaler(a["x_mean"], a["x_std"]), Scaler(a["y_mean"], a["y_std"]),
                   slice(*map(int, a["mode_cols"])), int(a["n_v"]), int(a["n_lines"]), float(a["alpha"]))


class MlpModel(_ElementModel):
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
    """One LightGBM regressor per output (extremes and extras only, no node-level output)."""
    kind = "lgbm"

    def __init__(self, boosters: list):
        self.boosters = boosters

    def outputs(self, x: np.ndarray) -> np.ndarray:
        return np.stack([b.predict(x, num_threads=1) for b in self.boosters], axis=1)

    def extremes(self, x: np.ndarray) -> np.ndarray:
        return self.outputs(x)[:, :4]

    def arrays(self) -> dict:
        return {f"tree{i}": np.array(b.model_to_string()) for i, b in enumerate(self.boosters)}

    @classmethod
    def from_arrays(cls, a) -> "LgbmModel":
        import lightgbm
        n = sum(1 for k in a if k.startswith("tree"))
        return cls([lightgbm.Booster(model_str=str(a[f"tree{i}"])) for i in range(n)])


class FailureModel:
    """Probability that the solver fails to converge (LightGBM classifier)."""

    def __init__(self, booster):
        self.booster = booster

    def proba(self, x: np.ndarray) -> np.ndarray:
        return self.booster.predict(x, num_threads=1)


class Novelty:
    """Mahalanobis distance of standardised features in the principal components holding most of the train variance."""

    def __init__(self, xs: Scaler, components: np.ndarray, variances: np.ndarray, threshold: float):
        self.xs, self.components, self.variances, self.threshold = xs, components, variances, float(threshold)

    def distance(self, x: np.ndarray) -> np.ndarray:
        proj = self.xs.apply(x) @ self.components.T
        return np.sqrt((proj ** 2 / self.variances).sum(axis=1))

    def arrays(self) -> dict:
        return {"mean": self.xs.mean, "std": self.xs.std, "components": self.components.astype(np.float32),
                "variances": self.variances, "threshold": self.threshold}

    @classmethod
    def from_arrays(cls, a) -> "Novelty":
        return cls(Scaler(a["mean"], a["std"]), a["components"].astype(float), a["variances"], float(a["threshold"]))


KINDS = {"ridge": RidgeModel, "mlp": MlpModel, "lgbm": LgbmModel}


def save(path: Path, model, failure: FailureModel | None = None, novelty: Novelty | None = None) -> None:
    arrays = {f"m_{k}": v for k, v in model.arrays().items()}
    if failure is not None:
        arrays["failure_tree"] = np.array(failure.booster.model_to_string())
    if novelty is not None:
        arrays.update({f"n_{k}": v for k, v in novelty.arrays().items()})
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:                          # a file handle keeps the exact name (no added .npz)
        np.savez_compressed(fh, kind=np.array(model.kind), **arrays)


def load(path: Path):
    """(model, failure model or None, novelty detector or None)."""
    with np.load(path, allow_pickle=False) as d:
        model = KINDS[str(d["kind"])].from_arrays({k[2:]: d[k] for k in d.files if k.startswith("m_")})
        failure = novelty = None
        if "failure_tree" in d.files:
            import lightgbm
            failure = FailureModel(lightgbm.Booster(model_str=str(d["failure_tree"])))
        if "n_threshold" in d.files:
            novelty = Novelty.from_arrays({k[2:]: d[k] for k in d.files if k.startswith("n_")})
    return model, failure, novelty
