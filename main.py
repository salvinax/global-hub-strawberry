import time
import json
import os
import requests
import boto3
from datetime import datetime
import pytz
from pathlib import Path
from typing import Optional

# on monday
# -> find adjustement value for wind sensor
# -> figure out spectrometer irrandiance
# -> test everything

# import drivers for sensors
from mcp3008_sensors import MCP3008Sensors
from i2c_sensors import I2CSensors
from modbus_sensors import ModbusRTUBus, SN522, SQ522
from spectrometer import StellarNetSpectrometer

BUCKET_NAME = "strawberry-lysimeter-data1"
S3_PREFIX = "telemetry"
DEVICE_ID = "global01"

TZ_NAME = "America/New_York"

POLL_PERIOD_S = 30.0

# WRITE TO BACKUP FILE IF SERVER IS DOWN
# save files locally in case of failures 
SPOOL_DIR = Path("./spool")
SENT_DIR = SPOOL_DIR / "sent"

# timestamp eastern time
def now_local() -> datetime:
    return datetime.now(pytz.timezone(TZ_NAME))

def hour_key(dt: datetime) -> str:
    # YYYY-MM-DD_HH
#    return dt.strftime("%M")
    return dt.strftime("%Y-%m-%d_%H")


# convert to json
def json_default(o):
    if isinstance(o, datetime):
        return o.isoformat()
    if hasattr(o, "tolist"):
        return o.tolist()
    return str(o)      

def safe_call(name: str, fn):
    """Run a sensor read; return dict with error if it fails."""
    try:
        return {"ok": True, "data": fn()}
    except Exception as e:
        return {"ok": False, "error": f"{name}: {type(e).__name__}: {e}"}

# append sensor data to hourly file 
def append_payload(payload: dict, hk: str) -> None:
    path = SPOOL_DIR / f"{DEVICE_ID}_{hk}.jsonl"
    line = json.dumps(payload, default=json_default)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def upload_backlog(s3_client, current_hk: str) -> None:
    for path in sorted(SPOOL_DIR.glob(f"{DEVICE_ID}_*.jsonl")):
        hk = path.stem.replace(f"{DEVICE_ID}_", "")
        if hk != current_hk:  # don't upload the active hour file
            try_upload_hour(s3_client, hk)
            print('uploaded')

def try_upload_hour(s3_client, hk: str) -> bool:
    """
    upload any hour files that are NOT the current hour.
    uploads once per hour
    """
    path = SPOOL_DIR / f"{DEVICE_ID}_{hk}.jsonl"
    if not path.exists():
        return True

    date_part = hk.split("_", 1)[0]  # YYYY-MM-DD
    filename = f"{DEVICE_ID}_{hk}.jsonl"
    key = f"{S3_PREFIX}/{DEVICE_ID}/{date_part}/{filename}"

    try:
        s3_client.upload_file(str(path), BUCKET_NAME, key)
        path.rename(SENT_DIR / path.name)  # archive so no re-upload
        print(f"[S3] uploaded {path.name} -> s3://{BUCKET_NAME}/{key}")
        # upload backlog
        return True

    except Exception as e:
        print(f"[S3] upload failed for {path.name}: {e}")
        return False



def main():
    # ensure local dir exists
    SPOOL_DIR.mkdir(parents=True, exist_ok=True)
    SENT_DIR.mkdir(parents=True, exist_ok=True)
    
    # INITIALIZATION of sensors

    # Shared I2C bus on Pi pins 3/5
    i2c_sensors = I2CSensors()

    # MCP3008 sensors (SPI0: pins 19/21/23 + CE0 pin 24)
    adc = MCP3008Sensors()

    # Modbus RTU bus (one shared UART) + two slaves
    bus = ModbusRTUBus()
    sn522 = SN522(bus, addr=1)  # net radiometer
    sq522 = SQ522(bus, addr=5)  # PAR on Modbus

    # Initialize the spectrometer RPi usb
    spec = StellarNetSpectrometer()

    # Set up AWS
    # use env variable
    s3 = boto3.client("s3")

    # record current
    current_hk = hour_key(now_local())
    to_upload_hk: Optional[str] = None

	    # upload backlog
    upload_backlog(s3, current_hk)
    
    while True:
        dt = now_local()
        hk = hour_key(dt)
        #hk = int(hour_key(dt))

        if hk != current_hk:
        #if hk % 5 == 0:
            to_upload_hk = current_hk
            current_hk = hk

        if to_upload_hk is not None:
            if try_upload_hour(s3, to_upload_hk):
                to_upload_hk = None  # uploaded successfully

        # Read all sensors
        mcp_result = safe_call("mcp3008", adc.take_measurement)
        i2c_result = safe_call("i2c", i2c_sensors.take_measurement)
        sn_result = safe_call("sn522", sn522.take_measurement)
        sq_result = safe_call("sq522", sq522.take_measurement)
        spec_result = safe_call("spectrometer", spec.take_measurement)

        payload = {
            "est-timestamp": dt.isoformat(),
            "device_id": DEVICE_ID,
            "mcp3008": mcp_result,
            "i2c": i2c_result,
            "sn522": sn_result,
            "sq522": sq_result,
            "spectrometer": spec_result
        }
        
     
        # save payload to local file 
        append_payload(payload, current_hk)

        # sleep
        time.sleep(POLL_PERIOD_S)


if __name__ == "__main__":
    main()
