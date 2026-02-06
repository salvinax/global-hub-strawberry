import time
import minimalmodbus
import serial

# Wiring
# White wire -> rx/positive -> a (pad 2)
# Blue wire -> tx/negative -> b (pad3)

class ModbusRTUBus:
    """shared Modbus RTU bus on one UART but multiple slaves."""

    def __init__(
        self,
        port="/dev/ttyAMA1",
        baud=19200,
        parity=serial.PARITY_EVEN,
        timeout=1.0,
        byteorder=0, 
    ):
        self.inst = minimalmodbus.Instrument(port, 1)
        self.inst.serial.baudrate = baud
        self.inst.serial.parity = parity
        self.inst.serial.bytesize = 8
        self.inst.serial.stopbits = 1
        self.inst.serial.timeout = timeout
        self.inst.mode = minimalmodbus.MODE_RTU
        self.inst.clear_buffers_before_each_transaction = True
        self.byteorder = byteorder

    def read_float32(self, slave_addr: int, reg: int) -> float:
        self.inst.address = int(slave_addr)
        return float(self.inst.read_float(reg, functioncode=3, byteorder=self.byteorder))

    def write_float32(self, slave_addr: int, reg: int, value: float) -> None:
        self.inst.address = int(slave_addr)
        self.inst.write_float(reg, float(value), byteorder=self.byteorder)

    def close(self):
        try:
            if self.inst.serial.is_open:
                self.inst.serial.close()
        except Exception:
            pass


class SN522:
    """Apogee SN-522 (net radiometer) all registers are float32."""

    def __init__(self, bus: ModbusRTUBus, addr: int = 1):
        self.bus = bus
        self.addr = int(addr)

        # Measurements (float32, 2 regs each)
        self.CALIBRATED_SHORTWAVE_UP_WATTS = 0
        self.CALIBRATED_SHORTWAVE_DOWN_WATTS = 2
        self.CALIBRATED_LONGWAVE_UP_WATTS = 4
        self.CALIBRATED_LONGWAVE_DOWN_WATTS = 6
        self.SHORTWAVE_NET_WATTS = 8
        self.LONGWAVE_NET_WATTS = 10
        self.TOTAL_NET_RADIATION = 12
        self.ALBEDO = 14
        self.SHORTWAVE_UP_MV = 16
        self.SHORTWAVE_DOWN_MV = 18
        self.LONGWAVE_UP_MV = 20
        self.LONGWAVE_DOWN_MV = 22
        self.LONGWAVE_UP_TEMPERATURE = 24
        self.LONGWAVE_DOWN_TEMPERATURE = 26

        # Config/status (float32)
        self.DEVICE_ADDRESS_REGISTER = 40
        self.MODEL_REGISTER = 42
        self.SERIAL_NUMBER_REGISTER = 44
        self.LONGWAVE_UP_MULTIPLIER = 52
        self.LONGWAVE_UP_OFFSET = 54
        self.LONGWAVE_DOWN_MULTIPLIER = 56
        self.LONGWAVE_DOWN_OFFSET = 58
        self.SHORTWAVE_UP_MULTIPLIER = 60
        self.SHORTWAVE_DOWN_MULTIPLIER = 62
        self.RUNNING_AVERAGE = 64
        self.HEATER_STATUS = 66

    def take_measurement(self) -> dict:
        calibrated_shortwave_up_watts = self.bus.read_float32(self.addr, self.CALIBRATED_SHORTWAVE_UP_WATTS)
        calibrated_shortwave_down_watts = self.bus.read_float32(self.addr, self.CALIBRATED_SHORTWAVE_DOWN_WATTS)
        calibrated_longwave_up_watts = self.bus.read_float32(self.addr, self.CALIBRATED_LONGWAVE_UP_WATTS)
        calibrated_longwave_down_watts = self.bus.read_float32(self.addr, self.CALIBRATED_LONGWAVE_DOWN_WATTS)

        shortwave_net_watts = self.bus.read_float32(self.addr, self.SHORTWAVE_NET_WATTS)
        longwave_net_watts = self.bus.read_float32(self.addr, self.LONGWAVE_NET_WATTS)
        total_net_radiation = self.bus.read_float32(self.addr, self.TOTAL_NET_RADIATION)
        albedo = self.bus.read_float32(self.addr, self.ALBEDO)

        shortwave_up_mv = self.bus.read_float32(self.addr, self.SHORTWAVE_UP_MV)
        shortwave_down_mv = self.bus.read_float32(self.addr, self.SHORTWAVE_DOWN_MV)
        longwave_up_mv = self.bus.read_float32(self.addr, self.LONGWAVE_UP_MV)
        longwave_down_mv = self.bus.read_float32(self.addr, self.LONGWAVE_DOWN_MV)

        longwave_up_temperature = self.bus.read_float32(self.addr, self.LONGWAVE_UP_TEMPERATURE)
        longwave_down_temperature = self.bus.read_float32(self.addr, self.LONGWAVE_DOWN_TEMPERATURE)

        return {
            "cal_sw_up_w": calibrated_shortwave_up_watts,
            "cal_sw_down_w": calibrated_shortwave_down_watts,
            "cal_lw_up_w": calibrated_longwave_up_watts,
            "cal_lw_down_w": calibrated_longwave_down_watts,
            "sw_net_w": shortwave_net_watts,
            "lw_net_w": longwave_net_watts,
            "net_total_w": total_net_radiation,
            "albedo": albedo,
            # "sw_up_mv": shortwave_up_mv,
            # "sw_down_mv": shortwave_down_mv,
            # "lw_up_mv": longwave_up_mv,
            # "lw_down_mv": longwave_down_mv,
            "lw_up_temp": longwave_up_temperature,
            "lw_down_temp": longwave_down_temperature,
        }

    def read_all_config(self) -> dict:
        device_address = self.bus.read_float32(self.addr, self.DEVICE_ADDRESS_REGISTER)
        model = self.bus.read_float32(self.addr, self.MODEL_REGISTER)
        serial_number = self.bus.read_float32(self.addr, self.SERIAL_NUMBER_REGISTER)

        longwave_up_multiplier = self.bus.read_float32(self.addr, self.LONGWAVE_UP_MULTIPLIER)
        longwave_up_offset = self.bus.read_float32(self.addr, self.LONGWAVE_UP_OFFSET)
        longwave_down_multiplier = self.bus.read_float32(self.addr, self.LONGWAVE_DOWN_MULTIPLIER)
        longwave_down_offset = self.bus.read_float32(self.addr, self.LONGWAVE_DOWN_OFFSET)

        shortwave_up_multiplier = self.bus.read_float32(self.addr, self.SHORTWAVE_UP_MULTIPLIER)
        shortwave_down_multiplier = self.bus.read_float32(self.addr, self.SHORTWAVE_DOWN_MULTIPLIER)

        running_average = self.bus.read_float32(self.addr, self.RUNNING_AVERAGE)
        heater_status = self.bus.read_float32(self.addr, self.HEATER_STATUS)

        return {
            "device_address": device_address,
            "model": model,
            "serial_number": serial_number,
            "lw_up_multiplier": longwave_up_multiplier,
            "lw_up_offset": longwave_up_offset,
            "lw_down_multiplier": longwave_down_multiplier,
            "lw_down_offset": longwave_down_offset,
            "sw_up_multiplier": shortwave_up_multiplier,
            "sw_down_multiplier": shortwave_down_multiplier,
            "running_average": running_average,
            "heater_status": heater_status,
            "ts": time.time(),
        }

    def set_heater(self, enable: bool):
        self.bus.write_float32(self.addr, self.HEATER_STATUS, 1.0 if enable else 0.0)


class SQ522:
    """Apogee SQ-522 (PAR) all registers are float32."""

    def __init__(self, bus: ModbusRTUBus, addr: int = 5):
        self.bus = bus
        self.addr = int(addr)

        # Measurements (float32, 2 regs each)
        self.CALIBRATED_OUTPUT = 0
        self.DETECTOR_MILLIVOLTS = 2
        self.IMMERSED_OUTPUT = 4
        self.SOLAR_OUTPUT = 6

        # Config/status (float32)
        self.DEVICE_ADDRESS_REGISTER = 16
        self.MODEL_REGISTER = 18
        self.SERIAL_NUMBER_REGISTER = 20
        self.MULTIPLIER = 28
        self.OFFSET = 30
        self.IMMERSION_FACTOR = 32
        self.SOLAR_MULTIPLIER = 34
        self.RUNNING_AVERAGE = 36
        self.HEATER_STATUS = 38

    def take_measurement(self) -> dict:
        calibrated_output = self.bus.read_float32(self.addr, self.CALIBRATED_OUTPUT)
        detector_millivolts = self.bus.read_float32(self.addr, self.DETECTOR_MILLIVOLTS)
        immersed_output = self.bus.read_float32(self.addr, self.IMMERSED_OUTPUT)
        solar_output = self.bus.read_float32(self.addr, self.SOLAR_OUTPUT)

        return {
            "calibrated_output": calibrated_output,
            # "detector_mv": detector_millivolts,
            # "immersed_output": immersed_output,
            # "solar_output": solar_output,
        }

    def read_all_config(self) -> dict:
        device_address = self.bus.read_float32(self.addr, self.DEVICE_ADDRESS_REGISTER)
        model = self.bus.read_float32(self.addr, self.MODEL_REGISTER)
        serial_number = self.bus.read_float32(self.addr, self.SERIAL_NUMBER_REGISTER)

        multiplier = self.bus.read_float32(self.addr, self.MULTIPLIER)
        offset = self.bus.read_float32(self.addr, self.OFFSET)
        immersion_factor = self.bus.read_float32(self.addr, self.IMMERSION_FACTOR)
        solar_multiplier = self.bus.read_float32(self.addr, self.SOLAR_MULTIPLIER)
        running_average = self.bus.read_float32(self.addr, self.RUNNING_AVERAGE)
        heater_status = self.bus.read_float32(self.addr, self.HEATER_STATUS)

        return {
            "device_address": device_address,
            "model": model,
            "serial_number": serial_number,
            "multiplier": multiplier,
            "offset": offset,
            "immersion_factor": immersion_factor,
            "solar_multiplier": solar_multiplier,
            "running_average": running_average,
            "heater_status": heater_status,
        }

    def set_heater(self, enable: bool):
        self.bus.write_float32(self.addr, self.HEATER_STATUS, 1.0 if enable else 0.0)

    def set_address(self, new_addr: int):
        # write new address to the device
        self.bus.write_float32(self.addr, self.DEVICE_ADDRESS_REGISTER, float(new_addr))
        # update local address for future reads
        self.addr = int(new_addr)

