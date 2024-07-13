from PyQt5 import QtCore
from pypylon import pylon
from numpy import transpose, shape
import cv2

class LiveView(QtCore.QThread):
    '''
    Worker Thread used to show live images in the widget. 
    '''
    def __init__(self, basler, window):
        super().__init__()
        self._running = True
        self.cam = basler
        self.Qwindow = window

    def run(self):
        self.cam.StartGrabbing('LatestImage')
        pixel_fmt = self.cam.get_pixelformat()
        
        while self._running:
            grab_result = self.cam.read_one(5000)

            if grab_result:
                if pixel_fmt == 'YCbCr422_8':
                    # TO DO:
                    # 1. Either reduce upload rate of images to raw data 
                    # or lower their quality to ensure that Worker Thread
                    # does not slow main widget too much. 
                    # !! These are only tentative solutions. You might need
                    # to do more digging as to what is the problem because the 
                    # widget seems to behave well as the conditions in the sample
                    # change. The issue is when the sample is static, the widget
                    # jams up. It might be that the GrabResult function in pypylon
                    # is very quick when this is the case and forces too many uploads
                    # of images every second onto the image window in the widget, hence
                    # causing the widget to slow down 
                    # 2. Check if the converter can act on any RGB pylon image. If it 
                    # does, the if pixel_fmt == part can be used to only convert the images
                    # to Mono8 to perform fft by using cv2.cvtColor (see line 46). 

                    converter = pylon.ImageFormatConverter()
                    converter.OutputPixelFormat = pylon.PixelType_BGR8packed  # Convert to BGR format
                    converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned
                    img = converter.Convert(grab_result)
                    img_arr = img.GetArray()
                    self.pyqtimage(img_arr)


                    # Mono8_img = cv2.cvtColor(img_arr, cv2.COLOR_BGR2GRAY) 
                    

            grab_result.Release()
        
    def pyqtimage(self,img):
        ''' 
        img: Array of the image to upload to the QtWindow in the widget
        pyqtgraph expects (width, height, channels), so the image is formatted
        using np.transpose
        '''
        img = transpose(img, (1, 0, 2))  
        self.Qwindow.setImage(img)

    def stop(self):
        '''Triggered when the freerun box is unchecked. It will stop the 
        Basler acquisiton and will stop grabbing so that the freerun can be
        turned back on without errors.'''
        self.cam.StopGrabbing()
        self._running = False