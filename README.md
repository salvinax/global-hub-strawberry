# Strawberry Global Hub

This project runs on a Raspberry Pi that:
1) **Collects local sensor data** 
2) **Receives node data over BLE notifications** (Nordic nodes)
3) **Stores everything in SQLite**
4) **Uploads data to AWS S3** every N minutes, into separate folder prefixes

---

## How the system works

### Components

#### 1 `collector.py` (data collection)
- Runs continuously
- Reads Pi-connected sensors on a fixed interval 
- Connects to a Nordic node via BLE, subscribes to notifications, and stores each received data packet
- On BLE connect it sends a “time sync” write to the Nordic (epoch + seconds-until-pump-target + other settings set by user)

All collected data is stored locally in SQLite.

#### 2 `uploader.py` (S3 uploader)
- Runs continuously
- Every `UPLOAD_PERIOD_S` (default: 300s=5 min):
  - Pulls rows from SQLite that haven’t been uploaded yet
  - Uploads **Pi sensor rows** to `s3://<bucket>/<S3_PREFIX_SENSORS>/...`
  - Uploads **BLE node rows** to `s3://<bucket>/<S3_PREFIX_NODES>/...`
  - Marks uploaded rows in SQLite (`uploaded=1`) so they don’t re-upload

---

## Data storage (SQLite)

The SQLite database holds two main tables:

- `sensor_samples`  
  Pi-local sensor snapshots (JSON payload):
  - `ts` (epoch seconds)
  - `payload` (JSON text)
  - `uploaded` (0/1)

- `node_packets`  
  BLE notifications from Nordic nodes (JSON payload):
  - `ts` (epoch seconds)
  - `node_id` (Node name)
  - `payload` (JSON text)
  - `uploaded` (0/1)

---

## Configuration (systemd service files)

You run both scripts as services (recommended). The service files contain `Environment=` lines you can edit without changing code.

### Collector service: `collector.service`
Typical fields you may change:
- `DB_PATH` — where the SQLite DB lives
- `BLE_ADDRESS` (required) or `BLE_DEVICE_NAME` 
- `BLE_NOTIFY_UUID` — the Nordic notify characteristic UUID
- `BLE_TIME_UUID` — the Nordic time sync write characteristic UUID
- `GLOBAL_PERIOD_S` — Global Hub (RPi) polling interval
- `DEVICE_ID` — a string identifying this Pi gateway
- `PUMP_TARGET_HHMM` - (ex. 23:39 - military time) sets the time pump turns ON (once per day)
- `PUMP_PERIOD_S` - how many the seconds the pump remains ON
- `NODE_PERIOD_S` - Sets the Local Node (Nordic) polling interval



### Uploader service: `uploader.service`
Typical fields you may change:
- `DB_PATH` — same DB file as collector
- `UPLOAD_PERIOD_S` — upload frequency in seconds (e.g. 300 = 5 min)
- `S3_BUCKET` — your S3 bucket name
- `S3_REGION` — AWS region (e.g. `us-east-1`)
- `S3_PREFIX_SENSORS` — “folder” for Pi sensor uploads (e.g. `sensors`) in bucket
- `S3_PREFIX_NODES` — “folder” for node uploads (e.g. `nodes`) in bucket
- `AWS_ACCESS_KEY_ID`=...
- `AWS_SECRET_ACCESS_KEY`=...
- `AWS_SESSION_TOKEN`=....


> After editing a service file, always run:
```bash
sudo systemctl daemon-reload
sudo systemctl restart collector.service
sudo systemctl restart uploader.service

Check out dev_param.md for more details...