"""Candidate models, export without PyTorch, guard bands, novelty check and screening metrics, on synthetic data."""
import math

import numpy as np
import pytest

from ml.surrogate import calibrate, metrics, predict, schema, train
from ml.surrogate.teacher import Labels

N_V, N_L, H, KB = 6, 3, 2, 2               # two nodes x three phases, three lines, two homes, two battery nodes


def _data(n, seed):
    """Features shaped like schema.features; outputs depend on them nonlinearly but smoothly."""
    rng = np.random.default_rng(seed)
    load, pv = rng.uniform(0, 3, (n, H)), rng.uniform(0, 3, (n, H))
    kwp = np.full((n, H), 3.0)
    up, tap = rng.uniform(0.95, 1.08, n), rng.integers(0, 3, n)
    bat, slot = rng.uniform(-20, 20, n), rng.integers(-1, KB, n)
    mode, topo = rng.integers(0, 4, n), rng.integers(0, 1 + schema.N_SWITCHED, n)
    x = schema.features(load, pv, kwp, up, tap, bat, slot, mode, topo, KB)
    net = (pv - load).sum(axis=1) - np.where(slot >= 0, bat, 0) / 10
    v = up[:, None] + 0.01 * net[:, None] * np.linspace(0.2, 1, N_V)[None, :] - 0.003 * tap[:, None]
    lines = 20 + 8 * np.abs(net)[:, None] * np.array([1.0, 0.7, 0.4])[None, :]
    trafo = 30 + 10 * np.abs(net)
    extras = np.column_stack([0.5 + 0.1 * np.abs(net), 5 + 2 * np.abs(net), -net * 3])
    el = np.hstack([v, lines, trafo[:, None], extras])
    return train.Data(x, el, predict.outputs_from_elements(el, N_V, N_L), np.ones(n, bool), N_V, N_L,
                      train.mode_slice(H, KB))


@pytest.fixture(scope="module")
def sets():
    return _data(3000, 0), _data(800, 1), _data(2000, 2)


def test_feature_layout_puts_the_battery_at_its_node_and_one_hot_codes():
    x = schema.features(np.ones((2, H)), np.zeros((2, H)), np.ones((2, H)), [1.0, 1.0], [0, 2], [10.0, -5.0], [1, -1],
                        [0, 3], [0, 2], KB)
    names = schema.feature_names(H, KB)
    assert x.shape == (2, len(names)) and len(names) == 3 * H + 2 + KB + 4 + 1 + schema.N_SWITCHED
    assert x[0, names.index("battery_kw_at_1")] == 10.0 and x[1, names.index("battery_kw_at_0")] == 0.0
    assert x[1, names.index("mode_volt_var_watt")] == 1 and x[1, names.index("layout_2")] == 1
    assert train.mode_slice(H, KB) == slice(names.index("mode_fixed_pf"), names.index("mode_volt_var_watt") + 1)


def test_ridge_picks_alpha_on_tune_and_round_trips(sets, tmp_path):
    tr, tu, _ = sets
    model, info = train.fit_ridge(tr, tu)
    assert info["alpha"] in train.RIDGE_ALPHAS
    predict.save(tmp_path / "r.npz", model)
    back, failure, novelty = predict.load(tmp_path / "r.npz")
    assert failure is None and novelty is None and back.kind == "ridge"
    np.testing.assert_allclose(back.outputs(tu.x), model.outputs(tu.x))
    assert back.outputs(tu.x).shape == (len(tu.x), 7)
    assert np.abs(model.outputs(tu.x)[:, 0] - tu.outputs[:, 0]).mean() < 0.005


def test_mlp_runs_in_numpy_exactly_like_scikit_learn(sets, tmp_path):
    from sklearn.neural_network import MLPRegressor
    tr, tu, _ = sets
    model, info = train.fit_mlp(tr, tu, hidden=(32, 16), max_epochs=30, patience=5)
    assert 1 <= info["best_epoch"] <= info["epochs_run"] <= 30 and info["device"] == "cpu"
    ref = MLPRegressor(hidden_layer_sizes=(32, 16))
    ref.coefs_, ref.intercepts_ = model.weights, model.biases
    ref.n_layers_, ref.out_activation_, ref.activation = 4, "identity", "relu"
    np.testing.assert_allclose(model.elements(tu.x), model.ys.invert(ref.predict(model.xs.apply(tu.x))), rtol=1e-6, atol=1e-8)
    predict.save(tmp_path / "m.npz", model)
    back, _, _ = predict.load(tmp_path / "m.npz")
    np.testing.assert_allclose(back.outputs(tu.x), model.outputs(tu.x), rtol=1e-5, atol=1e-4)  # float32 weights


def test_lightgbm_predicts_every_output_and_round_trips(sets, tmp_path):
    tr, tu, _ = sets
    model, info = train.fit_lgbm(tr, tu)
    assert set(info) == set(schema.EXTREMES + schema.EXTRAS)
    predict.save(tmp_path / "g.npz", model)
    back, _, _ = predict.load(tmp_path / "g.npz")
    np.testing.assert_allclose(back.outputs(tu.x), model.outputs(tu.x))


def test_failure_model_needs_enough_failures(sets):
    tr, tu, _ = sets
    model, info = train.fit_failure(tr, tu)
    assert model is None and info["train_failures"] == 0


def test_novelty_flags_states_unlike_training_and_round_trips(sets, tmp_path):
    tr, tu, cal = sets
    nov = train.fit_novelty(tr, cal)
    assert (nov.distance(tu.x) <= nov.threshold).mean() > 0.99
    odd = tu.x.copy()
    odd[:, :H] = odd[:, H:2 * H] * 3 + 4              # demand far beyond anything paired with that solar in training
    assert (nov.distance(odd) > nov.threshold).mean() > 0.9
    model, _ = train.fit_ridge(tr, tu)
    predict.save(tmp_path / "n.npz", model, novelty=nov)
    _, _, back = predict.load(tmp_path / "n.npz")
    np.testing.assert_allclose(back.distance(tu.x), nov.distance(tu.x))


def test_conformal_quantile_rank_and_floor():
    assert calibrate.conformal_quantile(np.arange(1, 100), 0.9) == 90.0
    assert calibrate.conformal_quantile(np.array([1.0, 2.0]), 0.99) == math.inf
    assert calibrate.conformal_quantile(-np.ones(50), 0.5) == 0.0


def test_limit_centred_bins_merge_until_each_is_big_enough():
    rng = np.random.default_rng(5)
    n = 20000
    pred = np.column_stack([rng.uniform(0.85, 1.15, n), rng.uniform(0.85, 1.15, n), rng.uniform(0, 150, n),
                            rng.uniform(0, 150, n), rng.uniform(0, 3, n), rng.uniform(0, 30, n), rng.uniform(-50, 50, n)])
    noise = np.where(pred[:, 1:2] < 0.88, 0.05, 0.002) * rng.normal(size=pred.shape)
    g = calibrate.fit_guard(pred, pred + noise, alpha=0.05, edges=calibrate.limit_edges(), min_count=1000)
    for counts in g["bin_counts"]:
        assert min(counts) >= 1000
    assert any(0.94 > e > 0.90 for e in g["edges"][1])               # a cut between the two lower limits survives
    assert calibrate.margin_at(g, 1, 0.94) < 0.01 < calibrate.margin_at(g, 1, 0.86)   # the deep tail stays apart


def test_guard_covers_fresh_exchangeable_states():
    rng = np.random.default_rng(3)
    true = rng.normal(1.0, 0.02, (20000, 7))
    pred = true + rng.normal(0, 0.003, true.shape)
    g = calibrate.fit_guard(pred[:8000], true[:8000], alpha=0.05)
    guarded, _ = calibrate.bounds(pred[8000:], g)
    t = true[8000:]
    covered = (guarded[:, 0] >= t[:, 0]) & (guarded[:, 1] <= t[:, 1]) & (guarded[:, 2] >= t[:, 2]) & (guarded[:, 3] >= t[:, 3])
    assert covered.mean() >= 0.95 - 0.01


def test_decision_is_conservative_and_uses_a_vuf_limit_when_given():
    guard = {"danger": [0.004, 0.004, 2.0, 2.0, 0.2, 1.0, 1.0], "optimistic": [0.004, 0.004, 2.0, 2.0, 0.2, 1.0, 1.0]}
    row = lambda v, load=50.0, vuf=1.0: [v, 1.0, 50, load, vuf, 10, 5]  # noqa: E731
    pred = np.array([row(1.057), row(1.070), row(1.0), row(np.nan), row(1.0, 99), row(1.0, vuf=1.9)])
    d = calibrate.decide(pred, guard, 0.94, 1.06)
    assert d["risky"].tolist() == [True, True, False, True, True, False]
    assert d["clearly_unsafe"].tolist() == [False, True, False, False, False, False]
    d = calibrate.decide(pred, guard, 0.94, 1.06, vuf_limit=2.0)
    assert d["risky"][5] and not d["risky"][2]
    d = calibrate.decide(pred, guard, 0.94, 1.06, p_fail=np.array([0, 0, 0.5, 0, 0, 0]))
    assert d["risky"][2]


def test_margin_at_a_limit_reads_the_bin_that_holds_it():
    g = {"danger": [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0], [7.0, 8.0]], "optimistic": [[0, 0]] * 4,
         "edges": [[1.05], [0.95], [50.0], [50.0]]}
    assert calibrate.margin_at(g, 0, 1.06) == 2.0 and calibrate.margin_at(g, 1, 0.94) == 3.0
    assert calibrate.margin_at({"danger": [0.1, 0.2, 0.3, 0.4]}, 2, 100.0) == 0.3


def test_screening_metrics_show_denominators_and_a_miss_bound():
    unsafe = np.array([1, 1, 0, 0, 0], bool)
    flagged = np.array([1, 0, 1, 0, 0], bool)
    m = metrics.screening(flagged, unsafe)
    assert m["unsafe_as_safe"] == 1 and m["unsafe_miss_rate"] == 0.5 and m["false_rejections"] == 1
    assert "miss_rate_upper95" in m
    assert metrics.screening(np.zeros(2, bool), np.zeros(2, bool))["unsafe_miss_rate"] is None
    assert metrics.miss_bound(0, 30000) == pytest.approx(1 - 0.05 ** (1 / 30000), rel=1e-6)   # about 1 in 10,000
    assert metrics.miss_bound(0, 0) is None and metrics.miss_bound(3, 100) > 0.03


def test_truly_unsafe_counts_solver_failures_and_vuf_when_limited():
    u = np.ones((3, 2, 3))
    u[1, 0, 0] = 1.07
    lab = Labels(u, np.full((3, 2), 10.0), np.full(3, 10.0), np.array([True, True, False]), np.ones(3),
                 np.array([1.0, 1.0, 3.0]), np.zeros(3), np.zeros(3))
    lab.u_pu[2] = np.nan
    assert metrics.truly_unsafe(lab, 0.94, 1.06).tolist() == [False, True, True]
    lab.converged[2] = True
    lab.u_pu[2] = 1.0
    assert metrics.truly_unsafe(lab, 0.94, 1.06, vuf_limit=2.0).tolist() == [False, True, True]


def test_selection_rule_is_the_pre_registered_one():
    m = lambda fs, fr, lat: {"false_safe": fs, "false_rejection_rate": fr, "latency_s": lat}  # noqa: E731
    assert train.select({"ridge": m(3, 0.1, 1e-6), "lgbm": m(1, 0.3, 1e-4), "mlp": m(2, 0.05, 1e-5)})[0] == "lgbm"
    assert train.select({"ridge": m(0, 0.2, 1e-6), "lgbm": m(0, 0.3, 1e-4), "mlp": m(0, 0.1, 1e-5)})[0] == "mlp"
    assert train.select({"ridge": m(0, 0.1, 1e-6), "lgbm": m(0, 0.1, 1e-4), "mlp": m(0, 0.1, 1e-5)})[0] == "ridge"
    kind, why = train.select({"ridge": m(0, 0.1, 1e-4), "lgbm": m(5, 0.0, 1e-6), "mlp": m(0, 0.1, 1e-5)})
    assert kind == "ridge" and "does not beat ridge" in why


def test_a_column_constant_in_training_is_centred_not_blown_up():
    s = predict.Scaler.fit(np.array([[1.0, 0.0], [3.0, 0.0]]))
    assert s.apply(np.array([[2.0, 1.0]]))[0, 1] == 1.0
