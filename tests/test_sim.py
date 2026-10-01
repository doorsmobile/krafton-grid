from app.sim import topology as T
from app.sim.promql import query as promql, PromQLError
from tests.conftest import advance

import pytest


def test_inventory_matches_spec():
    assert T.GPU_COUNT == 5000 and T.NODE_COUNT == 625 and T.GPU_RACKS == 40
    assert len(T.K8S_NODES) == 30 and T.STORAGE_TOTAL_PB == 100
    assert [m["id"] for m in T.MODULES] == ["M1", "M2", "M3", "M4", "M5"]


def test_physics_is_plausible(eng):
    s = eng.live["site"]
    assert 4.0 < s["it_mw"] < 9.0, s["it_mw"]
    assert 1.08 < s["pue"] < 1.30
    assert eng.live["power"]["redundancy"] == "2N"
    g = eng.live["gpu"]
    assert g["total"] == 5000 and 0 < g["allocated"] <= 5000
    assert g["max_temp"] < 87


def test_cdu_failure_is_causal_and_correlated(eng):
    base = eng.live["cooling"]["row_supply_c"]["A2"]
    eng.run_scenario("cdu-failure")
    advance(eng, 12)
    peak = eng.live["cooling"]["row_supply_c"]["A2"]
    assert peak > base + 5, (base, peak)
    advance(eng, 30)
    cdus = eng.live["cooling"]["cdus"]
    assert cdus["CDU-A2"]["status"] == "failed"
    assert cdus["CDU-AS"]["covering"] == "A2"        # spare took the row over the N+1 manifold
    incs = [i for i in eng.alerts.incident_list(20) if i["status"] != "resolved"]
    assert incs and len(incs[0]["alerts"]) >= 2      # alerts correlated into one incident
    eng.stop_scenario("cdu-failure")
    advance(eng, 60)
    assert eng.live["cooling"]["cdus"]["CDU-A2"]["status"] != "failed"


def test_promql(eng):
    r = promql(eng.tsdb, "topk(3, rack_temp_max_c)", window_s=300)
    assert r["resultType"] == "matrix" and len(r["result"]) == 3
    r = promql(eng.tsdb, "avg by (partition) (node_gpu_util)", window_s=300)
    assert {s["metric"]["partition"] for s in r["result"]} == {"train", "infer", "dev", "batch"}
    assert promql(eng.tsdb, "1 + 2")["result"] == 3
    with pytest.raises(PromQLError):
        promql(eng.tsdb, "sum by (")


def test_logql(eng):
    r = eng.logs.query('{service="slurmd"}', eng.now, window_s=600, limit=5)
    assert r["resultType"] == "streams" and len(r["lines"]) <= 5
    r = eng.logs.query('count_over_time({service="slurmd"}[1m])', eng.now, window_s=600)
    assert r["resultType"] == "matrix"


def test_job_submit_places_or_queues(eng):
    j = eng.submit_job("pubg-ally", "finetune", 8, "unit-test-sft", None)
    assert j["state"] == "PENDING" and j["gpus"] == 64 and j["partition"] == "train"
    advance(eng, 20)
    job = eng.fleet.jobs.get(int(j["id"]))
    assert job is None or job.state in ("RUNNING", "PENDING")
    with pytest.raises(ValueError):
        eng.submit_job("nope", "finetune", 8, None, None)


def test_budget_workflow(eng):
    c = eng.cost
    before = next(i for i in eng.cost.budget(eng.now, eng.monthly())["items"] if i["code"] == "OPX-110")["budget"]
    r = c.create_request({"kind": "increase", "source": "OPX-110", "amount": 1e8, "team": "Infra Ops", "reason": "test", "submit": True}, eng.now)
    assert r["status"] == "submitted"
    for _ in range(3):
        r = c.act(r["id"], "approve", eng.now)
    assert r["status"] == "approved"
    after = next(i for i in eng.cost.budget(eng.now, eng.monthly())["items"] if i["code"] == "OPX-110")["budget"]
    assert after == before + 1e8
    with pytest.raises(ValueError):
        c.act(r["id"], "approve", eng.now)
    with pytest.raises(ValueError):
        c.create_request({"kind": "transfer", "source": "OPX-110", "target": "OPX-110", "amount": 1}, eng.now)


def test_unit_economics_are_sane(eng):
    rows = eng.monthly()
    s = eng.cost.summary(eng.now, rows, eng.gpu_hours_month())
    # straight-line forecast must stay close to last month even right after month rollover
    assert 0.5 < s["forecast"]["dc"] / rows[-2]["dc_total"] < 1.6
    assert 800 < s["unit"]["tco_per_gpu_hr"] < 8000
    assert s["unit"]["tco_per_gpu_hr"] < s["unit"]["aws_b200_per_gpu_hr"]


def test_budget_requests_persist_across_restart(eng):
    from app.sim.cost import Cost
    r = eng.cost.create_request({"kind": "refund", "source": "OPX-220", "amount": 2e7, "team": "FinOps", "reason": "persist"}, eng.now)
    again = Cost(eng.now)                       # a fresh process would load the same store
    assert any(x["id"] == r["id"] for x in again.requests)
