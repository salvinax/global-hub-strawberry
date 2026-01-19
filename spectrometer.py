from stellarnet_driverLibs import stellarnet_driver3 as sn
from typing import Any, Dict
import os
import numpy as np
import time
# https://www.stellarnet.us/wp-content/uploads/stellarnet_driver3-Documentation_v2.5.pdf

class StellarNetSpectrometer:

    def __init__(
        self,
        channel: int = 0,
        inttime_ms: int = 50,
        scansavg: int = 1,
        smooth: int = 0,
        xtiming: int = 3,
        temp_comp: bool = False,
    ):
        n = int(sn.total_device_count())
        if n <= 0:
            raise RuntimeError("StellarNet: no devices detected.")
        if channel < 0 or channel >= n:
            raise RuntimeError(f"StellarNet: requested channel {channel}, but only {n} device(s) connected.")

        self.channel = channel
        self.inttime_ms = int(inttime_ms)
        self.scansavg = int(scansavg)
        self.smooth = int(smooth)
        self.xtiming = int(xtiming)
        self.temp_comp = bool(temp_comp)
        self.dark_counts = None
        self.spectrometer, self.wav = sn.array_get_spec(self.channel)
        self.aperturePercentage = 100

        # Set parameter
        sn.setParam(self.spectrometer, self.inttime_ms, self.scansavg, self.smooth, self.xtiming, True)
        sn.setTempComp(self.spectrometer, self.temp_comp)
        # Enable timeout 
        sn.ext_trig(self.spectrometer,False)

        self.CAL_PATH = "/home/syd/Desktop/global-hub/stellarnet_driverLibs/MyCal-C25013132-UVVIS-CR2.CAL"
        self.DARK_PATH = "/home/syd/Desktop/global-hub/dark_spectra/dark_ch0_int50ms.txt"

        # LOAD dark spectrum
        self.load_dark_txt(self.DARK_PATH)


    # get raw x and y data from spectrometer
    def read_raw(self) -> np.ndarray:
        data = sn.array_spectrum(self.spectrometer, self.wav)
        return np.asarray(data, dtype=float)


    # DARK CAPTURE - before deployment
    def acquire_dark(self, n: int = 7, settle_s: float = 0.1) -> np.ndarray:
        """
        Cover the spectrometer, block all light, then call this.
        Takes n spectra and returns the median as the dark spectrum.
        """
        spectra = []
        for _ in range(n):
            time.sleep(settle_s)
            xy = self.read_raw()    
            spectra.append(xy[:, 1])

        dark_y = np.median(np.stack(spectra, axis=0), axis=0)
        self.dark_counts = dark_y  
        return dark_y


    def save_dark_txt(self, folder: str = "dark_spectra") -> str:
        """
        Save the currently stored dark spectrum to a text file.
        """
        if self.dark_counts is None:
            raise RuntimeError("No dark spectrum stored. Call acquire_dark() first.")

        os.makedirs(folder, exist_ok=True)

        filename = f"dark_ch{self.channel}_int{self.inttime_ms}ms.txt"

        path = os.path.join(folder, filename)

        with open(path, "w", encoding="utf-8") as f:
            f.write("# StellarNet dark spectrum\n")
            f.write(f"# channel={self.channel}\n")
            f.write(f"# inttime_ms={self.inttime_ms}\n")
            f.write(f"# scansavg={self.scansavg}\n")
            f.write(f"# smooth={self.smooth}\n")
            f.write(f"# xtiming={self.xtiming}\n")
            f.write(f"# temp_comp={int(self.temp_comp)}\n")
            f.write(f"# n_points={len(self.wav)}\n")
            f.write("# columns: wav_nm\tdark_counts\n")

            for x, y in zip(self.wav, self.dark_counts):
                f.write(f"{x:.6f}\t{y:.6f}\n")

        return path

    def load_dark_txt(self, path: str) -> np.ndarray:
        """
        loads dark from TXT created by save_dark_txt().
        Sets self.dark_counts and returns it.
        """
        xs, ds = [], []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) < 2:
                    continue
                xs.append(float(parts[0]))
                ds.append(float(parts[1]))


        dark = np.asarray(ds, dtype=float)
        # check if same length 
        if dark.shape[0] != len(self.wav):
            raise RuntimeError(
                f"Dark length {dark.shape[0]} != device length {len(self.wav)}."
            )

        self.dark_counts = dark
        return dark


    # Function to calculate irradiance spectrum from raw data
    def getWattsY(self,spectrometerWavelength, rawSampleDataY, rawDarkDataY, rawSampleDataCapturedIntegrationTimeInMS, calibrationFilePath, aperturePercentage=100):
        """
        Calculate the Watts/m^2 spectral data using the provided raw sample data, dark data, and calibration file.

        Args:
            spectrometerWavelength (array or list): Wavelength values for the spectrometer.
            rawSampleDataY (array or list): Raw sample spectral data directly obtained from the spectrometer, without dark subtraction.
            rawDarkDataY (array or list): Raw dark spectral data (to subtract from the sample data). The spectrometer should be covered to ensure no light enters.
            rawSampleDataCapturedIntegrationTimeInMS (float): The integration time in milliseconds at which the sample data was captured.
            calibrationFilePath (str): The path to the StellarNet .CAL calibration file. It should be a valid StellarNet calibration file.
            aperturePercentage (float, optional): Percentage of the aperture value (the amount of light entering the spectrometer). Default is 100%.

        Returns:
            numpy.ndarray: A numpy array representing the Watts/m^2 spectrum corresponding to the provided wavelengths.

        Notes:
            - `spectrometerWavelength`, `rawSampleDataY`, and `rawDarkDataY` must have the same length. The `spectrometerWavelength` array should correspond to the provided `rawSampleDataY` and `rawDarkDataY`.
        """

        # Step 1: Load the calibration data and interpolate it to match the spectrometerWavelength
        calibrationData = np.genfromtxt(calibrationFilePath, skip_header=31, skip_footer=1)  # Read the calibration data from the file
        interpolatedCalibrationDataY = np.interp(spectrometerWavelength, calibrationData[:, 0], calibrationData[:, 1], left=0, right=0)  # Interpolate calibration data

        # Step 2: Extract the calibration integration time from the .CAL file
        calibrationIntegrationTime = int(
            next(line.strip().split('=')[1]
                for line in open(calibrationFilePath, 'r') if 'Csf1' in line))  # Extract integration time from the calibration file

        # Step 3: Subtract dark data from the sample data to obtain the corrected scope data
        scopeY = np.subtract(rawSampleDataY, rawDarkDataY)  # Subtract dark data from sample data to correct for dark noise
        scopeY[scopeY < 0] = 0  # Ensure no negative values after subtraction

        # Step 4: Normalize the raw scope data based on the integration times (calibration and sample)
        normRatio = float(calibrationIntegrationTime) / float(rawSampleDataCapturedIntegrationTimeInMS)  # Calculate the normalization ratio

        # Step 5: Convert the spectral data to Watts, applying the aperture scaling
        wattsY = np.asarray(scopeY * interpolatedCalibrationDataY[:len(spectrometerWavelength)] * normRatio * (100.0 / aperturePercentage))  # Convert to Watts

        wattsY[wattsY < 0] = 0  # Ensure no negative values in the Watts data

        return {'X':spectrometerWavelength, 'Y':wattsY}  # Return the calculated Watts values


    def take_measurement(self):
        """
        Returns:
          - wavelength x 
          - corrected_y
          - watts_y [nm, W/m^2/nm]
        """

        # take normal spectra
        raw_xy = self.read_raw()  

        x_nm = raw_xy[:, 0]
        raw_y = raw_xy[:, 1]


        corrected_y = raw_y - self.dark_counts
        corrected_y[corrected_y < 0] = 0.0

        calibrated_y = self.getWattsY(
            spectrometerWavelength=x_nm,
            rawSampleDataY=raw_y,
            rawDarkDataY=self.dark_counts,
            rawSampleDataCapturedIntegrationTimeInMS=self.inttime_ms,
            calibrationFilePath= self.CAL_PATH,
            aperturePercentage=self.aperturePercentage)

        watts_y = np.asarray(cal_out["Y"], dtype=float)

        return {
            "wavelength_nm": x_nm,
            "corrected_y": corrected_y,
            "calibrated_y": watts_y
        }


    def close(self) -> None:
        #release resources
        try:
            sn.reset(self.spectrometer)
        except Exception:
            pass

    