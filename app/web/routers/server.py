from fastapi import APIRouter, Request

from ..data import rm
from ..templating import render

router = APIRouter()


@router.get("/server", include_in_schema=False)
def page_server(request: Request):
    return render(request, "server.html", "Server Status", rm.view("server"))


@router.get("/api/server", tags=["server"], summary="This host: CPU · memory · disk · network · service processes · Redis store")
def api_server():
    return rm.view("server")
