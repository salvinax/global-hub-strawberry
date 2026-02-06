# uploader.py
import os, time, json, gzip, logging, sqlite3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import boto3
from botocore.exceptions import BotoCoreError, ClientError

from db import init_db

LOG = logging.getLogger("uploader")

DB_PATH = os.getenv("DB_PATH", "/var/lib/berrycam/data.db")

# make sure to aws configure before runinng 
S3_BUCKET = os.environ["S3_BUCKET"]
S3_REGION = os.getenv("S3_REGION", "us-east-1")

PFX_SENSORS = os.getenv("S3_PREFIX_SENSORS", "sensors")
PFX_NODES   = os.getenv("S3_PREFIX_NODES", "nodes")

UPLOAD_PERIOD_S = int(os.getenv("UPLOAD_PERIOD_S", "300")) # 5 x 60 s for now

# set up aws
s3 = boto3.client("s3", region_name=S3_REGION)

# round down 
def floor_window(ts: int, period: int) -> int:
    return (ts // period) * period

# set file title 
def s3_key(prefix: str, window_start_ts: int) -> str:
    dt = datetime.fromtimestamp(window_start_ts, tz=ZoneInfo("America/New_York"))
    return f"{prefix}/{dt:%Y/%m/%d/%H-%M}.jsonl.gz"

# set 
def fetch_rows(conn, table: str, window_start: int, window_end: int):
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT id, ts, payload
        FROM {table}
        WHERE uploaded = 0 AND ts >= ? AND ts < ?
        ORDER BY ts ASC
        """,
        (window_start, window_end),
    )
    return cur.fetchall()

def mark_uploaded(conn, table: str, ids):
    if not ids:
        return
    cur = conn.cursor()
    cur.execute(
        f"UPDATE {table} SET uploaded = 1 WHERE id IN ({','.join(['?']*len(ids))})",
        ids,
    )

def upload_jsonl_gz(bucket: str, key: str, records: list[dict]):
    blob = b"".join((json.dumps(r, separators=(",", ":")) + "\n").encode("utf-8") for r in records)
    gz = gzip.compress(blob)
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=gz,
        ContentType="application/x-ndjson",
        ContentEncoding="gzip",
    )

def window_upload(conn, table: str, prefix: str, window_start: int, window_end: int) -> int:
    rows = fetch_rows(conn, table, window_start, window_end)
    if not rows:
        return 0

    ids = []
    records = []
    for _id, ts, payload in rows:
        ids.append(_id)
        rec = json.loads(payload)
        rec["_ts_db"] = ts
        records.append(rec)

    key = s3_key(prefix, window_start)
    upload_jsonl_gz(S3_BUCKET, key, records)

    mark_uploaded(conn, table, ids)
    conn.commit()

    LOG.info("Uploaded %d rows from %s to s3://%s/%s", len(ids), table, S3_BUCKET, key)
    return len(ids)

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s: %(message)s")
    init_db(DB_PATH)

    while True:
        now = int(time.time())
        window_start = floor_window(now, UPLOAD_PERIOD_S)

        # upload previous full window
        target_start = window_start - UPLOAD_PERIOD_S
        target_end   = window_start

        try:
            with sqlite3.connect(DB_PATH, timeout=10) as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")

                window_upload(conn, "sensor_samples", PFX_SENSORS, target_start, target_end)
                window_upload(conn, "node_packets",   PFX_NODES,   target_start, target_end)

        except (sqlite3.Error, BotoCoreError, ClientError, json.JSONDecodeError) as e:
            LOG.warning("Upload error (will retry next cycle): %r", e)

        # sleep to next boundary
        now2 = time.time()
        next_tick = floor_window(int(now2), UPLOAD_PERIOD_S) + UPLOAD_PERIOD_S
        time.sleep(max(1, next_tick - now2))

if __name__ == "__main__":
    main()
