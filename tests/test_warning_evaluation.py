import pandas as pd

from ml.evaluate_warning import forecast_challenge_score, summarise


def test_challenge_score_uses_forecast_columns_only():
    day = pd.DataFrame({
        "p10": [0.0, 0.1, 0.2, 0.0],
        "p50": [0.0, 0.4, 0.1, 0.0],
        "p90": [0.0, 0.8, 0.5, 0.0],
        "actual": [0.0, 0.0, 1.0, 0.0],
    })
    score = forecast_challenge_score(day)
    changed_reference = day.copy()
    changed_reference["actual"] = 999.0
    assert forecast_challenge_score(changed_reference) == score
    assert score > 0


def test_warning_summary_reports_duration_peak_and_classification_metrics():
    rows = [
        {
            "predicted_steps": 4, "reference_steps": 5, "p10_steps": 3, "p90_steps": 6,
            "predicted_peak_pu": 1.11, "reference_peak_pu": 1.12,
            "predicted_start": "10:00", "reference_start": "09:45",
        },
        {
            "predicted_steps": 0, "reference_steps": 0, "p10_steps": 0, "p90_steps": 1,
            "predicted_peak_pu": 1.08, "reference_peak_pu": 1.08,
            "predicted_start": None, "reference_start": None,
        },
    ]
    result = summarise(rows)
    assert result["days"] == 2
    assert result["unsafe_duration_mae_minutes"] == 7.5
    assert result["unsafe_day_precision"] == 1.0
    assert result["unsafe_day_recall"] == 1.0
    assert result["reference_inside_p10_p90_duration_envelope"] == 1.0

