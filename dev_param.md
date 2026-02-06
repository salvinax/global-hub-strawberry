
# FOR ACTUAL SETUP - PROD
# create systemd service 

sudo nano /etc/systemd/system/collector.service

########################################################################

[Unit]
Description=Strawberry Data Collector
After=bluetooth.service network-online.target
Wants=bluetooth.service network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/salvina/Desktop/global-hub-strawberry

Environment=PYTHONUNBUFFERED=1
Environment=DB_PATH=/home/salvina/Desktop/global-hub-strawberry/database/data.db

# BLE target: set ONE (address recommended)
Environment=BLE_ADDRESS=ED:5B:7E:83:4F:F0
Environment=BLE_DEVICE_NAME=

# Nordic GATT UUIDs
Environment=BLE_NOTIFY_UUID=8f3a6c22-4b72-4fd1-9e38-3c2b7d9a51f4
Environment=BLE_TIME_UUID=12345679-1234-1234-1234-1234567890ab

# Nordic payload decoding
Environment=NODE_NAME_LENGTH=8

# Local sensor sampling period
Environment=DEVICE_ID=pi-gateway-1

# Time sync target (for seconds-until-target logic)
Environment=PUMP_TARGET_HHMM=23:00
Environment=PUMP_PERIOD_S=30
Environment=GLOBAL_PERIOD_S=30
Environment=NODE_PERIOD_S=30

ExecStart=/home/salvina/Desktop/global-hub-strawberry/.venv/bin/python /home/salvina/Desktop/global-hub-strawberry/collector.py

Restart=on-failure
RestartSec=2
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target



#########################################################


sudo nano /etc/systemd/system/uploader.service


########################################################

[Unit]
Description=Strawberry S3 Uploader
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/salvina/Desktop/global-hub-strawberry

Environment=PYTHONUNBUFFERED=1
Environment=DB_PATH=/home/salvina/Desktop/global-hub-strawberry/database/data.db

# Upload cadence (5 minutes)
Environment=UPLOAD_PERIOD_S=300

# S3 destination
Environment=S3_BUCKET=strawberry-lysimeter-data
Environment=S3_REGION=us-east-1
Environment=S3_PREFIX_SENSORS=sensors
Environment=S3_PREFIX_NODES=nodes

Environment=AWS_ACCESS_KEY_ID=...
Environment=AWS_SECRET_ACCESS_KEY=...
Environment=AWS_SESSION_TOKEN=....


ExecStart=/home/salvina/Desktop/global-hub-strawberry/.venv/bin/python /home/salvina/Desktop/global-hub-strawberry/uploader.py

Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target



################################################################

# enable and start both services 
sudo systemctl daemon-reload
sudo systemctl enable --now collector
sudo systemctl enable --now uploader


# check status
sudo systemctl status collector --no-pager
sudo systemctl status uploader --no-pager


# Follow logs on different terminals 
sudo journalctl -u collector -f
sudo journalctl -u uploader -f


# everytime env change is made
sudo systemctl daemon-reload
sudo systemctl restart collector
sudo systemctl restart uploader




#### SETTING UP DEV ENVIRONMENT

# ALWAYS SET ENV VARAIBLES FOR AWS 

export AWS_ACCESS_KEY_ID=
export AWS_SECRET_ACCESS_KEY=
export AWS_SESSION_TOKEN=

#check if it works
aws s3 ls

source .venv/bin/activate

# ENABLE BLUETOOTH ON RPI
sudo rfkill unblock bluetooth
sudo systemctl enable --now bluetooth
sudo systemctl status bluetooth --no-pager

#troubleshooting:
  #sudo systemctl restart bluetooth
  #bluetoothctl show
  #power on


### FOR COLLECTOR 
## WRITE IN TERMINAL 
##############################################
export DB_PATH=/home/salvina/Desktop/global-hub-strawberry/database/data.db
export BLE_ADDRESS=ED:5B:7E:83:4F:F0
export BLE_NOTIFY_UUID=8f3a6c22-4b72-4fd1-9e38-3c2b7d9a51f4
export BLE_TIME_UUID=12345679-1234-1234-1234-1234567890ab
export GLOBAL_PERIOD_S=30
export NODE_PERIOD_S=30
export PUMP_PERIOD_S=30
export PUMP_TARGET_HHMM=23:00

python3 collector.py

sudo env \
  DB_PATH=/home/salvina/Desktop/global-hub-strawberry/database/data.db \
  BLE_ADDRESS=ED:5B:7E:83:4F:F0 \
  BLE_NOTIFY_UUID=8f3a6c22-4b72-4fd1-9e38-3c2b7d9a51f4 \
  BLE_TIME_UUID=12345679-1234-1234-1234-1234567890ab \
  GLOBAL_PERIOD_S=30 \
  NODE_PERIOD_S=30 \
  PUMP_PERIOD_S=30 \
  PUMP_TARGET_HHMM=23:00 \
  /home/salvina/Desktop/global-hub-strawberry/.venv/bin/python \
  /home/salvina/Desktop/global-hub-strawberry/collector.py


#if you want to run as root - because of usb ports chmod problem

sudo /home/salvina/Desktop/global-hub-strawberry/.venv/bin/python \
  /home/salvina/Desktop/global-hub-strawberry/collector.py
############################################


### FOR UPLOADER
## WRITE IN TERMINAL 
############################################
export DB_PATH=/home/salvina/Desktop/global-hub-strawberry/database/data.db
export S3_BUCKET=strawberry-lysimeter-data
export S3_REGION=us-east-1
export S3_PREFIX_SENSORS=sensors
export S3_PREFIX_NODES=nodes
export UPLOAD_PERIOD_S=300

python3 uploader.py


sudo env \
  DB_PATH=/home/salvina/Desktop/global-hub-strawberry/database/data.db \
  S3_BUCKET=strawberry-lysimeter-data \
  S3_REGION=us-east-1 \
  S3_PREFIX_SENSORS=sensors \
  S3_PREFIX_NODES=nodes \
  UPLOAD_PERIOD_S=300 \
  AWS_ACCESS_KEY_ID= \
  AWS_SECRET_ACCESS_KEY= \
  AWS_SESSION_TOKEN= \
  /home/salvina/Desktop/global-hub-strawberry/uploader.py


# if you want to run as root with env - not really needed
sudo /home/salvina/Desktop/global-hub-strawberry/.venv/bin/python \
  /home/salvina/Desktop/global-hub-strawberry/uploader.py

############################################

