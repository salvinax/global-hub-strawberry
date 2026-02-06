# collector.py
import os, time, json, asyncio, logging, struct
import concurrent.futures
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timedelta

from bleak import BleakClient, BleakScanner

from db import init_db, db_connect

# import drivers for sensors
from mcp3008_sensors import MCP3008Sensors
from i2c_sensors import I2CSensors
from modbus_sensors import ModbusRTUBus, SN522, SQ522
#from spectrometer import StellarNetSpectrometer

LOG = logging.getLogger("collector")

DB_PATH = os.getenv("DB_PATH", "/var/lib/berrycam/data.db")

# BLE
BLE_DEVICE_NAME = os.getenv("BLE_DEVICE_NAME", "")      # optional
BLE_ADDRESS     = os.getenv("BLE_ADDRESS", "")          # optional (preferred)
BLE_NOTIFY_UUID = os.getenv("BLE_NOTIFY_UUID", "")      # Nordic -> Pi notifications (required)
BLE_TIME_UUID   = os.getenv("BLE_TIME_UUID", "")        # Pi -> Nordic write for time sync (required for time sync)

# Nordic payload parsing
NODE_NAME_LENGTH = 8
node_name = ""
# Scheduling / time sync target
PUMP_TARGET_HHMM = os.getenv("PUMP_TARGET_HHMM", "23:00")    # default 11pm

# intervals SAMPLING FREQ
GLOBAL_PERIOD_S = int(os.getenv("GLOBAL_PERIOD_S", "30"))
PUMP_PERIOD_S = int(os.getenv("PUMP_PERIOD_S", "30"))
NODE_PERIOD_S = int(os.getenv("NODE_PERIOD_S", "30"))

#  use one dedicated thread for all blocking sensor reads (global hub)
SENSOR_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=1)

# SQLite writes can also block; queue writes to not disturb ble
db_q: "asyncio.Queue[tuple[str, int, Optional[str], Dict[str, Any]]]" = asyncio.Queue(maxsize=2000)

def epoch_s() -> int:
    return int(time.time())

def epoch_ms_part() -> int:
    # 0to999 (ms portion of current epoch time)
    t = time.time()
    return int((t - int(t)) * 1000)

#make sure user input is correct and valid time
def parse_hhmm(s: str) -> Tuple[int, int]:
    parts = s.strip().split(":")
    hh = int(parts[0])
    mm = int(parts[1]) if len(parts) > 1 else 0
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ValueError
    return hh, mm

def local_now():
    return datetime.now().astimezone()

# find number of seconds between pump target time and now
def next_target_epoch_s(hhmm: str) -> int:
    hh, mm = parse_hhmm(hhmm)
    now = local_now()
    target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return int(target.timestamp())

# unpack payload!!!
def payload_unpack(node_name_len: int) -> str:
    # packed struct, little-endian:
    # uint8  ver
    # uint32 uptime_ms
    # uint32 epoch_s
    # uint16 epoch_ms
    # char   node_name[N]
    # int16  mlx_obj_c, mlx_amb_c
    # int16  sen_temp_c, sen_rh
    # int16  soil_temp_c
    # int16  wind_mph
    # int32  par_ppfd
    # int16  shortwave_w_m2
    # int16  pyr_temp_k
    # int16  longwave_w_m2
    # int32  weight_integer
    # int32  weight_fractional
    # B(1 byte) + I (4 bytes) + I + H (2 bytes) +  8s 
    return f"<BIIH{node_name_len}s" + "hhhhhh" + "i" + "hhh" + "ii"

def expected_payload_len(node_name_len: int) -> int:
    return struct.calcsize(payload_unpack(node_name_len))

def decode_sensor_payload_v1(data: bytes, node_name_len: int) -> Dict[str, Any]:
    fmt = payload_unpack(node_name_len)
    need = struct.calcsize(fmt)
    if len(data) != need:
        # store raw if mismatch
        return {
            "decode_error": f"len {len(data)} != expected {need}",
            "raw_hex": data.hex(),
        }

    (ver, uptime_ms, epoch_s_val, epoch_ms_val, node_name_b,
     mlx_obj_c, mlx_amb_c,
     sen_temp_c, sen_rh,
     soil_temp_c,
     wind_mph,
     par_ppfd,
     shortwave_w_m2,
     pyr_temp_k,
     longwave_w_m2,
     weight_integer,
     weight_fractional) = struct.unpack(fmt, data)

    # REMOVE TRAILING ZEROS 
    node_name = node_name_b.split(b"\x00", 1)[0].decode("utf-8", errors="ignore")
    dt = datetime.now().astimezone()


    return {
        "ver": ver,
        "est-timestamp": dt.isoformat(),
        "node_name": node_name,

        "mlx_obj_c": mlx_obj_c/100,
        "mlx_amb_c": mlx_amb_c/100,

        "sen_temp_c": sen_temp_c/100,
        "sen_rh": sen_rh/100,

        "soil_temp_c": soil_temp_c/100,
        "wind_mph": wind_mph/100,

        "par_ppfd": par_ppfd/100,

        "shortwave_w_m2": shortwave_w_m2/100,
        "pyr_temp_k": pyr_temp_k/100,
        "longwave_w_m2": longwave_w_m2/100,

        "weight_in_g": weight_integer + (abs(weight_fractional)/10**6)
    }


DEVICE_ID = "pi-gateway-1"
sensor_stack = None

# call functions through this function
def safe_call(name: str, fn):
    try:
        return fn()
    except Exception as e:
        LOG.warning("Sensor '%s' failed: %r", name, e)
        return {"error": repr(e)}

def init_sensors_once():
    global sensor_stack
    if sensor_stack is not None:
        return sensor_stack

    
    # i2c_sensors = I2CSensors()
    # adc = MCP3008Sensors()
    # bus = ModbusRTUBus()
    # sn522 = SN522(bus, addr=1)
    # sq522 = SQ522(bus, addr=5)
    # spec = StellarNetSpectrometer()

    # placeholder for testing:
    i2c_sensors = None
    adc = None
    sn522 = None
    sq522 = None
    spec = None

    sensor_stack = dict(i2c=i2c_sensors, adc=adc, sn522=sn522, sq522=sq522, spec=spec)
    return sensor_stack

def read_local_sensors_blocking() -> Dict[str, Any]:
    # make sure sensors are initialized 
    s = init_sensors_once()
    dt = datetime.now().astimezone()

    # Replace these with your real calls once you wire objects above:
    # mcp_result  = safe_call("mcp3008",      s["adc"].take_measurement)
    # i2c_result  = safe_call("i2c",          s["i2c"].take_measurement)
    # sn_result   = safe_call("sn522",        s["sn522"].take_measurement)
    # sq_result   = safe_call("sq522",        s["sq522"].take_measurement)
    # spec_result = safe_call("spectrometer", s["spec"].take_measurement)

    # placeholder for testing:
    mcp_result = {"todo": "hook MCP3008Sensors"}
    i2c_result = {"todo": "hook I2CSensors"}
    sn_result  = {"todo": "hook SN522"}
    sq_result  = {"todo": "hook SQ522"}
    spec_result= {"todo": "hook StellarNetSpectrometer"}

    

    return {
        "est-timestamp": dt.isoformat(),
        "device_id": DEVICE_ID,
        "mcp3008": mcp_result,
        "i2c": i2c_result,
        "sn522": sn_result,
        "sq522": sq_result,
        "spectrometer": spec_result,
    }

# db writer
async def db_writer_loop():
    while True:
        # wait until ther'es something in queue
        kind, ts, node_id, payload = await db_q.get()
        try:
            
            with db_connect(DB_PATH) as conn:
                if kind == "sensor":
                    conn.execute(
                        "INSERT INTO sensor_samples(ts, payload, uploaded) VALUES (?, ?, 0)",
                        (ts, json.dumps(payload)),
                    )
                elif kind == "node":
                    conn.execute(
                        "INSERT INTO node_packets(ts, node_id, payload, uploaded) VALUES (?, ?, ?, 0)",
                        (ts, node_id, json.dumps(payload)),
                    )
                conn.commit()
        except Exception as e:
            LOG.exception("DB write failed: %r", e)
        finally:
            # exit gracefully
            db_q.task_done()



async def sensor_loop():
    next_t = time.monotonic() #time.time()
    while True:
        next_t += GLOBAL_PERIOD_S
        try:
            # run in seperate thread because it might break ble
            payload = await asyncio.get_running_loop().run_in_executor(
                SENSOR_EXECUTOR, read_local_sensors_blocking
            )
            ts = epoch_s()
            payload["_src"] = "pi"
            payload["_ts"] = ts
            db_q.put_nowait(("sensor", ts, None, payload))
            LOG.info("Sensor sample queued")
        except Exception as e:
            LOG.exception("Sensor loop error: %r", e)

        await asyncio.sleep(max(0, next_t - time.monotonic()))

async def find_device_address() -> str:
    if BLE_ADDRESS:
        return BLE_ADDRESS
    if not BLE_DEVICE_NAME:
        raise RuntimeError("Set BLE_ADDRESS or BLE_DEVICE_NAME")
    LOG.info("Scanning for BLE device name=%s ...", BLE_DEVICE_NAME)
    dev = await BleakScanner.find_device_by_filter(lambda d, ad: d.name == BLE_DEVICE_NAME, timeout=15.0)
    if not dev:
        raise RuntimeError(f"Could not find device named {BLE_DEVICE_NAME}")
    return dev.address

async def send_time_sync(client: BleakClient):
    """
    look at Zephyr time_sync_write():
      len must be 10
      epoch_s  = le32 @ [0]
      epoch_ms = le16 @ [4]
      next_pump_epoch_s = le32 @ [6]
      pump_period_s = le16 @ [10]
      node_sampling_s = le16 @ [12]

    """
    if not BLE_TIME_UUID:
        LOG.info("BLE_TIME_UUID not set; skipping time sync write")
        return

    e_s = epoch_s()
    e_ms = epoch_ms_part()
    next_pump = next_target_epoch_s(PUMP_TARGET_HHMM)
    next_pump = next_target_epoch_s("23:05")

    pkt = struct.pack("<IHIHH", e_s, e_ms, next_pump, PUMP_PERIOD_S, NODE_PERIOD_S)

    try:
        await client.write_gatt_char(BLE_TIME_UUID, pkt, response=True)
        LOG.info("Time sync sent: epoch_s=%d epoch_ms=%d next_pump_epoch_s=%d (target %s)",
                 e_s, e_ms, next_pump, PUMP_TARGET_HHMM)
    except Exception as e1:
        try:
            await client.write_gatt_char(BLE_TIME_UUID, pkt, response=False)
            LOG.info("Time sync sent (noresp): epoch_s=%d epoch_ms=%d next_pump_epoch_s=%d",
                     e_s, e_ms, next_pump)
        except Exception as e2:
            LOG.warning("Time sync write failed: %r / %r", e1, e2)


async def ble_loop():
    if not BLE_NOTIFY_UUID:
        raise RuntimeError("BLE_NOTIFY_UUID is required (Nordic notify characteristic UUID)")

    need_len = expected_payload_len(NODE_NAME_LENGTH)
    LOG.info("Expecting Nordic payload length=%d bytes (NODE_NAME_LENGTH=%d)", need_len, NODE_NAME_LENGTH)

    while True:
        addr = None
        client = None
        disconnected_evt = None

        try:
            addr = await find_device_address()
            LOG.info("Connecting BLE: %s", addr)

            loop = asyncio.get_running_loop()
            disconnected_evt = asyncio.Event()

            def _on_disconnect(_client):
                loop.call_soon_threadsafe(disconnected_evt.set)

            client = BleakClient(addr, disconnected_callback=_on_disconnect)
            await client.connect()

            if not client.is_connected:
                raise RuntimeError("BLE connect failed")

            # send time sync when connected at the start
            await send_time_sync(client)

            def on_notify(_: int, data: bytearray):
                b = bytes(data)
                payload = decode_sensor_payload_v1(b, NODE_NAME_LENGTH)

                ts = epoch_s()
                payload["_ts"] = ts
                payload["_src"] = "nordic"

                try:
                    db_q.put_nowait(("node", ts, node_name, payload))
                except Exception:
                    LOG.warning("DB queue full; dropping packet")

            await client.start_notify(BLE_NOTIFY_UUID, on_notify)
            LOG.info("Notifications started on %s", BLE_NOTIFY_UUID)

            # Block here until Bleak reports a disconnect
            await disconnected_evt.wait()

            LOG.warning("BLE disconnected: %s (reconnecting...)", addr)

        except asyncio.CancelledError:
            raise

        except Exception as e:
            LOG.warning("BLE loop error: %r (reconnecting...)", e)

        finally:
            # clean up before reconnecting
            try:
                if client and client.is_connected:
                    try:
                        await client.stop_notify(BLE_NOTIFY_UUID)
                    except Exception:
                        pass
                    await client.disconnect()
            except Exception:
                pass

        # small delay before attempting reconnect
        await asyncio.sleep(2)


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s: %(message)s")
    init_db(DB_PATH)
    await asyncio.gather(db_writer_loop(), sensor_loop(), ble_loop())

if __name__ == "__main__":
    asyncio.run(main())
