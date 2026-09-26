from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse

from app.config import RELEASE_NAME
from app.sim import engine
from app.web.deps import BASE_DIR, page_ctx, templates

router = APIRouter(tags=["main"])

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    it = engine.get_it_bundle()
    cloud = engine.get_cloud_bundle()
    cost = engine.get_cost_bundle()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        page_ctx(
            "dashboard",
            halls=engine.get_json("halls") or [],
            modules=engine.get_modules(),
            it_summary=it["summary"],
            it_live=it["live"],
            gpu_pods=it["gpu_pods"],
            cloud_live=cloud["live"],
            cost_live=cost["live"],
            cost_trends=cost["trends"],
        ),
    )



@router.get("/campus-aerial", response_class=HTMLResponse)
async def campus_aerial(request: Request):
    return templates.TemplateResponse(
        request,
        "campus_aerial.html",
        page_ctx("campus-aerial"),
    )



@router.get("/campus-aerial/image")
async def campus_aerial_image_download():
    path = BASE_DIR / "static" / "campus" / "campus-aerial.png"
    if not path.exists():
        return JSONResponse({"error": "campus aerial image not found"}, status_code=404)
    return FileResponse(
        path,
        media_type="image/png",
        filename=f"krafton-grid-campus-aerial-{RELEASE_NAME}.png",
    )


