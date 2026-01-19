# Test Script for I2C Sensors (scd41- co2/temperature/humidity)
# from mcp3008_sensors import MCP3008Sensors
from i2c_sensors import I2CSensors
from spectrometer import StellarNetSpectrometer
from modbus_sensors import ModbusRTUBus, SN522, SQ522

#  # Shared I2C bus on Pi pins 3/5
# i2c_sensors = I2CSensors()

# print(i2c_sensors.take_measurement())

# i2c_sensors.stop()
# i2c_sensors.reset_i2c_bus()

# adc = MCP3008Sensors()
# print(adc.take_measurement())
# get adjustment value from the function below and add it to code
# print(adc.calibrate_zero_wind_adjustment())

# Modbus RTU bus (one shared UART) + two slaves
# bus = ModbusRTUBus()
# sn522 = SN522(bus)  # net radiometer
# print(sn522.take_measurement())
# bus.close()

# spec = StellarNetSpectrometer()
# aquire black spectrum and save file 
# spec.acquire_dark()
# spec.save_dark_txt()
# spec.close()
