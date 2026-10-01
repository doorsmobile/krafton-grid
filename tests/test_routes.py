import pathlib

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.web import nav


@pytest.fixture(scope="module")
def client():
    from app.web.data import rm
    with TestClient(app) as c:
        assert rm.wait_ready(60), "collector never published"
        yield c


def test_every_menu_page_renders(client):
    for p in nav.flat_pages():
        r = client.get(p["href"])
        assert r.status_code == 200, (p["href"], r.text[:200])
        assert "grid-claude" in r.headers.get("x-grid-release", "")


def test_every_menu_page_has_api(client):
    from app.web.routers.core import iter_routes
    gets = {r.path for r in iter_routes(app.routes) if "GET" in (getattr(r, "methods", None) or ())}
    for p in nav.flat_pages():
        assert p["api"], p["href"]
        for a in p["api"]:
            assert a in gets or any(a == getattr(r, "path", "") for r in iter_routes(app.routes)), a
            if a in gets and "{" not in a and "stream" not in a:
                assert client.get(a).status_code == 200, a


def test_catalog_and_cloud_order(client):
    c = client.get("/api/catalog").json()
    assert c["release"].startswith("grid-claude-v") and len(c["apis"]) > 50
    assert client.get("/api/cloud").json()["order"] == ["aws", "gcp", "nhn"]


def test_main_has_no_cost_card(client):
    html = client.get("/").text
    for card in ("Power", "Capacity", "Cooling", "GPU", "Kubernetes", "Storage", "AWS", "GCP", "NHN"):
        assert card in html
    src = (pathlib.Path(__file__).resolve().parents[1] / "app" / "templates" / "main.html").read_text()
    assert "/cost" not in src   # Cost lives only in the sidebar, never on the Main 3×3


def test_legacy_redirects(client):
    r = client.get("/fractos", follow_redirects=False)
    assert r.status_code in (307, 308) and r.headers["location"] == "/gpu-platform"
    assert client.get("/api/fractos").status_code == 200


def test_mission_control_offline(client, monkeypatch):
    from app.web import agent
    monkeypatch.setattr(agent, "claude_available", lambda: False)
    r = client.post("/api/observability/agent", json={"question": "지금 문제 있어?"}).json()
    assert r["mode"] == "offline" and r["answer"].startswith("**[") and r["steps"]


def test_commands_round_trip_through_the_store(client):
    r = client.post("/api/gpu-platform/jobs", json={"project": "pubg-ally", "profile": "finetune", "size": 8, "name": "bus-test"})
    assert r.status_code == 200 and r.json()["name"] == "bus-test"
    job = client.get(f"/api/gpu/job/{r.json()['id']}")          # republished before the reply → readable at once
    assert job.status_code == 200 and job.json()["job"]["name"] == "bus-test"
    assert client.post("/api/gpu-platform/jobs", json={"project": "nope"}).status_code == 400
    assert client.post("/api/gpu/node/kg-r99-n99/drain", json={}).status_code == 404


def test_series_and_promql_read_from_store(client):
    s = client.get("/api/series/gpu_temp_c?col=4321&minutes=30").json()   # one column of a 5,000-wide ring
    assert s["points"] and s["labels"]["gpu"].endswith("-g1")
    q = client.post("/api/observability/metrics/query", json={"query": "topk(3, rack_temp_max_c)", "window_minutes": 5}).json()
    assert len(q["result"]) == 3
    logs = client.post("/api/observability/logs/query", json={"query": '{service="slurmd"}', "window_minutes": 10}).json()
    assert logs["resultType"] == "streams"


def test_healthz_reports_the_data_path(client):
    h = client.get("/healthz").json()
    assert h["ok"] and h["store"] == "memory" and h["collector"].startswith("embedded@") and h["data_age_s"] < 15
