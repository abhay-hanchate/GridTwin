"""The application shell (backend/main.py): API v2 mounted under /api/v2 and the built dashboard. Round 1's /api
routes were removed in P10.12; the routes themselves are tested in tests/test_api_v2_*.py."""
import pytest
from fastapi.testclient import TestClient

import backend.main as api

client = TestClient(api.app)


def test_api_v2_is_served_by_the_main_app():
    assert client.get("/api/v2/health").json()["status"] == "ok"
    assert client.get("/api/v2/rules").status_code == 200


@pytest.mark.parametrize("path", ["/api/run", "/api/actions", "/api/grid", "/api/scenarios", "/api/summary",
                                  "/api/fix-sim", "/api/early-warning", "/api/live-forecast", "/api/health"])
def test_round_one_routes_are_gone(path):
    r = client.get(path)
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")       # never the dashboard page


def test_an_unknown_api_path_is_a_json_404_even_with_the_dashboard_built(monkeypatch, tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>GridTwin</title>", encoding="utf-8")
    monkeypatch.setattr(api, "FRONTEND_DIST", tmp_path)
    shell = TestClient(api.create_app())
    assert shell.get("/api/nope").status_code == 404
    page = shell.get("/planning")
    assert page.status_code == 200 and "GridTwin" in page.text
    assert shell.get("/api/v2/health").status_code == 200
