"""Upload raw landing files to S3, keeping the same partitioned layout.

  local:  data/raw/orders/date=2026-10-07/run_<id>.jsonl
  S3:     s3://<bucket>/raw/orders/date=2026-10-07/run_<id>.jsonl

Enabled only when S3_BUCKET is set in .env, so the extractor still works locally
without AWS.

Idempotent: an object that already exists in S3 with the same size is skipped,
so re-running a sync never duplicates or re-uploads data.

Standalone use (upload everything already on disk, e.g. the first full load):
  python -m extractor.s3_upload --sync
"""
import argparse, os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
RAW_ROOT = Path("data") / "raw"
BUCKET = os.environ.get("S3_BUCKET", "").strip()
PREFIX = "raw"


def enabled():
    return bool(BUCKET)


def _client():
    import boto3  # imported lazily so the extractor runs without boto3 when S3 is off
    return boto3.client("s3")  # reads AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_DEFAULT_REGION


def s3_key(local_path):
    rel = Path(local_path).resolve().relative_to(RAW_ROOT.resolve())
    return f"{PREFIX}/{rel.as_posix()}"     # forward slashes even on Windows


def upload(local_path, s3=None):
    """Upload one file. Returns 'uploaded' or 'skipped' (already there, same size)."""
    s3 = s3 or _client()
    key = s3_key(local_path)
    size = os.path.getsize(local_path)
    try:
        head = s3.head_object(Bucket=BUCKET, Key=key)
        if head["ContentLength"] == size:
            return "skipped"
    except s3.exceptions.ClientError as e:
        if e.response["Error"]["Code"] not in ("404", "NoSuchKey", "NotFound"):
            raise
    s3.upload_file(str(local_path), BUCKET, key)
    return "uploaded"


def sync_all():
    if not enabled():
        raise SystemExit("S3_BUCKET is not set in .env")
    s3 = _client()
    files = sorted(p for p in RAW_ROOT.rglob("*") if p.is_file() and not p.name.endswith(".tmp"))
    counts = {"uploaded": 0, "skipped": 0}
    for p in files:
        result = upload(p, s3)
        counts[result] += 1
        print(f"  {result:8} s3://{BUCKET}/{s3_key(p)}")
    print(f"\nSync done: {counts['uploaded']} uploaded, {counts['skipped']} already in S3")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sync", action="store_true", help="upload all local raw files")
    if ap.parse_args().sync:
        sync_all()
    else:
        ap.print_help()