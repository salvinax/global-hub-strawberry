# MCP3008 - 8-Channel 10-Bit ADC With SPI Interface
# Datasheet: https://cdn-shop.adafruit.com/datasheets/MCP3008.pdf

# Sensors connected to MCP3008: 
# - par sensor (sq-214)
# - wind sensor revC

# Regression based on this Arduino sketch: 
# https://github.com/moderndevice/Wind_Sensor/blob/master/WindSensor/WindSensor.ino


import time
import math
import busio
import board
import digitalio
import adafruit_mcp3xxx.mcp3008 as MCP
from adafruit_mcp3xxx.analog_in import AnalogIn


class MCP3008Sensors:
    def __init__(
        self,
        *,
        r_shunt=180.0,
        wind_v_supply=5.0,
        volt_div_top=1000.0, 
        volt_div_bot=2000.0,  
        zero_wind_adjustment=0.2,
        B=0.2300,
        C=2.7265,
        par0=MCP.P0,
        par1=MCP.P1,
        wind_tmp=MCP.P2,
        wind_rv=MCP.P3,
        cs_pin=board.CE0,
    ):
        # constants, convert to floats
        self.r_shunt = float(r_shunt)

        self.wind_v_supply = float(wind_v_supply)
        self.volt_div_top = float(volt_div_top)
        self.volt_div_bot = float(volt_div_bot)
        self.div_gain = (self.volt_div_top + self.volt_div_bot) / self.volt_div_bot  # Vsensor = Vadc * gain

        self.zero_wind_adjustment = float(zero_wind_adjustment)
        self.B = float(B)
        self.C = float(C)

        # SPI + MCP3008
        spi = busio.SPI(clock=board.SCK, MISO=board.MISO, MOSI=board.MOSI)
        # cs = digitalio.DigitalInOut(cs_pin)
        cs = digitalio.DigitalInOut(board.CE0)
        mcp = MCP.MCP3008(spi, cs)

        # mcp3008 channel assignments
        self.par0 = AnalogIn(mcp, par0)
        self.par1 = AnalogIn(mcp, par1)
        self.wind_tmp = AnalogIn(mcp, wind_tmp)
        self.wind_rv = AnalogIn(mcp, wind_rv)

    # helpers
    def _avg_voltage(self, chan: AnalogIn, n: int, delay_s: float = 0.002) -> float:
        acc = 0.0
        for _ in range(n):
            acc += chan.voltage
            time.sleep(delay_s)
        return acc / n

    def _adc_to_sensor_volts(self, v_adc: float) -> float:
        return v_adc * self.div_gain

    # SQ-214
    def sq214_ppfd_from_adc_voltage(self, v_adc: float):
        """v_adc is voltage across shunt measured by MCP3008 channel."""
        i_ma = (v_adc / self.r_shunt) * 1000.0
        ppfd = 250.0 * (i_ma - 4.0)
        if ppfd < 0:
            ppfd = 0.0
        return ppfd, i_ma

    # Wind RevC 
    def wind_velocity_from_adc_voltages(self, tmp_v_adc: float, rv_v_adc: float):
        """
        Returns wind mph + temp estimate
        """
        # Undo divider -> sensor-level volts
        v_tmp = self._adc_to_sensor_volts(tmp_v_adc)
        v_rv = self._adc_to_sensor_volts(rv_v_adc)

        # Convert TMP volts -> counts/steps
        tmp_counts = v_tmp * (1024.0 / self.wind_v_supply)

        # same regressions as the Arduino sketch
        tempCtimes100 = (0.005 * tmp_counts * tmp_counts) - (16.862 * tmp_counts) + 9075.4

        zeroWind_counts = (-0.0006 * tmp_counts * tmp_counts) + (1.0727 * tmp_counts) + 47.172
        predicted_zeroWind_volts = (zeroWind_counts * (self.wind_v_supply / 1024.0))  # before adjustment
        zeroWind_volts = predicted_zeroWind_volts - self.zero_wind_adjustment

        delta_v = v_rv - zeroWind_volts
        wind_mph = 0.0 if delta_v <= 0 else math.pow(delta_v / self.B, self.C)

        return {
            "wind_mph": wind_mph,
            "temp_c": tempCtimes100 / 100.0
        }

    def calibrate_zero_wind_adjustment(self, seconds: float = 20.0, sample_hz: float = 20.0):
        """
        Still-air calibration (glass-over-sensor method).
        Computes zeroWindAdjustment so wind reads ~0 at the current temperature.

        zeroWind_volts == v_rv (at zero wind)
        where zeroWind_volts = predicted_zeroWind_volts - adjustment
        => adjustment = predicted_zeroWind_volts - v_rv
        """
        n = max(1, int(seconds * sample_hz))
        tmp_adc_acc = 0.0
        rv_adc_acc = 0.0
        dt = 1.0 / sample_hz

        for _ in range(n):
            tmp_adc_acc += self.wind_tmp.voltage
            rv_adc_acc += self.wind_rv.voltage
            time.sleep(dt)

        tmp_adc = tmp_adc_acc / n
        rv_adc = rv_adc_acc / n

        v_tmp = self._adc_to_sensor_volts(tmp_adc)
        v_rv = self._adc_to_sensor_volts(rv_adc)

        tmp_counts = v_tmp * (1024.0 / self.wind_v_supply)
        zeroWind_counts = (-0.0006 * tmp_counts * tmp_counts) + (1.0727 * tmp_counts) + 47.172
        predicted_zeroWind_volts = (zeroWind_counts * (self.wind_v_supply / 1024.0))

        new_adjustment = predicted_zeroWind_volts - v_rv
        self.zero_wind_adjustment = new_adjustment
        return new_adjustment

    # One-call measurement
    def take_measurement(self, avg_n: int = 8):
        # PAR sensors (SQ-214s)
        v_par0 = self._avg_voltage(self.par0, n=avg_n)
        v_par1 = self._avg_voltage(self.par1, n=avg_n)
        ppfd0, i0 = self.sq214_ppfd_from_adc_voltage(v_par0)
        ppfd1, i1 = self.sq214_ppfd_from_adc_voltage(v_par1)

        # Wind sensor (TMP + RV)
        v_tmp_adc = self._avg_voltage(self.wind_tmp, n=avg_n)
        v_rv_adc = self._avg_voltage(self.wind_rv, n=avg_n)
        wind = self.wind_velocity_from_adc_voltages(v_tmp_adc, v_rv_adc)

        return {
            "sq214_0": {"ppfd": ppfd0, "i_ma": i0, "v_adc": v_par0},
            "sq214_1": {"ppfd": ppfd1, "i_ma": i1, "v_adc": v_par1},
            "wind": wind,
        }



