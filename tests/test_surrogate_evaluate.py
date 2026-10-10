"""The evaluation script's own logic: contract conversion, action order, gates and the summaries."""
import numpy as np

from ml.surrogate.teacher import StateArrays
from scripts import surrogate_evaluate as ev


def test_states_convert_to_the_contract_with_their_layout_and_battery_node():
    s = StateArrays(np.ones((2, 3)), np.zeros((2, 3)), np.full((2, 3), 3.0), np.array([1.0, 1.02]), np.array([0.0, 20.0]),
                    np.array([0, 1]), np.array([0, 1]), np.array([-1, 31]), np.array([0, 1]))
    layouts = [[[0, 1], [1, 2]], [[0, 1], [0, 2]]]
    out = ev.to_operating_states("rural_weak_63", s, layouts)
    assert out[0].battery_node is None and out[1].battery_node == 31
    assert out[1].inverter_mode == "volt_var" and out[1].tap_pos == 1
    assert out[0].line_ends == ((0, 1), (1, 2)) and out[1].line_ends == ((0, 1), (0, 2))


def test_actions_are_tried_least_curtailment_first_then_least_battery():
    acts = ev._e1_actions()
    assert acts[0] == (0.0, 1.0) and len(acts) == len(ev.E1_BATTERY) * len(ev.E1_KEEP)
    assert [k for _, k in acts] == sorted((k for _, k in acts), reverse=True)


def test_the_cheapest_actions_are_solved_whatever_the_screen_says():
    risky = np.array([True, True, False, True, False, True])
    order = ev.e1_order(risky, always=3)
    assert order[:3] == [0, 1, 2] and order == [0, 1, 2, 4, 3, 5]
    assert sorted(order) == list(range(len(risky)))


def test_gates_fail_visibly():
    reg = {"node_voltage_v": {"mae": 0.3, "p99": 2.5}, "line_loading_pts": {"mae": 1.0, "p99": 4.0}}
    g = ev.gates(reg)
    assert g["voltage_mae_v"]["passed"] and not g["voltage_p99_v"]["passed"] and g["loading_p99_pts"]["passed"]


def test_end_to_end_summary_counts_speed_and_quality():
    row = {"seconds": {"solve_all": 4.0, "solver_in_cost_order": 2.0, "screen_then_verify": 1.0},
           "solver_states": {"solve_all": 100, "solver_in_cost_order": 40, "screen_then_verify": 10},
           "same_choice_as_solve_all": True, "false_rejections": 1, "screened_safe_but_unsafe": 0, "overrules": [],
           "truly_safe_actions": 2, "battery_node_trained": False}
    s = ev._summary_e1([row, row])
    assert s["speedup_vs_solve_all"] == 4.0 and s["speedup_vs_cost_order"] == 2.0 and s["false_rejections"] == 2
    assert s["runs_with_a_safe_action"] == 2 and s["battery_node_untrained_runs"] == 2
