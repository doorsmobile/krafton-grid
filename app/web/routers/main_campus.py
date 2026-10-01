from fastapi import APIRouter, Request

from ..data import need, rm
from ..templating import render

router = APIRouter()


@router.get("/", include_in_schema=False)
def page_main(request: Request):
    return render(request, "main.html", "Main", rm.view("main"))


@router.get("/api/main", tags=["main"], summary="Main dashboard: KPIs, Facility · AI · Cloud cards, racks, incidents")
def api_main():
    return rm.view("main")


@router.get("/campus-aerial", include_in_schema=False)
def page_campus(request: Request):
    return render(request, "campus.html", "Campus Aerial", rm.view("campus"))


@router.get("/api/campus", tags=["main"], summary="Campus master plan: phases, build-out timeline, live hotspots")
def api_campus():
    return rm.view("campus")
