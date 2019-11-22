#!/bin/bash

# colors
RED='\033[0;31m'
NC='\033[0m'

# https://www.pyimagesearch.com/2018/09/26/install-opencv-4-on-your-raspberry-pi/
# https://docs.opencv.org/master/d7/d9f/tutorial_linux_install.html
# install prereqs


read -p "Upgrade installed packages? (y/n): " doupgrade
if [ "$doupgrade" == "n" ]; then
    echo -e "${RED}    not upgrading existing packages\n${NC}"
fi

# update and install packages
sudo apt-get update

if [ "$doupgrade" == "y" ]; then
    sudo apt-get upgrade -y
fi

echo -e "${RED}    Installing prereqs\n${NC}"
sudo apt-get install -y build-essential cmake ccache unzip pkg-config \
    libjpeg-dev libpng-dev libtiff-dev \
    libavcodec-dev libavformat-dev libswscale-dev libv4l-dev \
    libxvidcore-dev libx264-dev ffmpeg \
    libgtk-3-dev libcanberra-gtk* \
    libatlas-base-dev gfortran \
    python2-dev python-numpy

#python -m pip install numpy

echo -e "${RED}    Cloning OpenCV\n${NC}"

GITDIR=$HOME/git
mkdir $GITDIR
cd $GITDIR
git clone https://github.com/opencv/opencv.git
git clone https://github.com/opencv/opencv_contrib

echo -e "${RED}    Configuring OpenCV\n${NC}"

cd opencv
mkdir build
cd build

# https://www.pyimagesearch.com/2017/10/09/optimizing-opencv-on-the-raspberry-pi/

cmake -D CMAKE_BUILD_TYPE=RELEASE \
    -D CMAKE_INSTALL_PREFIX=/usr/local \
    -D OPENCV_EXTRA_MODULES_PATH=/home/pi/git/opencv_contrib/modules \
    -D BUILD_TESTS=OFF \
    -D BUILD_PERF_TESTS=OFF \
    -D BUILD_DOCS=OFF \
    -D WITH_TBB=ON \
    -D CMAKE_CXX_FLAGS="-DTBB_USE_GCC_BUILTINS=1 -D__TBB_64BIT_ATOMICS=0" \
    -D WITH_OPENMP=ON \
    -D WITH_IPP=OFF \
    -D WITH_OPENCL=ON \
    -D WITH_V4L=ON \
    -D WITH_LIBV4L=ON \
    -D ENABLE_NEON=ON \
    -D ENABLE_VFPV3=ON \
    -D PYTHON2_EXECUTABLE=/usr/bin/python \
    -D PYTHON_INCLUDE_DIR=/usr/include/python2.7 \
    -D PYTHON_INCLUDE_DIR2=/usr/include/arm-linux-gnueabihf/python2.6 \
    -D OPENCV_ENABLE_NONFREE=ON \
    -D INSTALL_PYTHON_EXAMPLES=OFF \
    -D WITH_CAROTENE=ON \
    -D CMAKE_SHARED_LINKER_FLAGS='-latomic' \
    -D BUILD_EXAMPLES=OFF ..

echo -e "${RED}    Temporarily increasing swap size\n${NC}"
# increase swap so multicore compile can have enough memory
sudo sed -i 's/^CONF_SWAPSIZE=100/CONF_SWAPSIZE=2048/g' /etc/dphys-swapfile
sudo /etc/init.d/dphys-swapfile stop
sudo /etc/init.d/dphys-swapfile start

echo -e "${RED}    Compiling OpenCV\n${NC}"
make -j4

echo -e "${RED}    Installing OpenCV\n${NC}"
sudo make install
sudo ldconfig

echo -e "${RED}    Reducing swap\n${NC}"
sudo sed -i 's/^CONF_SWAPSIZE=2048/CONF_SWAPSIZE=100/g' /etc/dphys-swapfile
sudo /etc/init.d/dphys-swapfile stop
sudo /etc/init.d/dphys-swapfile start

# increase uvcvideo timeout
# https://stackoverflow.com/a/12715374

echo -e "${RED}    Increasing timeout on uvcvideo -- necessary for multiple cameras\n${NC}"
sudo sh -c 'echo options uvcvideo nodrop=1 timeout=10000 quirks=0x80 > /etc/modprobe.d/uvcvideo.conf'
sudo rmmod uvcvideo
sudo modprobe uvcvideo


read -p "Permanently increase usbfs size?  (y/n/size in mb, default=1000MB): " usbfs_size
if [ "$usbfs_size" == "n" ]; then
    echo -e "${RED}    WARNING: You will need to manually increase usbfs in order to take large pictures or use multiple cameras\n${NC}"
    echo -e "${RED}    To do so, use a command like:\n${NC}"
    echo -e "${RED}    sudo sh -c 'echo 1000 > /sys/module/usbcore/parameters/usbfs_memory_mb'"
else
    if [ "$usbfs_size" == "y" ]; then
        usbfs_size=1000
    fi

    echo -e "${RED}    Setting usbfs to ${usbfs_size} on boot by editing /etc/rc.local\n${NC}"
    sudo sed -i "/^exit 0/i sudo sh -c 'echo ${usbfs_size} > /sys/module/usbcore/parameters/usbfs_memory_mb'" /etc/rc.local
fi

#sudo rmmod uvcvideo
#sudo modprobe uvcvideo nodrop=1 timeout=10000
# https://www.raspberrypi.org/forums/viewtopic.php?f=37&t=11745


