"""Security checks on the real API v2 app (P10.7, G5).

The stub-app tests in test_api_v2_base.py cover the middleware alone; these send hostile input through the real
routes: traversal through every parameter that reaches a file, oversize and malformed bodies, error bodies without
stack traces or server paths, CORS, and no secrets in the repository.
"""
import re
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.v2.app import create_app
from backend.v2.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
TRACES = re.compile(r"Traceback|File \"|[A-Za-z]:\\\\|/home/|/usr/lib|site-packages")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    settings = Settings(code_version="sec", results_dir=tmp_path_factory.mktemp("results"), max_body_bytes=10_000)
    return TestClient(create_app(settings), raise_server_exceptions=False)


def no_leak(r):
    assert not TRACES.search(r.text), r.text[:300]
    assert set(r.json()) == {"error"} and set(r.json()["error"]) == {"code", "message", "details"}


@pytest.mark.parametrize("path", [
    "/jobs/..%2F..%2Fetc%2Fpasswd", "/jobs/..%2F..%2Fresults.json", "/jobs/%2e%2e%5cwin.ini",
    "/risk?network=..%2F..%2Fetc%2Fpasswd", "/risk?rule=..%2Fvoltage_rules", "/risk?fix=..%2Fx",
    "/fixes?network=..%5C..%5Cx", "/headroom?rule=..%2F..%2Fx", "/report?network=..%2Fx",
])
def test_traversal_through_route_parameters_is_refused(client, path):
    r = client.get(path)
    assert r.status_code in (404, 422)
    assert "root:" not in r.text and "[extensions]" not in r.text
    no_leak(r)


def test_an_oversize_body_is_refused_before_it_is_parsed(client):
    r = client.post("/whatif", content=b"{" + b" " * 20_000 + b"}", headers={"content-type": "application/json"})
    assert r.status_code == 413
    no_leak(r)


@pytest.mark.parametrize("body", [b"{not json", b"[1, 2, 3]", b'{"changes": "all"}', b'{"adoption": 7}'])
def test_malformed_whatif_bodies_get_the_error_model(client, body):
    r = client.post("/whatif", content=body, headers={"content-type": "application/json"})
    assert r.status_code == 422
    no_leak(r)


def test_too_many_items_in_one_request_are_refused(client):
    r = client.post("/whatif", json={"fixes": [{"id": "fix.volt_var"}] * 7})
    assert r.status_code == 422
    no_leak(r)


def test_unknown_registry_ids_are_refused_with_the_valid_ones(client):
    r = client.post("/whatif", json={"fixes": [{"id": "__import__('os')"}]})
    assert r.status_code == 404 and "fix.volt_var" in r.json()["error"]["details"]["valid"]
    no_leak(r)


def test_connection_check_bounds_are_enforced(client):
    for body in ({"node": -1, "kw": 3}, {"node": 1, "kw": 0}, {"node": 1, "kw": 51}, {"node": 1, "kw": 3, "phase": "D"}):
        r = client.post("/connection-check", json=body)
        assert r.status_code == 422, body
        no_leak(r)


def test_cors_answers_only_the_configured_origins(client):
    ok = client.get("/health", headers={"origin": "http://localhost:5173"})
    bad = client.get("/health", headers={"origin": "https://attacker.example"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in bad.headers


def test_only_get_and_post_are_allowed(client):
    assert client.delete("/rules").status_code == 405
    assert client.put("/whatif", json={}).status_code == 405


SECRET = re.compile(rb"sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|ghp_[A-Za-z0-9]{36}"
                    rb"|AIza[0-9A-Za-z_-]{35}")


def test_the_secret_pattern_catches_the_usual_shapes():
    # built from parts so this file does not match its own scan
    assert SECRET.search(b"key = sk-" + b"a" * 30) and SECRET.search(b"-----BEGIN RSA " + b"PRIVATE KEY-----")
    assert not SECRET.search(b"sk-short and AKIA-not-a-key")


def test_no_secrets_or_env_files_are_tracked():
    files = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout.split(b"\0")
    names = [f.decode() for f in files if f]
    assert not [n for n in names if Path(n).name.startswith(".env")], "an .env file is tracked"
    hits = []
    for name in names:
        path = ROOT / name
        if path.suffix in {".parquet", ".png", ".pdf", ".jpg", ".ico", ".woff2"} or not path.is_file():
            continue
        if path.stat().st_size < 5_000_000 and SECRET.search(path.read_bytes()):
            hits.append(name)
    assert not hits, f"secret-like strings in {hits}"
