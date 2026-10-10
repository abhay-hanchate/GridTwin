"""Candidate models, export without PyTorch, guard bands and screening metrics, on synthetic data."""
import math

import numpy as np
import pytest

from ml.surrogate import calibrate, metrics, predict, schema, train
from ml.surrogate.teacher import Labels

N_V, N_L = 6, 3                      # two nodes x three phases, three lines


def _data(n, seed):
    """Features shaped like schema.features for two homes; outputs depend on them nonlinearly but smoothly."""
    rng = np.random.default_rng(seed)
    load, pv = rng.uniform(0, 3, (n, 2)), rng.uniform(0, 3, (n, 2))
    kwp = np.full((n, 2), 3.0)
    up, tap, bat = rng.uniform(0.95, 1.08, n), rng.integers(0, 3, n), rng.uniform(-20, 20, n)
    mode = rng.integers(0, 4, n)
    x = schema.features(load, pv, kwp, up, tap, bat, mode)
    net = (pv - load).sum(axis=1) - bat / 10
    v = up[:, None] + 0.01 * net[:, None] * np.linspace(0.2, 1, N_V)[None, :] - 0.003 * tap[:, None]
    lines = 20 + 8 * np.abs(net)[:, None] * np.array([1.0, 0.7, 0.4])[None, :]
    trafo = 30 + 10 * np.abs(net)
    el = np.hstack([v, lines, trafo[:, None]])
    ext = predict.extremes_from_elements(el, N_V, N_L)
    return train.Data(x, el, ext, np.ones(n, bool), N_V, N_L)


@pytest.fixture(scope="module")
def sets():
    return _data(3000, 0), _data(800, 1), _data(2000, 2)


def test_ridge_picks_alpha_on_tune_and_round_trips(sets, tmp_path):
    tr, tu, _ = sets
    model, info = train.fit_ridge(tr, tu)
    assert info["alpha"] in train.RIDGE_ALPHAS and set(info["tune_mse_standardised"]) == set(train.RIDGE_ALPHAS)
    predict.save(tmp_path / "r.npz", model)
    back, failure = predict.load(tmp_path / "r.npz")
    assert failure is None and back.kind == "ridge"
    np.testing.assert_allclose(back.extremes(tu.x), model.extremes(tu.x))
    assert np.abs(model.extremes(tu.x)[:, 0] - tu.extremes[:, 0]).mean() < 0.005


def test_mlp_runs_in_numpy_exactly_like_scikit_learn(sets, tmp_path):
    from sklearn.neural_network import MLPRegressor
    tr, tu, _ = sets
    model, info = train.fit_mlp(tr, tu, hidden=(32, 16), max_epochs=30, patience=5)
    assert 1 <= info["best_epoch"] <= info["epochs_run"] <= 30 and info["device"] == "cpu"
    ref = MLPRegressor(hidden_layer_sizes=(32, 16))
    ref.coefs_, ref.intercepts_ = model.weights, model.biases
    ref.n_layers_, ref.out_activation_, ref.activation = 4, "identity", "relu"
    z = model.xs.apply(tu.x)
    np.testing.assert_allclose(model.elements(tu.x), model.ys.invert(ref.predict(z)), rtol=1e-6, atol=1e-8)
    predict.save(tmp_path / "m.npz", model)
    back, _ = predict.load(tmp_path / "m.npz")
    np.testing.assert_allclose(back.extremes(tu.x), model.extremes(tu.x), rtol=1e-5, atol=1e-5)  # float32 weights


def test_lightgbm_predicts_extremes_and_round_trips(sets, tmp_path):
    tr, tu, _ = sets
    model, info = train.fit_lgbm(tr, tu)
    assert set(info) == set(schema.EXTREMES)
    predict.save(tmp_path / "g.npz", model)
    back, _ = predict.load(tmp_path / "g.npz")
    np.testing.assert_allclose(back.extremes(tu.x), model.extremes(tu.x))


def test_failure_model_needs_enough_failures(sets):
    tr, tu, _ = sets
    model, info = train.fit_failure(tr, tu)
    assert model is None and info["train_failures"] == 0


def test_conformal_quantile_rank_and_floor():
    assert calibrate.conformal_quantile(np.arange(1, 100), 0.9) == 90.0           # ceil(100 * 0.9) = 90th smallest
    assert calibrate.conformal_quantile(np.array([1.0, 2.0]), 0.99) == math.inf    # too few states for the level
    assert calibrate.conformal_quantile(-np.ones(50), 0.5) == 0.0                   # never negative


def test_guard_covers_fresh_exchangeable_states():
    rng = np.random.default_rng(3)
    true = rng.normal(1.0, 0.02, (20000, 4))
    pred = true + rng.normal(0, 0.003, true.shape)
    g = calibrate.fit_guard(pred[:8000], true[:8000], alpha=0.05)
    guarded, optimistic = calibrate.bounds(pred[8000:], g)
    t = true[8000:]
    covered = (guarded[:, 0] >= t[:, 0]) & (guarded[:, 1] <= t[:, 1]) & (guarded[:, 2] >= t[:, 2]) & (guarded[:, 3] >= t[:, 3])
    assert covered.mean() >= 0.95 - 0.01
    assert np.all(optimistic[:, 0] <= pred[8000:, 0])


def test_decision_is_conservative():
    guard = {"danger": [0.004, 0.004, 2.0, 2.0], "optimistic": [0.004, 0.004, 2.0, 2.0]}
    pred = np.array([[1.057, 1.0, 50, 50],    # guarded 1.061 > 1.06: risky, not clearly unsafe
                     [1.070, 1.0, 50, 50],    # even the optimistic 1.066 > 1.06: clearly unsafe
                     [1.000, 1.0, 50, 50],    # safe
                     [np.nan, 1.0, 50, 50],   # a non-finite prediction is never safe
                     [1.000, 1.0, 50, 99]])   # loading 99 + 2 > 100: risky
    d = calibrate.decide(pred, guard, 0.94, 1.06)
    assert d["risky"].tolist() == [True, True, False, True, True]
    assert d["clearly_unsafe"].tolist() == [False, True, False, False, False]
    d = calibrate.decide(pred, guard, 0.94, 1.06, p_fail=np.array([0, 0, 0.5, 0, 0]))
    assert d["risky"][2]


def test_screening_metrics_show_denominators():
    unsafe = np.array([1, 1, 0, 0, 0], bool)
    flagged = np.array([1, 0, 1, 0, 0], bool)
    m = metrics.screening(flagged, unsafe)
    assert m["unsafe_as_safe"] == 1 and m["unsafe_miss_rate"] == 0.5 and m["false_rejections"] == 1
    assert m["false_rejection_rate"] == round(1 / 3, 5) and m["unsafe_among_screened_safe"] == round(1 / 3, 5)
    assert metrics.screening(np.zeros(2, bool), np.zeros(2, bool))["unsafe_miss_rate"] is None


def test_truly_unsafe_counts_solver_failures():
    u = np.ones((3, 2, 3))
    u[1, 0, 0] = 1.07
    lab = Labels(u, np.full((3, 2), 10.0), np.full(3, 10.0), np.array([True, True, False]), np.ones(3))
    lab.u_pu[2] = np.nan
    assert metrics.truly_unsafe(lab, 0.94, 1.06).tolist() == [False, True, True]


def test_selection_rule_is_the_pre_registered_one():
    m = lambda fs, fr, lat: {"false_safe": fs, "false_rejection_rate": fr, "latency_s": lat}  # noqa: E731
    # fewest unsafe-as-safe first, even if slower and with more false rejections
    assert train.select({"ridge": m(3, 0.1, 1e-6), "lgbm": m(1, 0.3, 1e-4), "mlp": m(2, 0.05, 1e-5)})[0] == "lgbm"
    # then the lowest false-rejection rate
    assert train.select({"ridge": m(0, 0.2, 1e-6), "lgbm": m(0, 0.3, 1e-4), "mlp": m(0, 0.1, 1e-5)})[0] == "mlp"
    # then latency
    assert train.select({"ridge": m(0, 0.1, 1e-6), "lgbm": m(0, 0.1, 1e-4), "mlp": m(0, 0.1, 1e-5)})[0] == "ridge"
    # the MLP ships only if it beats ridge on the first two
    kind, why = train.select({"ridge": m(0, 0.1, 1e-4), "lgbm": m(5, 0.0, 1e-6), "mlp": m(0, 0.1, 1e-5)})
    assert kind == "ridge" and "does not beat ridge" in why


def test_a_column_constant_in_training_is_centred_not_blown_up():
    s = predict.Scaler.fit(np.array([[1.0, 0.0], [3.0, 0.0]]))
    assert s.apply(np.array([[2.0, 1.0]]))[0, 1] == 1.0


def test_mondrian_guard_is_tight_where_errors_are_small_and_wide_where_they_are_large():
    rng = np.random.default_rng(5)
    n = 40000
    pred = np.column_stack([rng.uniform(0.9, 1.1, n), rng.uniform(0.8, 1.05, n), rng.uniform(0, 120, n), rng.uniform(0, 120, n)])
    noise = np.where(pred[:, 1:2] < 0.9, 0.05, 0.002) * rng.normal(size=(n, 4))       # big errors only at deep under-voltage
    true = pred + noise
    g = calibrate.fit_guard(pred[:20000], true[:20000], alpha=0.05, bins=8)
    assert len(g["edges"][1]) == 7 and np.shape(g["danger"]) == (4, 8)
    lo, hi = np.array([[1.0, 0.85, 50, 50]]), np.array([[1.0, 1.0, 50, 50]])
    m_lo, m_hi = calibrate.margins(lo, g, "danger")[0, 1], calibrate.margins(hi, g, "danger")[0, 1]
    assert m_hi < 0.01 < m_lo                                    # the deep-under-voltage tail no longer widens every state
    guarded, _ = calibrate.bounds(pred[20000:], g)
    t = true[20000:]
    assert ((guarded[:, 1] <= t[:, 1]).mean()) >= 0.95 - 0.01    # still covers, bin by bin under exchangeability
    flat = calibrate.fit_guard(pred[:20000], true[:20000], alpha=0.05)
    assert calibrate.margins(hi, flat, "danger")[0, 1] > m_hi


def test_a_bin_too_small_for_the_level_is_always_risky():
    pred = np.tile([[1.0, 1.0, 10.0, 10.0]], (40, 1)) + np.linspace(0, 0.01, 40)[:, None]
    g = calibrate.fit_guard(pred, pred, alpha=0.005, bins=4)
    assert np.isinf(calibrate.margins(pred[:1], g, "danger")).all()
    assert calibrate.decide(pred[:1], g, 0.9, 1.1)["risky"][0]


def test_margin_at_a_limit_reads_the_bin_that_holds_it():
    g = {"danger": [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0], [7.0, 8.0]], "optimistic": [[0, 0]] * 4,
         "edges": [[1.05], [0.95], [50.0], [50.0]]}
    assert calibrate.margin_at(g, 0, 1.06) == 2.0 and calibrate.margin_at(g, 1, 0.94) == 3.0
    assert calibrate.margin_at({"danger": [0.1, 0.2, 0.3, 0.4]}, 2, 100.0) == 0.3
