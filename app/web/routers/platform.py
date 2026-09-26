from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse

from app.config import RELEASE_NAME, SIM_INTERVAL_SEC
from app.sim import engine
from app.web.deps import BASE_DIR, page_ctx, templates

router = APIRouter(tags=["platform"])

@router.get("/tech-spec", response_class=HTMLResponse)
async def tech_spec(request: Request):
    from app.config import SIM_INTERVAL_SEC

    return templates.TemplateResponse(
        request,
        "tech_spec.html",
        page_ctx(
            "tech-spec",
            vendors=engine.get_json("vendors") or [],
            site=engine.get_json("site") or {},
            sim_interval=SIM_INTERVAL_SEC,
            cloud=engine.get_cloud_bundle(),
            cost=engine.get_cost_bundle(),
        ),
    )



@router.get("/architecture", response_class=HTMLResponse)
async def architecture_redirect():
    return RedirectResponse(url="/tech-spec", status_code=302)



@router.get("/vendors", response_class=HTMLResponse)
async def vendors(request: Request):
    return templates.TemplateResponse(
        request,
        "vendors.html",
        page_ctx("vendors", vendors=engine.get_json("vendors") or []),
    )



@router.get("/simulation", response_class=HTMLResponse)
async def simulation(request: Request):
    return templates.TemplateResponse(
        request,
        "simulation.html",
        page_ctx("simulation", bundle=engine.dump_simulation_bundle()),
    )


def _requirements_md_path() -> Path:
    return BASE_DIR.parent / "docs" / "REQUIREMENTS.md"



@router.get("/platform/requirements", response_class=HTMLResponse)
async def platform_requirements(request: Request):
    import markdown as md

    path = _requirements_md_path()
    raw = path.read_text(encoding="utf-8") if path.exists() else "# Missing\n\nREQUIREMENTS.md not found."
    html_body = md.markdown(
        raw,
        extensions=["tables", "fenced_code", "toc"],
    )
    return templates.TemplateResponse(
        request,
        "requirements.html",
        page_ctx(
            "requirements",
            md_html=html_body,
            md_path="docs/REQUIREMENTS.md",
            md_bytes=len(raw.encode("utf-8")),
        ),
    )



@router.get("/platform/requirements.md")
async def platform_requirements_download():
    path = _requirements_md_path()
    if not path.exists():
        return JSONResponse({"error": "REQUIREMENTS.md not found"}, status_code=404)
    return FileResponse(
        path,
        media_type="text/markdown; charset=utf-8",
        filename=f"krafton-grid-aidc-requirements-{RELEASE_NAME}.md",
    )



@router.get("/download/requirements.md")
async def download_requirements_alias():
    return RedirectResponse(url="/platform/requirements.md", status_code=302)

