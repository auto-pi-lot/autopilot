"""
Scripts used in :mod:`.run_script` and :mod:`.setup_autopilot` to install packages and configure the system environment

Scripts are contained in the :data:`.scripts.SCRIPTS` dictionary, and each script is of the form::

    'script_name': {
        'type': 'bool', # always bool, signals that gui elements should present it as a checkbox to run or not
        'text': 'human readable description of what the script does',
        'commands': [
            'list of shell commands'
        ]
    }

The  commands in each ``commands`` list are concatenated with ``&&``  and run sequentially (see
:func:`.run_script.call_series` ). Certain commands that are expected to fail but don't impact the outcome of the
rest of the script -- eg. making a directory that already exists -- can be made optional by using the syntax::

    [
        'required command',
        {'command':'optional command', 'optional': True}
    ]

This concatenates the command with a ``; `` which doesn't raise an error if the command fails and allows the rest of
the script to proceed.

.. note::

    The above syntax will be used in the future for additional parameterizations that need to be made to scripts (
    though being optional is the only paramaterization avaialable now).

.. note::

    An unadvertised feature of ``raspi-config`` is the ability to run commands frmo the cli --
    find the name of a command here: https://github.com/RPi-Distro/raspi-config/blob/master/raspi-config
    and then use it like this: ``sudo raspi-config nonint function_name argument`` , so for example
    to enable the camera one just calls ``sudo raspi-config nonint do_camera 0`` (where turning the
    camera on, perhaps counterintuitively, is ``0`` which is true for all commands)

.. todo::

    Probably should have these use :data:`.prefs.get('S')copes` as well
"""

from collections import OrderedDict as odict

SCRIPTS = odict({
    'env_pilot': {
        'type': 'bool',
        'text': 'install system packages necessary for autopilot Pilots? (required if they arent already)',
        'commands': [
            "sudo apt-get update",
            "sudo apt-get install -y build-essential cmake git python3-dev libatlas-base-dev libsamplerate0-dev libsndfile1-dev libreadline-dev libasound-dev i2c-tools libportmidi-dev liblo-dev libhdf5-dev libzmq3-dev libffi-dev",
        ]
    },
    'env_terminal': {
        'type': 'bool',
        'text': 'install system packages necessary for autopilot Terminals? (required if they arent already)',
        'commands': [
            'sudo apt-get update',
            'sudo apt-get install -y \
                libxcb-icccm4 \
                libxcb-image0 \
                libxcb-keysyms1 \
                libxcb-randr0 \
                libxcb-render-util0 \
                libxcb-xinerama0 \
                libxcb-xfixes0'
        ]
    },
    'performance': {
        'type': 'bool',
        'text': 'Do performance enhancements? (recommended, change cpu governor and give more memory to audio)',
        'commands': [
            'sudo systemctl disable raspi-config',
            'sudo sed -i \'/^exit 0/i echo "performance" | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor\' /etc/rc.local',
            'sudo sh -c "echo @audio - memlock 256000 >> /etc/security/limits.conf"',
            'sudo sh -c "echo @audio - rtprio 75 >> /etc/security/limits.conf"',
            'sudo sh -c "echo vm.swappiness = 10 >> /etc/sysctl.conf"' # https://www.raspberrypi.org/forums/viewtopic.php?t=198765
        ]
    },
    'change_pw': {
        'type': 'bool',
        'text': "If you haven't, you should change the default raspberry pi password or you _will_ get your identity stolen. Change it now?",
        'commands': ['passwd']
    },
    'set_locale': {
        'type': 'bool',
        'text': 'Would you like to set your locale?',
        'commands': ['sudo dpkg-reconfigure locales',
                     'sudo dpkg-reconfigure keyboard-configuration']
    },
    'hifiberry': {
        'type': 'bool',
        'text': 'Setup Hifiberry DAC/AMP?',
        'commands': [
            {'command': 'sudo adduser pi i2c', 'optional': True},
            'sudo sed -i \'s/^dtparam=audio=on/#dtparam=audio=on/g\' /boot/firmware/config.txt',
            'sudo sed -i \'$s/$/\\ndtoverlay=hifiberry-dacplus\\ndtoverlay=i2s-mmap\\ndtoverlay=i2c-mmap\\ndtparam=i2c1=on\\ndtparam=i2c_arm=on/\' /boot/firmware/config.txt',
            'echo -e \'pcm.!default {\\n type hw card 0\\n}\\nctl.!default {\\n type hw card 0\\n}\' | sudo tee /etc/asound.conf'
        ]
    },
    # 'viz': {
    #     'type': 'bool',
    #     'text': 'Install X11 server and psychopy for visual stimuli?'
    # },
    'bluetooth': {
        'type': 'bool',
        'text': 'Disable Bluetooth? (recommended unless you\'re using it <3',
        'commands': [
            'sudo sed - i \'$s/$/\ndtoverlay=pi3-disable-bt/\' /boot/firmware/config.txt',
            'sudo systemctl disable hciuart.service',
            'sudo systemctl disable bluealsa.service',
            'sudo systemctl disable bluetooth.service'
        ],
    },
    'systemd': {
        'type': 'bool',
        'text': 'Install Autopilot as a systemd service?\nIf you are running this command in a virtual environment it will be used to launch Autopilot'
    },
    'alias': {
        'type': 'bool',
        'text': 'Create an alias to launch with "autopilot" (must be run from setup_autopilot, calls make_alias)'
    },
    'jackd_source': {
        'type': 'bool',
        'text': 'Install jack audio from source, try this if youre having compatibility or runtime issues with jack (required if AUDIOSERVER == jack)',
        'commands': [
            "git clone https://github.com/jackaudio/jack2 --depth 1",
            "cd jack2",
            "./waf configure --alsa=yes --libdir=/usr/lib/arm-linux-gnueabihf/",
            "./waf build -j6",
            "sudo ./waf install",
            "sudo ldconfig",
            "sudo sh -c \"echo @audio - memlock 256000 >> /etc/security/limits.conf\"",  # giving jack more juice
            "sudo sh -c \"echo @audio - rtprio 75 >> /etc/security/limits.conf\"",
            "cd ..",
            "rm -rf ./jack2"
        ]
    },
    'opencv': {
        'type': 'bool',
        'text': 'Install OpenCV from source, including performance enhancements for ARM processors (takes awhile)',
        'commands': [
            "sudo apt-get install -y build-essential cmake ccache unzip pkg-config libjpeg-dev libpng-dev libtiff-dev libavcodec-dev libavformat-dev libswscale-dev libv4l-dev libxvidcore-dev libx264-dev ffmpeg libgtk-3-dev libcanberra-gtk* libatlas-base-dev gfortran python2-dev python-numpy",
            "git clone https://github.com/opencv/opencv.git",
            "git clone https://github.com/opencv/opencv_contrib",
            "cd opencv",
            "mkdir build",
            "cd build",
            "cmake -D CMAKE_BUILD_TYPE=RELEASE \
                -D CMAKE_INSTALL_PREFIX=/usr/local \
                -D OPENCV_EXTRA_MODULES_PATH=/home/pi/git/opencv_contrib/modules \
                -D BUILD_TESTS=OFF \
                -D BUILD_PERF_TESTS=OFF \
                -D BUILD_DOCS=OFF \
                -D WITH_TBB=ON \
                -D CMAKE_CXX_FLAGS=\"-DTBB_USE_GCC_BUILTINS=1 -D__TBB_64BIT_ATOMICS=0\" \
                -D WITH_OPENMP=ON \
                -D WITH_IPP=OFF \
                -D WITH_OPENCL=ON \
                -D WITH_V4L=ON \
                -D WITH_LIBV4L=ON \
                -D ENABLE_NEON=ON \
                -D ENABLE_VFPV3=ON \
                -D PYTHON3_EXECUTABLE=/usr/bin/python3 \
                -D PYTHON_INCLUDE_DIR=/usr/include/python3.7 \
                -D PYTHON_INCLUDE_DIR2=/usr/include/arm-linux-gnueabihf/python3.7 \
                -D OPENCV_ENABLE_NONFREE=ON \
                -D INSTALL_PYTHON_EXAMPLES=OFF \
                -D WITH_CAROTENE=ON \
                -D CMAKE_SHARED_LINKER_FLAGS='-latomic' \
                -D BUILD_EXAMPLES=OFF ..",
            "sudo sed -i 's/^CONF_SWAPSIZE=100/CONF_SWAPSIZE=2048/g' /etc/dphys-swapfile", # increase size of swapfile so multicore build works
            "sudo /etc/init.d/dphys-swapfile stop",
            "sudo /etc/init.d/dphys-swapfile start",
            "make -j4",
            "sudo --preserve-env=PATH make install",
            "sudo ldconfig",
            "sudo sed -i 's/^CONF_SWAPSIZE=2048/CONF_SWAPSIZE=100/g' /etc/dphys-swapfile",
            "sudo /etc/init.d/dphys-swapfile stop",
            "sudo /etc/init.d/dphys-swapfile start"
        ]
    },
    'performance_cameras': {
        'type': 'bool',
        'text': 'Do performance enhancements for video - mods to uvcvideo and increasing usbfs',
        'commands': [
            "sudo sh -c 'echo options uvcvideo nodrop=1 timeout=10000 quirks=0x80 > /etc/modprobe.d/uvcvideo.conf'",
            "sudo rmmod uvcvideo",
            "sudo modprobe uvcvideo",
            "sudo sed -i \"/^exit 0/i sudo sh -c 'echo ${usbfs_size} > /sys/module/usbcore/parameters/usbfs_memory_mb'\" /etc/rc.local"
        ],
    },
    'picamera': {
        'type': 'bool',
        'text': 'Enable PiCamera (with raspi-config)',
        'commands': [
            'sudo raspi-config nonint do_camera 0'
        ]
    },
    'picamera_legacy':{
      'type':'bool',
      'text': 'Enable Legacy Picamera driver (for raspiOS Bullseye)',
      'commands': [
          'sudo raspi-config nonint do_legacy 0'
      ]
    },
    'pigpiod': {
        'type': 'bool',
        'text': 'Install pigpio daemon (sneakers fork that gives full timestamps and has greater capacity for scripts)',
        'commands': [
            'wget https://github.com/sneakers-the-rat/pigpio/archive/master.zip',
            'unzip master.zip',
            'cd pigpio-master',
            'make -j4',
            'sudo --preserve-env=PATH make install',
            'cd ..',
            'sudo rm -rf ./pigpio-master',
            'sudo rm ./master.zip'
        ]
    },
    'i2c': {
        'type': 'bool',
        'text': 'Enable i2c and set baudrate to 100kHz',
        'commands': [
            'sudo sed -i \'s/^#dtparam=i2c_arm=on/dtparam=i2c_arm=on/g\' /boot/firmware/config.txt',
            'sudo sed -i \'$s/$/\ni2c_arm_baudrate=100000/\' /boot/firmware/config.txt',
            'sudo sed -i \'$s/$/\ni2c-dev/\' /etc/modules',
            'sudo dtparam i2c_arm=on',
            'sudo modprobe i2c-dev'
        ]
    }
})
""""""
