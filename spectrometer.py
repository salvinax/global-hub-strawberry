from stellarnet_driverLibs import stellarnet_driver3 as sn
from typing import Any, Dict
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
        if channel < 0 or channel >= n:
            raise RuntimeError(f"StellarNet: requested channel {channel}, but only {n} device(s) connected.")

        self.channel = channel
        self.spectrometer, self.wav = sn.array_get_spec(0)
        
        # Get current device parameter
        currentParam = sn.getDeviceParam(self.spectrometer)
        print(currentParam)

        # Configure
        # Only need to do once 
        sn.setParam(self.spectrometer, inttime_ms, scansavg, smooth, xtiming, True)
        sn.setTempComp(self.spectrometer, bool(temp_comp))
        # enable timeout 
        sn.ext_trig(self.spectrometer,False)

    # get x and y data from spectrometer
    def read(self) -> Dict[str, Any]:
        first_data = sn.array_spectrum(self.spectrometer, self.wav)
        
        return {
            "data": first_data
        }

    def close(self) -> None:
        #release resources
        try:
            sn.reset(self.spectrometer)
        except Exception:
            pass

    # Function to calculate irradiance spectrum from raw data
    def getWattsY(spectrometerWavelength, rawSampleDataY, rawDarkDataY, rawSampleDataCapturedIntegrationTimeInMS, calibrationFilePath, aperturePercentage=100):
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