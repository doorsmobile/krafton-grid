from fastapi import APIRouter, Request

from ..templating import render

router = APIRouter()


@router.get("/developers/api", include_in_schema=False)
def page_api(request: Request):
    return render(request, "developers/api.html", "API Catalog", {})
