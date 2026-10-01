from fastapi import APIRouter, Body, HTTPException, Request

from ..data import rm
from ..templating import render

router = APIRouter()


@router.get("/inventory", include_in_schema=False)
def page_inventory(request: Request):
    return render(request, "operations/inventory.html", "Inventory", rm.view("inventory"))


@router.get("/api/inventory", tags=["operations"], summary="Unified asset inventory (facility + IT), filterable")
def api_inventory(q: str = "", domain: str = ""):
    return rm.inventory(q, domain)


@router.get("/rack-view", include_in_schema=False)
def page_racks(request: Request):
    return render(request, "operations/rack_view.html", "Rack View", rm.view("racks"))


@router.get("/api/racks", tags=["operations"], summary="Every rack in every hall with power, temperature, health")
def api_racks():
    return rm.view("racks")


@router.get("/rack/{rack_id}", include_in_schema=False)
def page_rack(request: Request, rack_id: str):
    d = rm.entity("rack", rack_id.upper())
    if d is None:
        raise HTTPException(404, "rack not found")
    return render(request, "operations/rack.html", f"Rack {d['rack']['id']}", d)


@router.get("/api/rack/{rack_id}", tags=["operations"], summary="Rack elevation: U-by-U nodes, switches, per-GPU state")
def api_rack(rack_id: str):
    d = rm.entity("rack", rack_id.upper())
    if d is None:
        raise HTTPException(404, "rack not found")
    return d


@router.get("/alerts", include_in_schema=False)
def page_alerts(request: Request):
    return render(request, "operations/alerts.html", "Alerts", rm.view("alerts"),
                  focus=request.query_params.get("focus"), incident=request.query_params.get("incident"))


@router.get("/api/alerts", tags=["operations"], summary="Active alerts, incidents, history, MTTA/MTTR")
def api_alerts():
    return rm.view("alerts")


@router.get("/api/incidents", tags=["operations"], summary="Incidents (correlated alert groups) with timelines")
def api_incidents():
    return rm.view("incidents")


@router.post("/api/alerts/{alert_id}/ack", tags=["operations"], summary="Acknowledge an alert")
def api_ack(alert_id: str, payload: dict = Body(default={})):
    return rm.cmd("alerts.ack", id=alert_id, by=(payload or {}).get("by", "operator"))


@router.post("/api/incidents/{incident_id}/ack", tags=["operations"], summary="Acknowledge an incident and all its alerts")
def api_ack_incident(incident_id: str, payload: dict = Body(default={})):
    return rm.cmd("alerts.incident.ack", id=incident_id, by=(payload or {}).get("by", "operator"))


@router.get("/alerts/integrations", include_in_schema=False)
def page_integrations(request: Request):
    return render(request, "operations/integrations.html", "Slack / Webhooks", rm.view("integrations"))


@router.get("/api/alerts/integrations", tags=["operations"], summary="Slack / webhook / PagerDuty integrations and routes")
def api_integrations():
    return rm.view("integrations")


@router.post("/api/alerts/integrations/test", tags=["operations"], summary="Render (and optionally send) a test notification")
def api_integration_test(payload: dict = Body(...)):
    return rm.cmd("alerts.test", target=(payload or {}).get("target", "slack:#grid-alerts"))


@router.post("/api/alerts/integrations/{integration_id}", tags=["operations"], summary="Update an integration (enable, channel map, URL)")
def api_integration_update(integration_id: str, payload: dict = Body(...)):
    return rm.cmd("alerts.integration.update", id=integration_id, patch=payload or {})


@router.get("/api/alerts/deliveries", tags=["operations"], summary="Notification delivery log (Slack Block Kit payloads)")
def api_deliveries(limit: int = 100):
    return {"deliveries": rm.view("deliveries")["deliveries"][:max(1, min(400, limit))]}


@router.get("/alerts/config", include_in_schema=False)
def page_config(request: Request):
    return render(request, "operations/alert_config.html", "Alert Config", rm.view("alert_config"))


@router.get("/api/alerts/config", tags=["operations"], summary="Alert rules (thresholds, durations) and routing")
def api_config():
    return rm.view("alert_config")


@router.post("/api/alerts/config/rule/{rule_id}", tags=["operations"], summary="Update a rule's threshold, duration, severity or enabled flag")
def api_rule_update(rule_id: str, payload: dict = Body(...)):
    return rm.cmd("alerts.rule.update", id=rule_id, patch=payload or {})


@router.post("/api/alerts/config/routes", tags=["operations"], summary="Replace the routing table")
def api_routes_update(payload: dict = Body(...)):
    return rm.cmd("alerts.routes.replace", routes=(payload or {}).get("routes"))
