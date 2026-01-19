import time
import board
import adafruit_scd4x
import adafruit_lps28


class I2CSensors:
    """
    Shared-I2C driver for Raspberry Pi (pins 3/5) with:
      - SCD41 (CO2, T, RH)
      - LPS28 (pressure, T)
    """

    def __init__(self, i2c=None, scd_warmup_s: float = 5.0):
        # One shared I2C bus (Pi pins 3=SDA, 5=SCL)
        self.i2c = board.I2C()

        # Init sensors
        self.scd = adafruit_scd4x.SCD4X(self.i2c)
        self.lps = adafruit_lps28.LPS28(self.i2c)
       
        #self.scd_serial = [hex(x) for x in self.scd.serial_number]

        # SCD4x must be put into periodic measurement mode
        self.scd.start_periodic_measurement()
        time.sleep(scd_warmup_s)

    # ---------- individual reads ----------
    def read_scd41(self, timeout_s: float = 0.0):
        """
        Returns latest SCD41 reading dict if available, else None.
        If timeout_s > 0, wait for data_ready.
        """
        t0 = time.time()
        while not self.scd.data_ready:
            if timeout_s <= 0:
                return None
            if (time.time() - t0) >= timeout_s:
                return None
            time.sleep(0.1)

        return {
            "co2_ppm": int(self.scd.CO2),
            "temp_c": float(self.scd.temperature),
            "rh_pct": float(self.scd.relative_humidity),
        }

    def read_lps28(self):
        """Returns current LPS28 reading dict."""
        return {
            "pressure_hpa": float(self.lps.pressure),
            "temp_c": float(self.lps.temperature),
        }

    # ---------- combined read ----------
    def take_measurement(self, scd_timeout_s: float = 1.0):
        """
        One-call measurement.
        - LPS28 always returns a value
        - SCD41 returns a value if ready (might wait a bit)
        """
        lps = self.read_lps28()
        scd = self.read_scd41(timeout_s=scd_timeout_s)

        return {
            "scd41": scd,   # may be None if not ready yet
            "lps28": lps,
        }

    def stop(self):
        try:
            self.scd.stop_periodic_measurement()
        except Exception:
            pass

    def reset_i2c_bus(self): 
        try:
            self.i2c.deinit()
        except Exception:
            pass


# Settings for LPS28
# Data Rate in hz
# 1, 4, 10, 25, 50, 75, 100 or 200 (default)
# sensor.data_rate = 200

# Number of samples to average per measurement
# 4 (default), 8, 16, 32, 64, 128, 512
# sensor.averaging = 4

# Full scale measurement mode for pressure
# (False = 1260 hPa, True = 4060 hPa (default))
# sensor.full_scale_mode = True