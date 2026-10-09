from fastapi.testclient import TestClient

from backend.v2.app import create_app
from backend.v2.settings import Settings


def _client(**overrides) -> TestClient:
    return TestClient(create_app(Settings(code_version="abc1234", **overrides)), raise_server_exceptions=False)


def test_rules_list_every_rule_with_source_and_verification():
    rules = _client().get("/rules").json()
    assert isinstance(rules, list) and {"pm10", "up_2005"} <= {r["id"] for r in rules}
    for r in rules:
        assert r["source"] and r["verification"] in {"primary", "secondary", "unverified"}
    up = next(r for r in rules if r["id"] == "up_2005")
    assert (up["vmin_v"], up["vmax_v"]) == (216.2, 243.8)


def test_health_reports_the_code_version():
    assert _client(env="test").get("/health").json() == {"status": "ok", "version": "abc1234", "env": "test"}


def _make(tmp_path, *, district=True, model=True):
    data, models = tmp_path / "processed", tmp_path / "models"
    (data / "v2").mkdir(parents=True)
    models.mkdir()
    for name in ("load_kw", "pv_kw_per_kwp", "upstream_vm_pu"):
        (data / f"{name}.parquet").write_bytes(b"x")
    if district:
        (data / "v2" / "upstream_vm_pu_mathura.parquet").write_bytes(b"x")
    if model:
        (models / "solar_v2_manifest.json").write_text("{}")
    return {"data_dir": data, "model_dir": models, "results_dir": tmp_path / "results"}


def test_readiness_is_503_and_names_what_is_missing(tmp_path):
    r = _client(**_make(tmp_path, district=False)).get("/readiness")
    assert r.status_code == 503 and r.json()["error"]["code"] == "unavailable"
    assert r.json()["error"]["details"]["checks"]["district_profiles"] is False
    assert "district_profiles" in r.json()["error"]["message"]


def test_readiness_is_200_when_data_and_models_are_present(tmp_path):
    r = _client(**_make(tmp_path)).get("/readiness")
    assert r.status_code == 200 and r.json()["ready"] and r.json()["mode"] == "online"


def test_offline_mode_needs_only_the_precomputed_results(tmp_path):
    c = _client(offline=True, results_dir=tmp_path)
    assert c.get("/readiness").status_code == 503
    (tmp_path / "v2").mkdir()
    (tmp_path / "v2" / "index.json").write_text("{}")
    assert c.get("/readiness").json() == {"ready": True, "mode": "offline", "checks": {"precomputed_results": True}}


def test_metrics_count_requests_by_route_template():
    c = _client()
    c.get("/rules")
    text = c.get("/metrics").text
    assert 'gridtwin_requests_total{route="/rules",status="200"}' in text
    assert "gridtwin_request_seconds_bucket" in text
