#!/usr/bin/env bash

# currently, spinnaker hasn't released armhf builds for its most recent version of PySpin
# so we have to use old backports

# colors
RED='\033[0;31m'
NC='\033[0m'

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

# add backports to /etc/apt/sources.list
echo -e "\n${RED}Adding backports${NC}"
sudo sh -c "echo >> /etc/apt/sources.list"
sudo sh -c "echo \#\#\# START BACKPORTS \#\#\# backports for pyspin >> /etc/apt/sources.list"
sudo sh -c "echo deb http://ports.ubuntu.com/ubuntu-ports xenial-backports main restricted universe multiverse >> /etc/apt/sources.list"
sudo sh -c "echo deb http://ports.ubuntu.com/ubuntu-ports xenial-updates main restricted universe multiverse >> /etc/apt/sources.list"
sudo sh -c "echo deb http://ports.ubuntu.com/ubuntu-ports xenial main restricted universe multiverse >> /etc/apt/sources.list"
sudo sh -c "echo \#\#\# END BACKPORTS \#\#\# >> /etc/apt/sources.list"


echo -e "\n${RED}Updating Repositories${NC}"
sudo apt-get update --allow-insecure-repositories

echo -e "\n${RED}Installing Dependencies${NC}"
sudo apt install -y --allow-unauthenticated \
  libavutil-ffmpeg54 \
  libavcodec-ffmpeg56 \
  libavformat-ffmpeg56 \
  python-numpy \
  python-matplotlib

  #libswscale-ffmpeg \

python -m pip install numpy matplotlib requests


echo -e "\n${RED}Attempting to download Spinnaker SDK files from static link${NC}"

#cd ~/
#if [ ! -d "spinnaker" ]; then
#    echo -e "\n${RED}Making spinnaker directory in user directory${NC}"
#    mkdir spinnaker
#fi
#cd spinnaker

#SPINNAME="spinnaker-1.27.0.48-Ubuntu16.04-armhf-pkg.tar.gz"
#PYSPINNAME="spinnaker_python-1.27.0.48-Ubuntu16.04-cp27-cp27mu-linux_armv7l.tar.gz"
SPINURL="https://flir.app.boxcn.net/v/SpinnakerSDK/file/545650882106"
PYSPINURL="https://flir.app.boxcn.net/v/SpinnakerSDK/file/545654685895"

python -c "from autopilot.setup.request_helpers import download_box; download_box('${SPINURL}')"
python -c "from autopilot.setup.request_helpers import download_box; download_box('${PYSPINURL}')"

SPINFILES=( spinnaker-*.tar.gz )
PYSPINFILES=( spinnaker_python*.tar.gz )

# check if we were able to get it
got_spin=true
if ! (( ${#SPINFILES[@]} )); then
    got_spin=false
fi
if ! (( ${#PYSPINFILES[@]} )); then
    got_spin=false
fi
#
## and it's also not just a stub/error page
#min_size=1000
#spin_size="$(wc -c < ${SPINNAME})"
#pyspin_size="$(wc -c < ${PYSPINNAME})"
#
#if [ $spin_size -le $min_size ]; then
#    got_spin=false
#fi
#if [ $pyspin_size -le $min_size ]; then
#    got_spin=false
#fi

# if couldn't get it, prompt user to get it
if [ "$got_spin" = false ]; then
    echo -e "${RED}Failed to download with static link (submit an issue on github!)\n${NC}"
    echo -e "${RED}Go to https://flir.app.boxcn.net/v/SpinnakerSDK/ and download\n${NC}"
    echo -e "${RED}    - Spinnaker SDK for armhf (most recently in Linux>Ubuntu 16.04)\n${NC}"
    echo -e "${RED}    - PySpin for armhf or armv7 (>python>armv7)\n${NC}"
    echo -e "${RED}And put them in the current directory\n${NC}"
    read -p "What is the file name of the spinnaker sdk?: " SPINNAME
    read -p "What is the file name of PySpin?: " PYSPINNAME
fi

# unzip and install spinnaker sdk
# make a directory b/c we don't know what the subdir will be called,
# want to only have one subdir
mkdir spinnaker
tar -xvf ${SPINFILES[0]} -C spinnaker
cd spinnaker
cd *
sudo sh install_spinnaker_arm.sh

cd ../../
mkdir pyspin
tar -xvf ${PYSPINFILES[0]} -C pyspin
cd pyspin
python3 -m pip install spinnaker_*.whl

cd ../

# remove entries from sources.list
sed -i '/\#\#\# START BACKPORTS \#\#\#/,/\#\#\# END BACKPORTS \#\#\#/d' /etc/apt/sources.list

read -p "Clean up downloaded files? (y/n): " cleanup
if [ "$cleanup" == "y" ]; then
    rm -r ./spinnaker*
    rm -r ./pyspin*
fi




