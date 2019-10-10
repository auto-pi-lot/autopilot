#########ONLY CHANGE STUFF ABOVE THIS LINE############

# import functions
import numpy as np

import time
from datetime import datetime
import PySpin
import os
import sys
from tqdm import tqdm
from skvideo import io

from Queue import Queue
import threading



class Camera_Spin(object):
    """
    A camera that uses the Spinnaker SDK + PySpin (eg. FLIR cameras)

    .. todo::

        should implement attribute setting like in https://github.com/justinblaber/multi_pyspin/blob/master/multi_pyspin.py

        and have prefs loaded from .json like they do rather than making a bunch of config profiles


    """

    def __init__(self, serial=None, bin=(4, 4), fps=None, exposure=0.9):
        """


        Args:
            serial (str): Serial number of the camera to be initialized
            bin (tuple): How many pixels to bin (Horizontally, Vertically).
            fps (int): frames per second. If None, automatic exposure and continuous acquisition are used.
            exposure (int, float): Either a float from 0-1 to set the proportion of the frame interval (0.9 is default) or absolute time in us
        """

        # FIXME: Hardcoding just for testing
        serial = '19269891'
        self.serial = serial

        # find our camera!
        # get the spinnaker system handle
        self.system = PySpin.System.GetInstance()
        # need to hang on to camera list for some reason, could be cargo cult code
        self.cam_list = self.system.GetCameras()

        if self.serial:
            self.cam = self.cam_list.GetBySerial(self.serial)
        else:
            Warning(
                'No camera serial number provided, trying to get the first camera.\nAddressing cameras by serial number is STRONGLY recommended to avoid randomly using the wrong one')
            self.serial = 'noserial'
            self.cam = self.cam_list.GetByIndex(0)

        # initialize the cam - need to do this before messing w the values
        self.cam.Init()

        # get nodemap
        # TODO: Document what a nodemap is...
        self.nmap = self.cam.GetTLDeviceNodeMap()

        # Set Default parameters
        # FIXME: Should rely on params file
        self.cam.PixelFormat.SetValue(PySpin.PixelFormat_Mono8)
        #self.cam.AdcBitDepth.SetValue(PySpin.AdcBitDepth_Bit8)
        self.cam.AcquisitionMode.SetValue(PySpin.AcquisitionMode_Continuous)

        # configure binning - should come before fps because fps is dependent on binning
        if bin:
            self.cam.BinningSelector.SetValue(PySpin.BinningSelector_All)
            try:
                self.cam.BinningHorizontalMode.SetValue(PySpin.BinningHorizontalMode_Average)
                self.cam.BinningVerticalMode.SetValue(PySpin.BinningVerticalMode_Average)
            except PySpin.SpinnakerException:
                Warning('Average binning not supported, using sum')

            self.cam.BinningHorizontal.SetValue(int(bin[0]))
            self.cam.BinningVertical.SetValue(int(bin[1]))

        # exposure time is in microseconds, can be not given (90% fps interval used)
        # given as a proportion (0-1) or given as an absolute value
        if not exposure:
            # exposure = (1.0/fps)*.9*1e6
            self.cam.ExposureAuto.SetValue(PySpin.ExposureAuto_Continuous)
        else:
            if exposure < 1:
                # proportional
                exposure = (1.0 / fps) * exposure * 1e6

            self.cam.ExposureAuto.SetValue(PySpin.ExposureAuto_Off)
            self.cam.ExposureMode.SetValue(PySpin.ExposureMode_Timed)
            self.cam.ExposureTime.SetValue(exposure)

        # if fps is set, change to fixed fps mode
        if fps:
            self.cam.AcquisitionFrameRateEnable.SetValue(True)
            self.cam.AcquisitionFrameRate.SetValue(fps)
        self.fps = fps


    @property
    def bin(self):
        return (self.cam.BinningHorizontal.GetValue(), self.cam.BinningHorizontal.GetValue())

    @bin.setter
    def bin(self, new_bin):
        # TODO: Check if acquiring yno
        self.cam.BinningHorizontal.SetValue(int(new_bin[0]))
        self.cam.BinningVertical.SetValue(int(new_bin[1]))


    @property
    def device_info(self):
        """
        Device information like ID, serial number, version. etc.

        Returns:

        """

        device_info = PySpin.CCategoryPtr(self.nmap.GetNode('DeviceInformation'))

        features = device_info.GetFeatures()

        # save information to a dictionary
        info_dict = {}
        for feature in features:
            node_feature = PySpin.CValuePtr(feature)
            info_dict[node_feature.GetName()] = node_feature.ToString()

        return info_dict

    def fps_test(self, n_frames=1000, writer=True):
        """
        Try to acquire frames, return mean fps and inter-frame intervals


        Returns:
            mean_fps (float): mean fps
            sd_fps (float): standard deviation of fps
            ifi (list): list of inter-frame intervals

        """

        # start acquitision
        self.cam.BeginAcquisition()

        # keep track of how many frames captured
        frame = 0

        # list of inter-frame intervals
        ifi = []

        # start a writer to stash frames
        try:
            if writer:
                self.write_q = Queue()
                self.writer = threading.Thread(target=self._writer, args=(self.write_q,))
                self.writer.start()
        except Exception as e:
            print(e)

        while frame < n_frames:
            img = self.cam.GetNextImage()
            ifi.append(img.GetTimeStamp() / float(1e9))
            self.write_q.put_nowait(img)
            #img.Release()
            frame += 1

        self.cam.EndAcquisition()
        self.write_q.put_nowait('END')

        # compute returns
        # ifi is in nanoseconds...
        fps = 1./(np.diff(ifi)/1e3)
        mean_fps = np.mean(fps)
        sd_fps = np.std(fps)

        print('Waiting on video writer...')

        self.writer.join()

        return mean_fps, sd_fps, ifi

    def tmp_dir(self, new=False):
        if new or not hasattr(self, '_tmp_dir'):
            self._tmp_dir = os.path.join(os.path.expanduser('~'),
                                    '.tmp_capture_{}_{}'.format(self.serial, datetime.now().strftime("%y%m%d-%H%M%S")))
            os.mkdir(self._tmp_dir)

        return self._tmp_dir



    def _capture(self):

        ##########################
        # make a temporary directory to save images into
        #self.tmp_dir = os.path.join(os.path.expanduser('~'),
        #                            '.tmp_capture_{}_{}'.format(self.serial, datetime.now().strftime("%y%m%d-%H%M%S")))
        #os.mkdir(self.tmp_dir)
        pass

    def _writer(self, q):
        """
        Thread to write frames to file, then compress to video.

        Todo:
            need to wrap this all up in capture method

        Returns:

        """
        out_dir = self.tmp_dir(new=True)
        frame_n = 0
        # TODO: Get this from prefs, just testing this
        out_vid_fn = os.path.join(os.path.expanduser('~'), "{}_{}.mp4".format(self.serial, datetime.now().strftime("%y%m%d-%H%M%S")))

        vid_out = io.FFmpegWriter(out_vid_fn,
            inputdict={
                '-r': str(self.fps),
        },
            outputdict={
                '-vcodec': 'libx264',
                '-pix_fmt': 'yuv420p',
                '-r': str(self.fps),
                '-preset': 'fast'
            },
            verbosity=1
        )


        for img in iter(q.get, 'END'):
            #fname = os.path.join(out_dir, "{}_{:06d}.tif".format(self.serial, frame_n))
            #img.Save(fname)
            img_arr = img.GetNDArray()
            print(img_arr.shape)
            vid_out.writeFrame(img_arr)
            img.Release()

        vid_out.close()
        # convert to video







    def __del__(self):
        self.release()


    def release(self):
        # FIXME: Should check if finished writing to video before deleting tmp dir
        #os.rmdir(self.tmp_dir)
        self.cam.DeInit()
        self.cam_list.Clear()
        del self.cam
        del self.cam_list
        self.system.ReleaseInstance()

















#
# def acquire_images(cam_list):
#     print('*** IMAGE ACQUISITION ***\n')
#     try:
#         result = True
#
#         for i, cam in enumerate(cam_list):
#
#             # Set acquisition mode to continuous
#             node_acquisition_mode = PySpin.CEnumerationPtr(cam.GetNodeMap().GetNode('AcquisitionMode'))
#             if not PySpin.IsAvailable(node_acquisition_mode) or not PySpin.IsWritable(node_acquisition_mode):
#                 print('Unable to set acquisition mode to continuous (node retrieval; camera %d). Aborting... \n' % i)
#                 return False
#
#             node_acquisition_mode_continuous = node_acquisition_mode.GetEntryByName('Continuous')
#             if not PySpin.IsAvailable(node_acquisition_mode_continuous) or not PySpin.IsReadable(
#                     node_acquisition_mode_continuous):
#                 print('Unable to set acquisition mode to continuous (entry \'continuous\' retrieval %d). \
#                 Aborting... \n' % i)
#                 return False
#
#             acquisition_mode_continuous = node_acquisition_mode_continuous.GetValue()
#
#             node_acquisition_mode.SetIntValue(acquisition_mode_continuous)
#
#             print('Camera %d acquisition mode set to continuous...' % i)
#
#             # Begin acquiring images
#             cam.BeginAcquisition()
#
#             print('Camera %d started acquiring images...' % i)
#
#             # Retrieve device serial number for filename0
#             node_device_serial_number = PySpin.CStringPtr(cam.GetTLDeviceNodeMap().GetNode('DeviceSerialNumber'))
#
#             if PySpin.IsAvailable(node_device_serial_number) and PySpin.IsReadable(node_device_serial_number):
#                 device_serial_number = node_device_serial_number.GetValue()
#                 print('Camera %d serial number set to %s...' % (i, device_serial_number))
#
#         # Retrieve, convert, and save images for each camera
#         i = 0
#         millis = []  # keep track of frame times in ms
#         trial_info = []  # keep track of platform and distance
#         trial_outcome = []  # keep track of trial outcomes
#         jump_time = []  # keep track of jump times
#         laser_trial = []  # keep track of laser trials
#         cur_trial = 0  # initialize first trial
#         if random.random() < laser_prob:
#             laser = 1
#         else:
#             laser = 0
#         trial_disp = trial_params[cur_trial]  # for displaying current trial on screen
#         cv2.namedWindow('frame', cv2.WND_PROP_FULLSCREEN)
#         cv2.setWindowProperty('frame', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
#         font = cv2.FONT_HERSHEY_DUPLEX
#         fontcol = (0, 0, 0)
#         sttime = time.time()
#         while (True):
#
#             # esc key exits acquisition
#             k = cv2.waitKey(1) & 0xFF
#
#             # escape key exits the program
#             if k == 27:
#                 break
#
#             # success trial
#             elif k == ord('1'):
#                 trial_outcome.append(1)
#                 trial_info.append(trial_disp)
#                 laser_trial.append(laser)
#                 del trial_params[cur_trial]
#                 if trial_params == []:  # repopulate trial parameters if it's empty
#                     for platform in np.arange(1, 4):  # 3 platforms
#                         for distance in np.arange(8, 28, 4):  # 8 to 24 cm distances in 4cm increments
#                             trial_params.append([platform, distance])
#                 cur_trial = random.randint(0, len(trial_params) - 1)
#                 trial_disp = trial_params[cur_trial]
#                 if random.random() < laser_prob:
#                     laser = 1
#                 else:
#                     laser = 0
#
#             # failure trial
#             elif k == ord('0'):
#                 trial_outcome.append(0)
#                 trial_info.append(trial_disp)
#                 laser_trial.append(laser)
#                 cur_trial = random.randint(0, len(trial_params) - 1)
#                 trial_disp = trial_params[cur_trial]
#                 if random.random() < laser_prob:
#                     laser = 1
#                 else:
#                     laser = 0
#
#             # abort trial
#             elif k == ord('a'):
#                 trial_outcome.append(2)
#                 trial_info.append(trial_disp)
#                 laser_trial.append(laser)
#                 jump_time.append(round(time.time() - sttime))
#                 cur_trial = random.randint(0, len(trial_params) - 1)
#                 trial_disp = trial_params[cur_trial]
#                 if random.random() < laser_prob:
#                     laser = 1
#                 else:
#                     laser = 0
#
#             # jump happens
#             elif k == 32:
#                 jump_time.append(round(time.time() - sttime))
#
#             # advance a trial
#             elif k == ord('n'):
#                 cur_trial = random.randint(0, len(trial_params) - 1)
#                 trial_disp = trial_params[cur_trial]
#                 if random.random() < laser_prob:
#                     laser = 1
#                 else:
#                     laser = 0
#
#             # skip a trial (removes that trial from list)
#             elif k == ord('s'):
#                 cur_trial = random.randint(0, len(trial_params) - 1)
#                 trial_disp = trial_params[cur_trial]
#                 del trial_params[cur_trial]
#                 if trial_params == []:  # repopulate trial parameters if it's empty
#                     for platform in np.arange(1, 4):  # 3 platforms
#                         for distance in np.arange(8, 28, 4):  # 8 to 24 cm distances in 4cm increments
#                             trial_params.append([platform, distance])
#                 cur_trial = random.randint(0, len(trial_params) - 1)
#                 trial_disp = trial_params[cur_trial]
#                 if random.random() < laser_prob:
#                     laser = 1
#                 else:
#                     laser = 0
#
#             # remove last jump time (in case you accidentally hit spacebar)
#             elif k == ord('j'):
#                 if len(jump_time) > 0:
#                     del jump_time[-1]
#
#             # swap the last trial outcome in case you hit either 0 or 1 when you meant the other one
#             elif k == ord('u'):
#                 if len(trial_outcome) > 0:
#                     if trial_outcome[-1] == 0:
#                         trial_outcome[-1] = 1
#                     elif trial_outcome[-1] == 1:
#                         trial_outcome[-1] = 0
#
#             # remove the last trial in case you accidentally hit 0, 1, or a
#             elif k == ord('t'):
#                 if len(trial_info) > 0:
#                     del trial_info[-1]
#
#             for c, cam in enumerate(cam_list):
#                 try:
#                     # Retrieve next received image and ensure image completion
#                     image_result = cam.GetNextImage()
#
#                     if image_result.IsIncomplete():
#                         print('Image incomplete with image status %d ... \n' % image_result.GetImageStatus())
#                     else:
#                         # store the time the frame was acquired
#                         millis.append(image_result.GetTimeStamp() / 1e6)
#
#                         #  Convert image to mono 8
#                         image_converted = image_result.Convert(PySpin.PixelFormat_Mono8, PySpin.HQ_LINEAR)
#
#                         # Create a unique filename
#                         filename = '%s_cam%d_%s.jpg' % (expname, c, str(i).zfill(7))
#
#                         #  Save image
#                         image_converted.Save(filename)
#
#                         if c == 0:
#                             img0 = image_converted.GetNDArray()
#                         else:
#                             img1 = image_converted.GetNDArray()
#
#                         #  Release image
#                         image_result.Release()
#
#                 except PySpin.SpinnakerException as ex:
#                     print('Error: %s' % ex)
#                     result = False
#
#             # display image with current time
#             if np.mod(i, 12) == 0:
#                 img = np.concatenate((img0, img1), axis=1)
#                 curtime = round(time.time() - sttime)
#                 cv2.putText(img, '%ds plat=%d dist=%d laser=%d trial=%d jumps=%d' % (
#                 curtime, trial_disp[0], trial_disp[1], laser, len(trial_info), len(jump_time)), (10, 50), font, 0.8,
#                             fontcol, 1, cv2.LINE_AA)
#                 if len(trial_info) > 0:
#                     cv2.putText(img, 'prev: %d @ %d suc=%d | miss=%d abort=%d' % (
#                     trial_info[-1][0], trial_info[-1][1], trial_outcome[-1], trial_outcome.count(0),
#                     trial_outcome.count(2)), (10, 100), font, 0.8, fontcol, 1, cv2.LINE_AA)
#                 cv2.putText(img, 'spcbr=jump 1=suc 0=fail n=nexttr', (10, 210), font, 0.8, fontcol, 1, cv2.LINE_AA)
#                 cv2.putText(img, 's=skiptr j=undojump t=undotrial u=swapoutcome ', (10, 250), font, 0.8, fontcol, 1,
#                             cv2.LINE_AA)
#                 cv2.imshow('frame', img)
#             i += 1
#
#         for cam in cam_list:
#             cam.EndAcquisition()
#
#     except PySpin.SpinnakerException as ex:
#         print('Error: %s' % ex)
#         result = False
#
#     return result, millis, trial_info, trial_outcome, jump_time, laser_trial
#
#
# def print_device_info(nodemap, cam_num):
#     print('Printing device information for camera %d... \n' % cam_num)
#
#     try:
#         result = True
#         node_device_information = PySpin.CCategoryPtr(nodemap.GetNode('DeviceInformation'))
#
#         if PySpin.IsAvailable(node_device_information) and PySpin.IsReadable(node_device_information):
#             features = node_device_information.GetFeatures()
#             for feature in features:
#                 node_feature = PySpin.CValuePtr(feature)
#                 print('%s: %s' % (node_feature.GetName(),
#                                   node_feature.ToString() if PySpin.IsReadable(node_feature) else 'Node not readable'))
#
#         else:
#             print('Device control information not available.')
#
#     except PySpin.SpinnakerException as ex:
#         print('Error: %s' % ex)
#         return False
#
#     print('Done printing device information for camera %d... \n' % cam_num)
#
#     return result
#
#
# def run_multiple_cameras(cam_list):
#     try:
#         result = True
#
#
#         print('*** DEVICE INFORMATION ***\n')
#
#         for i, cam in enumerate(cam_list):
#             print('checking camera %d' % i)
#
#             # Retrieve TL device nodemap
#             nodemap_tldevice = cam.GetTLDeviceNodeMap()
#
#             # Print device information
#             result = print_device_info(nodemap_tldevice, i)
#
#         fps = []
#         for i, cam in enumerate(cam_list):
#             # Initialize camera
#             cam.Init()
#
#             # Retrieve GenICam nodemap
#             nodemap = cam.GetNodeMap()
#             node_acquisition_framerate = PySpin.CFloatPtr(nodemap.GetNode('AcquisitionFrameRate'))
#             print('camera %d fps=%d' % (i, node_acquisition_framerate.GetValue()))
#             fps.append(node_acquisition_framerate.GetValue())
#
#         # Acquire images on all cameras
#         result, millis, trial_info, trial_outcome, jump_time, laser_trial = acquire_images(cam_list)
#
#         for cam in cam_list:
#             # Deinitialize camera
#             cam.DeInit()
#
#         # Release reference to camera
#         # NOTE: Unlike the C++ examples, we cannot rely on pointer objects being automatically
#         # cleaned up when going out of scope.
#         # The usage of del is preferred to assigning the variable to None.
#         del cam
#
#     except PySpin.SpinnakerException as ex:
#         print('Error: %s' % ex)
#         result = False
#
#     return result, millis, fps, trial_info, trial_outcome, jump_time, laser_trial
#
#
# def main():
#     # Retrieve singleton reference to system object
#     system = PySpin.System.GetInstance()
#
#     # Get current library version
#     version = system.GetLibraryVersion()
#     print('Library version: %d.%d.%d.%d' % (version.major, version.minor, version.type, version.build))
#
#     # Retrieve list of cameras from the system
#     cam_list = system.GetCameras()
#
#     num_cameras = cam_list.GetSize()
#
#     print('Number of cameras detected: %d' % num_cameras)
#
#     # Finish if there are no cameras
#     if num_cameras == 0:
#         # Clear camera list before releasing system
#         cam_list.Clear()
#
#         # Release system instance
#         system.ReleaseInstance()
#
#         print('Not enough cameras!')
#         input('Done! Press Enter to exit...')
#         return False
#
#     # Run example on all cameras
#     print('Running acquisition for all cameras...')
#
#     result, millis, fps, trial_info, trial_outcome, jump_time, laser_trial = run_multiple_cameras(cam_list)
#
#     print('Acquisition complete!')
#
#     # Clear camera list before releasing system
#     cam_list.Clear()
#
#     # Release system instance
#     system.ReleaseInstance()
#
#     return result, millis, fps, trial_info, trial_outcome, jump_time, laser_trial, num_cameras
#
#
# if __name__ == '__main__':
#     result, millis, fps, trial_info, trial_outcome, jump_time, laser_trial, num_cameras = main()
#
# # close the camera window after acquisition is complete
# cv2.destroyAllWindows()
#
# platform = []
# distance = []
# for item in trial_info:
#     platform.append(item[0])
#     distance.append(item[1])
#
# # plot the time between frames
# fig, ax = plt.subplots(1, num_cameras, figsize=(5 * num_cameras, 5))
# m = []
# for c in np.arange(num_cameras):
#     print('c=%d' % c)
#     m.append(millis[c::num_cameras])
#
#     # convert the image files to video
#     imfiles = find('%s_cam%d_*.jpg' % (expname, c), pathname)
#     im = cv2.imread(imfiles[0])
#     height, width, layers = im.shape
#     out = cv2.VideoWriter(os.path.join(pathname, expname + '_cam%d.avi' % c),
#                           cv2.VideoWriter_fourcc('M', 'J', 'P', 'G'), fps[c], (width, height))
#     for f in tqdm(np.arange(len(imfiles))):
#         out.write(cv2.imread(imfiles[f]))
#
#     # check that the video was made then delete the frames
#     if os.path.exists(expname + '_cam%d.avi' % c):
#         for f in imfiles:
#             os.remove(f)
#     else:
#         print('something went wrong and the video was not writting, saving image files...')
#
#     # print the number of time points/files acquired to make sure nothing dropped
#     print('Number of time points collected =  %d' % len(m[c]))
#     print('Number of files acquired = %d' % len(imfiles))
#
#     ax[c].plot(np.diff(m[c]), 'k')
#     ax[c].set_ylabel('cam%d time between frames (ms)' % c)
#     ax[c].set_xlabel('frame # FPS=%d' % fps[c])
#     ax[c].set_ylim([0, 50])
# millis = m
#
# # save the actual frame times
# with h5py.File(expname + ".hdf5", "w") as f:
#     grp = f.create_group('experiment_info')
#     grp.attrs['expdate'] = np.string_(expdate)
#     grp.attrs['animal'] = np.string_(animal)
#     grp.attrs['condition'] = np.string_(condition)
#     for i, l in enumerate(millis):
#         grp.create_dataset('camtiming_' + str(i), data=l, dtype='i')
#     for i, l in enumerate(fps):
#         grp.create_dataset('fps_' + str(i), data=l, dtype='i')
#     grp = f.create_group('trial_info')
#     grp.create_dataset("platform", data=platform, dtype='i')
#     grp.create_dataset("distance", data=distance, dtype='i')
#     grp.create_dataset("trial_outcome", data=trial_outcome, dtype='i')
#     grp.create_dataset("jump_time", data=jump_time, dtype='i')
#     grp.create_dataset("laser_trial", data=laser_trial, dtype='i')
#
# fig.savefig(expname + '_camtiming.png')
# plt.show()