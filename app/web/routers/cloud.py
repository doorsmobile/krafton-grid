from fastapi import APIRouter, Request

from ..data import need, rm
from ..templating import render

router = APIRouter()


@router.get("/cloud", include_in_schema=False)
def page_cloud(request: Request):
    return render(request, "cloud/overview.html", "Cloud", rm.view("cloud"))


@router.get("/api/cloud", tags=["cloud"], summary="Cloud overview in fixed order AWS → GCP → NHN with top talkers and bursts")
def api_cloud():
    return rm.view("cloud")


@router.get("/cloud/aws", include_in_schema=False)
def page_aws(request: Request):
    return render(request, "cloud/aws.html", "AWS GPUaaS", rm.view("cloud_aws"))


@router.get("/api/cloud/aws", tags=["cloud"], summary="AWS: EC2 instances, Capacity Blocks, burst jobs")
def api_aws():
    return rm.view("cloud_aws")


@router.get("/cloud/aws/instance/{instance_id}", include_in_schema=False)
def page_aws_instance(request: Request, instance_id: str):
    d = need(rm.entity("aws_instance", instance_id), "instance")
    return render(request, "cloud/aws_instance.html", instance_id, d)


@router.get("/api/cloud/aws/instance/{instance_id}", tags=["cloud"], summary="One EC2 instance")
def api_aws_instance(instance_id: str):
    return need(rm.entity("aws_instance", instance_id), "instance")


@router.get("/cloud/gcp", include_in_schema=False)
def page_gcp(request: Request):
    return render(request, "cloud/gcp.html", "GCP Storage", rm.view("cloud_gcp"))


@router.get("/api/cloud/gcp", tags=["cloud"], summary="GCP: GCS buckets, Persistent Disks, transfer jobs")
def api_gcp():
    return rm.view("cloud_gcp")


@router.get("/cloud/gcp/bucket/{bucket}", include_in_schema=False)
def page_bucket(request: Request, bucket: str):
    d = need(rm.entity("gcp_bucket", bucket), "bucket")
    return render(request, "cloud/gcp_bucket.html", bucket, d)


@router.get("/api/cloud/gcp/bucket/{bucket}", tags=["cloud"], summary="One GCS bucket")
def api_bucket(bucket: str):
    return need(rm.entity("gcp_bucket", bucket), "bucket")


@router.get("/cloud/gcp/disk/{disk_id}", include_in_schema=False)
def page_disk(request: Request, disk_id: str):
    d = need(rm.entity("gcp_disk", disk_id), "disk")
    return render(request, "cloud/gcp_disk.html", disk_id, d)


@router.get("/api/cloud/gcp/disk/{disk_id}", tags=["cloud"], summary="One Persistent Disk")
def api_disk(disk_id: str):
    return need(rm.entity("gcp_disk", disk_id), "disk")


@router.get("/cloud/nhn", include_in_schema=False)
def page_nhn(request: Request):
    return render(request, "cloud/nhn.html", "NHN GPUaaS", rm.view("cloud_nhn"))


@router.get("/api/cloud/nhn", tags=["cloud"], summary="NHN Cloud GPU instances")
def api_nhn():
    return rm.view("cloud_nhn")


@router.get("/cloud/nhn/instance/{instance_id}", include_in_schema=False)
def page_nhn_instance(request: Request, instance_id: str):
    d = need(rm.entity("nhn_instance", instance_id), "instance")
    return render(request, "cloud/nhn_instance.html", instance_id, d)


@router.get("/api/cloud/nhn/instance/{instance_id}", tags=["cloud"], summary="One NHN GPU instance")
def api_nhn_instance(instance_id: str):
    return need(rm.entity("nhn_instance", instance_id), "instance")
