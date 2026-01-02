from __future__ import annotations

import os
from typing import Optional

import boto3
from fastapi import APIRouter, Header, HTTPException, Query

from app.schemas.api_contract import DebugAwsWhoAmIResponse, DebugS3HeadResponse
from app.core.config import settings

router = APIRouter()


def _debug_allowed() -> bool:
    env = (settings.app_env or "dev").strip().lower()
    return env != "prod"


def _require_debug_token(x_debug_token: Optional[str]) -> None:
    if not _debug_allowed():
        raise HTTPException(status_code=404, detail="Not Found")
    expected = os.getenv("DEBUG_TOKEN")
    # DEBUG_TOKEN 未設定ならデバッグ機能は無効化（404）
    if not expected:
        raise HTTPException(status_code=404, detail="Not Found")
    if not x_debug_token or x_debug_token != expected:
        raise HTTPException(status_code=403, detail="Forbidden")


def _aws_region() -> str:
    region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    if not region:
        raise HTTPException(status_code=500, detail="AWS_REGION is not set")
    return region


def _s3_bucket() -> str:
    bucket = os.getenv("S3_BUCKET")
    if not bucket:
        raise HTTPException(status_code=500, detail="S3_BUCKET is not set")
    return bucket


@router.get("/_debug/aws-whoami", response_model=DebugAwsWhoAmIResponse)
def aws_whoami(
    x_debug_token: Optional[str] = Header(default=None, alias="X-Debug-Token"),
) -> DebugAwsWhoAmIResponse:
    _require_debug_token(x_debug_token)

    region = _aws_region()
    bucket = os.getenv("S3_BUCKET")

    akid = os.getenv("AWS_ACCESS_KEY_ID", "")
    access_key_prefix = akid[:4] if akid else None

    try:
        sess = boto3.session.Session(region_name=region)
        ident = sess.client("sts").get_caller_identity()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"STS error: {type(e).__name__}")

    return {
        "region": region,
        "bucket": bucket,
        "access_key_prefix": access_key_prefix,
        "caller_identity": {
            "account": ident.get("Account"),
            "arn": ident.get("Arn"),
            "user_id": ident.get("UserId"),
        },
    }


@router.get("/_debug/s3-head", response_model=DebugS3HeadResponse)
def s3_head(
    key: str = Query(..., description="S3 object key"),
    x_debug_token: Optional[str] = Header(default=None, alias="X-Debug-Token"),
) -> DebugS3HeadResponse:
    _require_debug_token(x_debug_token)

    region = _aws_region()
    bucket = _s3_bucket()

    try:
        s3 = boto3.client("s3", region_name=region)
        resp = s3.head_object(Bucket=bucket, Key=key)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"HeadObject error: {type(e).__name__}"
        )

    return {
        "bucket": bucket,
        "region": region,
        "key": key,
        "etag": resp.get("ETag"),
        "content_length": resp.get("ContentLength"),
        "content_type": resp.get("ContentType"),
        "last_modified": str(resp.get("LastModified")),
        "server_side_encryption": resp.get("ServerSideEncryption"),
    }
