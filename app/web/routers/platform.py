import time

import markdown
from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from ... import config
from ..data import rm
from ..templating import render

router = APIRouter()


@router.get("/platform/tech-spec", include_in_schema=False)
def page_tech(request: Request):
    return render(request, "platform/tech_spec.html", "Tech Spec", rm.view("tech_spec"))


@router.get("/api/platform/tech-spec", tags=["platform"], summary="Stack, physical model, data path, code map")
def api_tech():
    return rm.view("tech_spec")


@router.get("/platform/vendors", include_in_schema=False)
def page_vendors(request: Request):
    return render(request, "platform/vendors.html", "Vendors & API", rm.view("vendors"))


@router.get("/api/vendors", tags=["platform"], summary="Vendor catalog (Facility · IT · Cloud AWS → GCP → NHN) with health")
def api_vendors():
    return rm.view("vendors")


@router.get("/api/vendor/{vendor_id}/sample", tags=["platform"], summary="Probe via the collector — payload shaped like the vendor's real API")
def api_vendor_sample(vendor_id: str):
    return rm.cmd("vendor.sample", id=vendor_id)


def _simulation() -> dict:
    return {**rm.view("simulation"), "redis": rm.store.browse(40), "meta": rm.meta() or {}}


@router.get("/platform/simulation", include_in_schema=False)
def page_sim(request: Request):
    return render(request, "platform/simulation.html", "Simulation", _simulation(), run=request.query_params.get("run"))


@router.get("/api/sim", tags=["simulation"], summary="Simulator state: mode, scenarios (catalog, active, history), store keys")
def api_sim():
    return _simulation()


@router.post("/api/sim/mode", tags=["simulation"], summary="Set mode: normal | stress | maintenance | failover")
def api_mode(payload: dict = Body(...)):
    return rm.cmd("sim.mode", mode=(payload or {}).get("mode", "normal"))


@router.post("/api/sim/scenario/{scenario_id}/start", tags=["simulation"], summary="Start a named failure / load scenario")
def api_scenario_start(scenario_id: str, payload: dict = Body(default={})):
    return rm.cmd("sim.scenario.start", id=scenario_id, duration_s=(payload or {}).get("duration_s"))


@router.post("/api/sim/scenario/{scenario_id}/stop", tags=["simulation"], summary="Stop a running scenario")
def api_scenario_stop(scenario_id: str):
    return rm.cmd("sim.scenario.stop", id=scenario_id)


@router.post("/api/sim/alert", tags=["simulation"], summary="Inject a manual alert (fans out to Slack / webhooks)")
def api_inject(payload: dict = Body(...)):
    p = payload or {}
    return rm.cmd("sim.alert.inject", severity=p.get("severity", "warning"), category=p.get("category", "platform"),
                  title=p.get("title") or "", text=p.get("text") or "", entities=p.get("entities", ""))


@router.post("/api/sim/alert/clear", tags=["simulation"], summary="Resolve all manually injected alerts")
def api_inject_clear():
    return rm.cmd("sim.alert.clear")


@router.get("/api/sim/redis", tags=["simulation"], summary="Browse the store (dcim:aidc100:claude:*) — what the web tier reads")
def api_redis():
    return rm.store.browse(200)


@router.get("/api/sim/export.json", tags=["simulation"], summary="Full export assembled from the published read models")
def api_export():
    data = {"release": config.RELEASE_NAME, "exported": time.time(), "meta": rm.meta(), "live": rm.live(),
            "alerts": rm.view("alerts")["active"], "incidents": rm.view("incidents")["incidents"],
            "scenarios": rm.view("simulation")["scenarios"], "cost_months": rm.view("cost_months")["months"],
            "budget_requests": rm.view("budget_requests")["requests"]}
    return JSONResponse(data, headers={"Content-Disposition": f'attachment; filename="{config.RELEASE_NAME}-export.json"'})


def _requirements_text() -> str:
    try:
        return config.REQUIREMENTS_MD.read_text(encoding="utf-8")
    except OSError:
        return "# Requirements file missing\n\nExpected at docs/REQUIREMENTS.md"


@router.get("/platform/requirements", include_in_schema=False)
def page_requirements(request: Request):
    text = _requirements_text()
    html = markdown.markdown(text, extensions=["tables", "fenced_code", "toc", "sane_lists"])
    return render(request, "platform/requirements.html", "Requirements", {"html": html, "chars": len(text)})


@router.get("/platform/requirements.md", tags=["platform"], summary="Download the canonical requirements MD")
def requirements_md():
    return PlainTextResponse(_requirements_text(), media_type="text/markdown; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{config.RELEASE_NAME}-REQUIREMENTS.md"'})
