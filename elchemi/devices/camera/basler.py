import time
from logging import getLogger
from threading import Thread

import numpy as np
from pypylon import pylon

from elchemi.devices.camera.exceptions import CameraException, CameraNotFound, WrongCameraState


class BaslerCamera:
    MODE_CONTINUOUS = 1
    MODE_SINGLE_SHOT = 0
    MODE_LAST = 2
    ACQUISITION_MODE = {
        MODE_CONTINUOUS: 'Continuous',
        MODE_SINGLE_SHOT: 'Single',
        MODE_LAST: 'Keep Last',
    }

    _acquisition_mode = MODE_SINGLE_SHOT

    def __init__(self, camera: str, initial_config: dict=None):
        self.logger = getLogger(__name__)
        self.config = initial_config
        self.camera = camera
        self.friendly_name = ''
        self.free_run_running = False
        self._stop_free_run = False
        self.fps = 0
        self.keep_reading = False
        self.continuous_reads_running = False
        self.initialized = False
        self.finalized = False
        self._buffer_size = None
        self.current_dtype = None
        self._driver = None
        self.width = 0
        self.height = 0
        self.pixel_format = None
        self.thread_reading = None

    def initialize(self):
        """ Initializes the communication with the camera. Get's the maximum and minimum width. It also forces
        the camera to work on Software Trigger.

        .. warning:: It may be useful to integrate other types of triggers in applications that need to
            synchronize with other hardware.
        """

        self.logger.debug('Initializing Basler Camera')
        tl_factory = pylon.TlFactory.GetInstance()
        devices = tl_factory.EnumerateDevices()
        if len(devices) == 0:
            raise CameraNotFound('No camera found')

        for device in devices:
            print(device.GetFriendlyName())
            if self.camera in device.GetFriendlyName():
                self._driver = pylon.InstantCamera()
                self._driver.Attach(tl_factory.CreateDevice(device))
                if not self._driver.IsOpen():                    
                    self._driver.Open()
                self.friendly_name = device.GetFriendlyName()

        if not self._driver:
            msg = f'Basler {self.camera} not found. Please check if the camera is connected'
            self.logger.error(msg)
            raise CameraNotFound(msg)

        self.logger.info(f'Loaded camera {self._driver.GetDeviceInfo().GetModelName()}')
        self.width = self.get_width()
        self.height = self.get_height()
        self._driver.Open()
        self.pixel_format = self.get_pixelformat()

    def StartGrabbing(self, grab):
        if grab == 'OneByOne':
            self._driver.StartGrabbing(pylon.GrabStrategy_OneByOne)
            self.logger.info('Grab Strategy: One by One')
        elif grab == 'LatestImage':
            self._driver.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
            self.logger.info('Grab Strategy: Latest Image')
        elif grab == 'LatestImages':
            self._driver.StartGrabbing(pylon.GrabStrategy_LatestImages)
            self.logger.info('Grab Strategy: Latest Images')

    def read_one(self, timeout):
        grabResult = self._driver.RetrieveResult(timeout, pylon.TimeoutHandling_Return)
        if not grabResult.IsValid(): # checks if the results have been saved in the buffer
            self.logger.warning(f'GrabResut is not valid, stopping results retrieve')
            grabResult.Release()
            return None
        else:
            return grabResult

    def set_frame_rate(self, fps):
        self._driver.AcquisitionFrameRateEnable.SetValue(True)
        self._driver.AcquisitionFrameRate.SetValue(fps)

    def StopGrabbing(self):
        self._driver.StopGrabbing()

    def get_acquisition_mode(self):
        return self._acquisition_mode

    def set_acquisition_mode(self, mode):
        if self._driver.IsGrabbing():
            self.logger.warning(f'{self} Changing acquisition mode for a grabbing camera')

        self.logger.info(f'{self} Setting acquisition mode to {mode}')

        if mode == self.MODE_CONTINUOUS:
            self.logger.debug(f'Setting buffer to {self._driver.MaxNumBuffer.Value}')
            self._acquisition_mode = mode

        elif mode == self.MODE_SINGLE_SHOT:
            self.logger.debug('Setting buffer to 1')
            self._acquisition_mode = mode

    def get_exposure(self):
        return float(self._driver.ExposureTime.Value)

    def set_exposure(self, exposure):
        """ Sets exposure time (in micro-s)
        """
        self._driver.ExposureTime.SetValue(exposure)

    def get_gain(self):
        return float(self._driver.Gain.Value)

    def set_gain(self, gain):
        self._driver.Gain.SetValue(gain)

    def get_autoexposure(self):
        return self._driver.ExposureAuto.Value

    def set_autoexposure(self, mode: str):
        modes = ('Off', 'Once', 'Continuous')
        if mode not in modes:
            raise ValueError(f'Mode must be one of {modes} and not {mode}')
        self._driver.ExposureAuto.SetValue(mode)

    def get_autogain(self):
        """ Auto Gain must be one of three values: Off, Once, Continuous"""
        return self._driver.GainAuto.Value

    def set_autogain(self, mode):
        modes = ('Off', 'Once', 'Continuous')
        if mode not in modes:
            raise ValueError(f'Mode must be one of {modes} and not {mode}')
        self._driver.GainAuto.SetValue(mode)

    def get_width(self):
        return self._driver.Width.Value

    def get_height(self):
        return self._driver.Height.Value

    def get_ROI(self):
        offset_X = self._driver.OffsetX.Value
        offset_Y = self._driver.OffsetY.Value
        width = self._driver.Width.Value - 1
        height = self._driver.Height.Value - 1
        self.width = width
        self.height = height
        return (offset_X, offset_X + width), (offset_Y, offset_Y + height)

    def set_ROI(self, vals):
        """ Sets the ROI on the camera. The input is a tuple with a specific format:
        vals = ((X_0, X_1), (Y_0, Y_1))
        In which each value defines a corner (and always _1>_0)
        """
        x_pos = vals[0]
        y_pos = vals[1]
        width = vals[2]
        height = vals[3]
        
        self.logger.info(f'Updating ROI: (x, y, width, height) = ({x_pos}, {y_pos}, {width}, {height})')
        
        self.logger.debug(f'Setting width to {width} and height to {height}')
        self._driver.Width.SetValue(width)
        self.width = width

        self.logger.debug(f'Setting Height to {height}')
        self._driver.Height.SetValue(height)
        self.height = height
        
        self.logger.debug(f'Setting X offset to {x_pos} and Y offset to {y_pos}')
        self._driver.OffsetX.SetValue(x_pos)
        self._driver.OffsetY.SetValue(y_pos)
        self.X = (x_pos, x_pos + width)
        self.Y = (y_pos, y_pos + height)

    def get_pixelformat(self):
        """ Pixel format must be one of Mono8, Mono12, Mono12p"""
        pixel_format = self._driver.PixelFormat.GetValue()
        if pixel_format == 'Mono8':
            self.current_dtype = np.uint8
        elif pixel_format == 'Mono12' or pixel_format == 'Mono12p':
            self.current_dtype = np.uint16
        else:
            self.logger.info(f'Camera is set to {pixel_format}, images will be converted \
                to Mono8 upon capture, some loss of accuracy could be caused')    
        return pixel_format

    def set_pixelformat(self, mode):
        if mode not in ('Mono8', 'Mono12'):
            raise ValueError('Supported modes are Mono8 and Mono12')

        self.logger.info(f'Setting pixel format to {mode}')
        self._driver.PixelFormat.SetValue(mode)
        if mode == 'Mono8':
            self.current_dtype = np.uint8
        elif mode == 'Mono12' or mode == 'Mono12p':
            self.current_dtype = np.uint16

    def trigger_camera(self):
        self.logger.info(f'Triggering {self} with mode: {self._acquisition_mode}')
        if self._driver.IsGrabbing():
            self.logger.warning('Triggering a grabbing camera')
            self._driver.StopGrabbing()
        mode = self._acquisition_mode

        if mode == self.MODE_CONTINUOUS:
            self.logger.info(f'{self} - Triggering Continuous')#, frame: ({self.width},{self.height})')
            # Calculate frame size in bytes
            frame_size = self.get_width() * self.get_height()
            if self.current_dtype == np.uint16:
                frame_size *= 2
            else:
                raise CameraException(f'{self} frame dtype is not known to allocate the buffer')

            # Calculate the number of frames to be allocated based on the buffer size (in MB) and the frame size
            # This is useful to keep into account that the frame can be cropped via the ROI or Binning.
            self.logger.info(f'{self} - Frame size: {frame_size} bytes')
            max_buffer_size = int(self.buffer_size.m_as('byte')/frame_size)
            self.logger.info(f'{self} - Calculated max buffer {max_buffer_size}')

            self._driver.MaxNumBuffer = max_buffer_size
            self._driver.OutputQueueSize = self._driver.MaxNumBuffer.Value
            self._driver.StartGrabbing(pylon.GrabStrategy_OneByOne)
            self.logger.info('Grab Strategy: One by One')
            self.logger.info(f'Output Queue Size: {self._driver.MaxNumBuffer.Value}')
        elif mode == self.MODE_SINGLE_SHOT:
            self._driver.MaxNumBuffer = 1
            self._driver.OutputQueueSize = 1
            self._driver.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
            self.logger.info('Grab Strategy: Latest Image')
        elif mode == self.MODE_LAST:
            self._driver.MaxNumBuffer = 10
            self._driver.OutputQueueSize = self._driver.MaxNumBuffer.Value
            self._driver.StartGrabbing(pylon.GrabStrategy_LatestImages)
            self.logger.info('Grab Strategy: Latest Images')
        else:
            raise CameraException('Unknown acquisition mode')

        # self._driver.ExecuteSoftwareTrigger()
        self.logger.info('Executed Software Trigger')

    def read_camera(self) -> list:
        img = []
        mode = self.get_acquisition_mode()
        exposure = self.get_exposure() * 1000  # Exposure in milliseconds
        self.logger.debug(f'Grabbing mode: {mode}')
        if mode == self.MODE_SINGLE_SHOT or mode == self.MODE_LAST:
            grab = self._driver.RetrieveResult(int(exposure + 100), pylon.TimeoutHandling_Return)
            if grab and grab.GrabSucceeded():
                img = [grab.GetArray().T]
                self.temp_image = img[-1]
                grab.Release()
            if mode == self.MODE_SINGLE_SHOT:
                self._driver.StopGrabbing()
            return img
        else:
            if not self._driver.IsGrabbing():
                raise WrongCameraState('You need to trigger the camera before reading')
            num_buffers = self._driver.NumReadyBuffers.Value
            if num_buffers > 0:
                if num_buffers > 0.9*self._driver.OutputQueueSize.Value:
                    self.logger.warning(f'{self} Buffer filled to 90% num buffers: {num_buffers}')
                img = [np.zeros((self.width, self.height), dtype=self.current_dtype)] * num_buffers
                tot_frames = 0
                for i in range(num_buffers):
                    grab = self._driver.RetrieveResult(int(exposure + 100), pylon.TimeoutHandling_ThrowException)
                    if grab:
                        if grab.GrabSucceeded():
                            img[i] = grab.GetArray().T
                            grab.Release()
                            tot_frames += 1
                        else:
                            self.logger.error(f'{self}: Grabbing failed {grab.ErrorDescription}')
                    # else:
                    #     if np.any(self.temp_image):
                    #         if np.all(self.temp_image == img[i]):
                    #             self.logger.error('Duplicated frame grabbed from Basler')
                if tot_frames != num_buffers:
                    self.logger.warning(f'{self}: Number of buffers: {num_buffers} but number of frames read: {tot_frames}')
                img = img[:tot_frames]
        if len(img) >= 1:
            self.temp_image = img[-1]

        return img

    def continuous_reads(self):
        self.continuous_reads_running = True
        self.keep_reading = True
        while self.keep_reading:
            imgs = self.read_camera()
            if len(imgs) >= 1:
                for img in imgs:
                    # TODO: Here is the place to do something with the acquired images!
                    continue
            time.sleep(.001)
        self.continuous_reads_running = False

    def start_continuous_reads(self):
        if self.continuous_reads_running:
            self.logger.warning("Trying to start a continuous read thread again!")
            return
        self.thread_reading = Thread(target=self.continuous_reads)
        self.thread_reading.start()
        self.trigger_camera()

    def stop_continuous_reads(self):
        if not self.continuous_reads_running:
            self.logger.warning("Trying to stop continuous reads, but it's not running")
            return
        self.keep_reading = False
        time.sleep(self.get_exposure()*1000)
        self._driver.StopGrabbing()
        t0 = time.time()
        while self.continuous_reads_running:
            if time.time() - t0 > 10:
                raise CameraException("The continuous reads are failing to stop")
            time.sleep(0.01)

    def configure_DIO(self):
        """Configures the Digital input-output of the camera based on a simple configuration dictionary that should be
        stored on the config parameters of the camera.
        """
        self.logger.info(f"{self} - Configure Digital input output")
        dio = self.config['DIO']
        for settings in dio:
            self.logger.debug(settings)
            self._driver.LineSelector.SetValue(dio[settings]['line'])
            self._driver.LineMode.SetValue(dio[settings]['mode'])
            self._driver.LineSource.SetValue(dio[settings]['source'])

    def finalize(self):
        self.logger.info(f'Finalizing camera {self}')
        if self.finalized:
            return

        self.stop_continuous_reads()
        self.finalized = True

    def __str__(self):
        if self.friendly_name:
            return f"Camera {self.friendly_name}"
        return super().__str__()


if __name__ == '__main__':
    cam = BaslerCamera('da')
    cam.initialize()
    cam.set_exposue(10000) # 10ms
    print(cam.get_exposure())
    print(cam.config)
    cam.config['roi'] = ((16, 1200-1), (16, 800-1))
    cam.set_ROI(cam.config['ROI'])
    cam.set_autoexposure('Off')
    cam.set_autogain('Off')
    cam.set_acquisition_mode(cam.MODE_SINGLE_SHOT)
    cam.trigger_camera()
    time.sleep(1)
    for i in range(10):
        img = cam.read_camera()
        print(img)
        