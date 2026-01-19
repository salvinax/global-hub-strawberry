import time
import json
import os
import requests
import boto3
from datetime import datetime
import pytz


# on sunday 
# -> set up aws account
# -> add timestamp for each dataset
# -> figure out spectrometer irrandiance
# -> test everything

# import drivers for sensors
from mcp3008_sensors import MCP3008Sensors
from i2c_sensors import I2CSensors
from modbus_sensors import ModbusRTUBus, SN522, SQ522
from spectrometer import StellarNetSpectrometer

AWS_ENDPOINT = "https://YOUR_API_ID.execute-api.YOUR_REGION.amazonaws.com/prod/telemetry"
# AWS_API_KEY = os.getenv("AWS_API_KEY", "")  # or hardcode temp
AWS_API_KEY = ""  # or hardcode temp


DEVICE_ID = "strawberry-globalpcb-01"
POLL_PERIOD_S = 20.0

SPOOL_PATH = "/tmp/telemetry_spool.jsonl"  # local fallback if AWS upload fails

# WRITE TO BACKUP FILE IF SERVER IS DOWN
# one json payload per line
def spool_append(payload: dict):
    with open(SPOOL_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")

def json_default(o):
    # datetime -> ISO string
    if isinstance(o, datetime):
        return o.isoformat()
    # numpy arrays / objects with .tolist()
    if hasattr(o, "tolist"):
        return o.tolist()
    raise TypeError(f"Not JSON serializable: {type(o)}")

# tries ot resend old unsent measurements to AWS
def spool_flush(post_fn, max_lines: int = 50):
    """Try to resend a few old payloads first."""
    if not os.path.exists(SPOOL_PATH):
        return

    # Read up to max_lines, keep the rest
    with open(SPOOL_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()

    if not lines:
        return

    to_send = lines[:max_lines]
    remaining = lines[max_lines:]

    sent = 0
    for line in to_send:
        payload = json.loads(line)
        if post_fn(payload):
            sent += 1
        else:
            # stop on first failure keep the rest unsent
            remaining = to_send[sent:] + remaining
            break

    # Write back remaining
    with open(SPOOL_PATH, "w", encoding="utf-8") as f:
        for line in remaining:
            f.write(line)

# POST TO AWS SERVER
# def post_to_aws(payload: dict) -> bool:
#     """Returns True on success, False on failure."""
#     headers = {"Content-Type": "application/json"}
#     if AWS_API_KEY:
#         headers["x-api-key"] = AWS_API_KEY

#     try:
#         r = requests.post(AWS_ENDPOINT, json=payload, headers=headers, timeout=6)
#         if 200 <= r.status_code < 300:
#             return True
#         print("AWS HTTP error:", r.status_code, r.text[:200])
#         return False
#     except Exception as e:
#         print("AWS post exception:", e)
#         return False

def post_to_aws(payload: dict) -> bool: 

    if boto3 is None:
        raise RuntimeError("boto3 not installed. pip install boto3")

    s3 = boto3.client("s3")
    s3 = boto3.resource('s3',
         aws_access_key_id='',
         aws_secret_access_key= AWS_API_KEY)
    BUCKET_NAME = "strawberry-lysimeter-data"
    # s3.put_object(
    # Bucket="strawberry-lysimeter-data",
    # Key=AWS_API_KEY,
    # Body=json.dumps(payload, default=json_default).encode("utf-8"),
    # ContentType="application/json",
    # )

    data = json.dumps(payload, default=json_default).encode("utf-8")
    s3.Bucket(BUCKET_NAME).put_object(Key= "test.json", Body=data)



def safe_call(name: str, fn):
    """Run a sensor read; return dict with error if it fails."""
    try:
        return {"ok": True, "data": fn()}
    except Exception as e:
        return {"ok": False, "error": f"{name}: {type(e).__name__}: {e}"}


def main():
    # INITIALIZATION

    # Shared I2C bus on Pi pins 3/5
    i2c_sensors = I2CSensors()

    # MCP3008 sensors (SPI0: pins 19/21/23 + CE0 pin 24)
    adc = MCP3008Sensors()

    # Modbus RTU bus (one shared UART) + two slaves
    bus = ModbusRTUBus()
    sn522 = SN522(bus, addr=1)  # net radiometer
    sq522 = SQ522(bus, addr=5)  # PAR on Modbus

    # Initialize the spectrometer RPi peripheral
    spec = StellarNetSpectrometer()

    # LOOP
    next_t = time.time()
    while True:
        t0 = time.time()

        # Read everything sequentially
        mcp_result = safe_call("mcp3008", adc.take_measurement)
        i2c_result = safe_call("i2c", i2c_sensors.take_measurement)
        sn_result = safe_call("sn522", sn522.take_measurement)
        sq_result = safe_call("sq522", sq522.take_measurement)
        # add spectrometer
        spec_result = safe_call("spectrometer", spec.read)
        # combine all dictionaries
        # timestamp in eastern time
        timestamp = str(datetime.now(pytz.timezone("America/New_York")))
        
        payload = {
            "est-timestamp": timestamp,
            "device_id": DEVICE_ID,
            "mcp3008": mcp_result,
            "i2c": i2c_result,
            "sn522": sn_result,
            "sq522": sq_result,
            "spectrometer": spec_result
        }
        print(payload)
        #  make into csv file 

        # # first try flushing old queued data, then send most recent
        # spool_flush(post_to_aws, max_lines=25)

        ok = post_to_aws(payload)

        # # write to backup file if did not send
        # if not ok:
        #     spool_append(payload)

        # # sleep to maintain 30s intervals
        # next_t += POLL_PERIOD_S
        # sleep_s = next_t - time.time()
        # if sleep_s < 0:
        #     # we're behind!!! reset schedule
        #     next_t = time.time()
        #     sleep_s = 0

        # # sleep
        time.sleep(POLL_PERIOD_S)


if __name__ == "__main__":
    main()
