from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.sim import engine
from app.web.deps import page_ctx, templates

router = APIRouter(tags=["cloud"])


@router.get("/cloud", response_class=HTMLResponse)
async def cloud_overview(request: Request):
    data = engine.get_cloud_overview()
    return templates.TemplateResponse(
        request,
        "cloud.html",
        page_ctx(
            "cloud-overview",
            aws=data["aws"],
            gcp=data["gcp"],
            nhn=data["nhn"],
            aws_talkers=data["aws_talkers"],
            nhn_talkers=data["nhn_talkers"],
            gcp_talkers=data["gcp_talkers"],
            cloud_live=data["live"],
        ),
    )


@router.get("/cloud/aws", response_class=HTMLResponse)
async def cloud_aws(request: Request):
    data = engine.get_cloud_overview()
    return templates.TemplateResponse(
        request,
        "cloud_aws.html",
        page_ctx(
            "cloud-aws",
            provider=data["aws"],
            talkers=data["aws_talkers"],
            cloud_live=data["live"],
        ),
    )


@router.get("/cloud/gcp", response_class=HTMLResponse)
async def cloud_gcp(request: Request):
    data = engine.get_cloud_overview()
    return templates.TemplateResponse(
        request,
        "cloud_gcp.html",
        page_ctx(
            "cloud-gcp",
            provider=data["gcp"],
            talkers=data["gcp_talkers"],
            cloud_live=data["live"],
        ),
    )


@router.get("/cloud/nhn", response_class=HTMLResponse)
async def cloud_nhn(request: Request):
    data = engine.get_cloud_overview()
    return templates.TemplateResponse(
        request,
        "cloud_nhn.html",
        page_ctx(
            "cloud-nhn",
            provider=data["nhn"],
            talkers=data["nhn_talkers"],
            cloud_live=data["live"],
        ),
    )


@router.get("/cloud/aws/instance/{instance_id}", response_class=HTMLResponse)
async def aws_instance_page(request: Request, instance_id: str):
    detail = engine.get_aws_instance_detail(instance_id)
    if not detail:
        return RedirectResponse(url="/cloud/aws", status_code=302)
    return templates.TemplateResponse(
        request,
        "cloud_aws_instance.html",
        page_ctx(
            "cloud-aws",
            instance=detail["instance"],
            provider=detail["provider"],
            series_json=json.dumps(detail["series"]),
        ),
    )


@router.get("/cloud/nhn/instance/{instance_id}", response_class=HTMLResponse)
async def nhn_instance_page(request: Request, instance_id: str):
    detail = engine.get_nhn_instance_detail(instance_id)
    if not detail:
        return RedirectResponse(url="/cloud/nhn", status_code=302)
    return templates.TemplateResponse(
        request,
        "cloud_nhn_instance.html",
        page_ctx(
            "cloud-nhn",
            instance=detail["instance"],
            provider=detail["provider"],
            series_json=json.dumps(detail["series"]),
        ),
    )


@router.get("/cloud/gcp/bucket/{bucket_id}", response_class=HTMLResponse)
async def gcp_bucket_page(request: Request, bucket_id: str):
    detail = engine.get_gcp_bucket_detail(bucket_id)
    if not detail:
        return RedirectResponse(url="/cloud/gcp", status_code=302)
    return templates.TemplateResponse(
        request,
        "cloud_gcp_bucket.html",
        page_ctx(
            "cloud-gcp",
            bucket=detail["bucket"],
            provider=detail["provider"],
            series_json=json.dumps(detail["series"]),
        ),
    )


@router.get("/cloud/gcp/disk/{disk_id}", response_class=HTMLResponse)
async def gcp_disk_page(request: Request, disk_id: str):
    detail = engine.get_gcp_disk_detail(disk_id)
    if not detail:
        return RedirectResponse(url="/cloud/gcp", status_code=302)
    return templates.TemplateResponse(
        request,
        "cloud_gcp_disk.html",
        page_ctx(
            "cloud-gcp",
            disk=detail["disk"],
            provider=detail["provider"],
            series_json=json.dumps(detail["series"]),
        ),
    )
