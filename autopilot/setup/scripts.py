from collections import OrderedDict as odict

# TODO: merge these into one...

ENV_PILOT = odict({
    'env_pilot'   : {'type': 'bool',
                     'text': 'install system packages necessary for autopilot? (required if they arent already)'},
    'performance' : {'type': 'bool',
                     'text': 'Do performance enhancements? (recommended, change cpu governor and give more memory to audio)'},
    'change_pw': {'type': 'bool',
                  'text': "If you haven't, you should change the default raspberry pi password or you _will_ get your identity stolen. Change it now?"},
    'set_locale': {'type': 'bool',
                   'text': 'Would you like to set your locale?'},
    'hifiberry' : {'type': 'bool',
                   'text': 'Setup Hifiberry DAC/AMP?'},
    'viz'       : {'type': 'bool',
                   'text': 'Install X11 server and psychopy for visual stimuli?'},
    'bluetooth' : {'type': 'bool',
                   'text': 'Disable Bluetooth? (recommended unless you\'re using it <3'},
    'systemd'   : {'type': 'bool',
                   'text': 'Install Autopilot as a systemd service?\nIf you are running this command in a virtual environment it will be used to launch Autopilot'},
    'jackd'     : {'type': 'bool',
                   'text': 'Install jack audio (required if AUDIOSERVER == jack)'},
    'pigpiod'   : {'type': 'bool',
                   'text': 'Install pigpio daemon'}
})
PILOT_ENV_CMDS = {
    'performance':
        ['sudo systemctl disable raspi-config',
         'sudo sed -i \'/^exit 0/i echo "performance" | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor\' /etc/rc.local',
         'sudo sh -c "echo @audio - memlock 256000 >> /etc/security/limits.conf"',
         'sudo sh -c "echo @audio - rtprio 75 >> /etc/security/limits.conf"',
         ],
    'performance_cameras':
        [
            "sudo sh -c 'echo options uvcvideo nodrop=1 timeout=10000 quirks=0x80 > /etc/modprobe.d/uvcvideo.conf'",
            "sudo rmmod uvcvideo",
            "sudo modprobe uvcvideo",
            "sudo sed -i \"/^exit 0/i sudo sh -c 'echo ${usbfs_size} > /sys/module/usbcore/parameters/usbfs_memory_mb'\" /etc/rc.local"
        ],
    'change_pw': ['passwd'],
    'set_locale': ['sudo dpkg-reconfigure locales',
                   'sudo dpkg-reconfigure keyboard-configuration'],
    'hifiberry':
        [
            {'command':'sudo adduser pi i2c', 'optional':True},
            'sudo sed -i \'s/^dtparam=audio=on/#dtparam=audio=on/g\' /boot/config.txt',
            'sudo sed -i \'$s/$/\\ndtoverlay=hifiberry-dacplus\\ndtoverlay=i2s-mmap\\ndtoverlay=i2c-mmap\\ndtparam=i2c1=on\\ndtparam=i2c_arm=on/\' /boot/config.txt',
            'echo -e \'pcm.!default {\\n type hw card 0\\n}\\nctl.!default {\\n type hw card 0\\n}\' | sudo tee /etc/asound.conf'
        ],
    'viz': [],
    'bluetooth':
        [
            'sudo sed - i \'$s/$/\ndtoverlay=pi3-disable-bt/\' /boot/config.txt',
            'sudo systemctl disable hciuart.service',
            'sudo systemctl disable bluealsa.service',
            'sudo systemctl disable bluetooth.service'
        ],
    'jackd':
        ['sudo apt update && sudo apt install -y jackd2'],
    'jackd_source':
        [
            "git clone git://github.com/jackaudio/jack2 --depth 1",
            "cd jack2",
            "./waf configure --alsa=yes --libdir=/usr/lib/arm-linux-gnueabihf/",
            "./waf build -j6",
            "sudo ./waf install",
            "sudo ldconfig",
            "sudo sh -c \"echo @audio - memlock 256000 >> /etc/security/limits.conf\"",             # giving jack more juice
            "sudo sh -c \"echo @audio - rtprio 75 >> /etc/security/limits.conf\"",
            "cd ..",
            "rm -rf ./jack2"
        ],
    'opencv':
        [
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
        ],
    'env_pilot':
        [
            "sudo apt-get update",
            "sudo apt-get install -y build-essential cmake git python3-dev libatlas-base-dev libsamplerate0-dev libsndfile1-dev libreadline-dev libasound-dev i2c-tools libportmidi-dev liblo-dev libhdf5-dev libzmq-dev libffi-dev",
        ],
    'pigpiod':[
        'wget https://github.com/sneakers-the-rat/pigpio/archive/master.zip',
        'unzip master.zip',
        'cd pigpio-master',
        'make -j4',
        'sudo --preserve-env=PATH make install',
        'cd ..',
        'sudo rm -rf ./pigpio-master',
        'sudo rm ./master.zip'
    ]

}