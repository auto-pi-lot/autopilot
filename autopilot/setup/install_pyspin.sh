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
sudo sh -c "echo \\n >> /etc/apt/sources.list"
sudo sh -c "echo \#\#\# START BACKPORTS \#\#\# backports for pyspin >> /etc/apt/sources.list"
sudo sh -c "echo deb http://ports.ubuntu.com/ubuntu-ports xenial-backports main restricted universe multiverse >> /etc/apt/sources.list"
sudo sh -c "echo deb http://ports.ubuntu.com/ubuntu-ports xenial-updates main restricted universe multiverse >> /etc/apt/sources.list"
sudo sh -c "echo deb http://ports.ubuntu.com/ubuntu-ports xenial main restricted universe multiverse >> /etc/apt/sources.list"
sudo sh -c "echo \#\#\# END BACKPORTS \#\#\# >> /etc/apt/sources.list"


echo -e "\n${RED}Updating Repositories${NC}"
sudo apt-get update --allow-insecure-repositories

echo -e "\n${RED}Installing Dependencies${NC}"
sudo apt install -y \
  libavutil-ffmpeg54 \
  libavcodec-ffmpeg56 \
  libswscale-ffmpeg \
  libavformat-ffmpeg56 \
  python-numpy \
  python-matplotlib

#python -m pip install --upgrade numpy matplotlib


echo -e "\n${RED}Attempting to download Spinnaker SDK files from static link${NC}"

cd ~/
mkdir spinnaker
cd spinnaker

SPINNAME="spinnaker-1.27.0.48-Ubuntu16.04-armhf-pkg.tar.gz"
PYSPINNAME="spinnaker_python-1.27.0.48-Ubuntu16.04-cp27-cp27mu-linux_armv7l.tar.gz"

# spinnaker-1.27.0.48-Ubuntu16.04-armhf-pkg.tar.gz
# https://flir.app.boxcn.net/v/SpinnakerSDK/folder/74727114471
wget -O ${SPINNAME} \
 https://public.boxcloud.com/d/1/b1\!FcjSQRSSVWTqnLboz6-BN3TZ5Zj-xmYnfMAD_hoyBkEsJiXUSocDEZINPktue1muWB1ggvp6aKjUxOjR9lbiuL6coU1JFZvrZJqjACgbT5j5EOK9ER-kHiUcipVrW8vilNE1W2zid1UqDqieeHiCQSEwR8TKk9xCMNIdUObf3WMykJbjhCM88IruSwYdtk6ammev42PIYpN2tCgru20gu5G9dYlbpL7EqWfk34SaPOfmlgJVrtBvSBXnCL1lpZtuQl-NG5Wr1ZD-51OUDNJjhiETwEsZVjP6UcNPPjuqTjwg3XclXIJ-gN5NRDBiEGbiqtK6DpGJJi3H5xddpZnKHug7rPihwauOT4tsIpMy_mj_CqETkE3imXGT8ppOXvJAVixkcvGmrnQ0-FLLOd0yIVuCwvMFz2XCWAOtAyh66rhdnQeOS3wt8KAUGv1mWH2XHGxpIUV8nOYPDPgCmTER4dcoxKQO5l-uvzGGGoV0rHyBGAiYqH2M_erBfwynp_HD9GkAm179GcHQua04T5D58Z5EJxKrDet0C3-euuC_BtLGSereihA5inKUs5eNY93dsS2wOkIfXo6xrIpq0fOQPntanHwjj-MHy-9z2atlDq2ct27O49-QYJXL_i0Vh7zWGxrV4JoUpYJraPmnPTGV471pReqHB1-OiH13cIWTofj5DB4c-JReNVF4HPD7vHajrmPyPExFw5JuH_ycoQXBtGh9GvYS_V9n983-1PHvI4a91aSJlZGrY0Fn9ArNe9Bq90Pv2pUW_hxYZc1TatJcG8B75PckfpkN3JqSlMpa3FKhVcEgBaoLgSccM6FxP469Sb8QeMq6xTC_mjH6luLgUA1nr_gsGxUBiIhqbnclja1p0Bl1roVRutpDoOz8rKttl3kO9QrkQhlQ7t0_Qqyw2nBzr1iAfWKpW1z7irVCBD932uO8ebTsFtZFTYHZUYv8aP--T87CECsUh1dhBqrHvU2eCa6ahe3n-mpnM7vlOIe-Ez606-nCtkauhg5GVwF76AnM7r9ggMV4JN0JdFU_6dzQUFOvJm8mynHTDVejzPVbtk6-CwuJTe9ZzZHPZ_rySYsva3HYpxOaXzjlvkcqzlTqHc70GZwVvjdH6T0JGVzn1-aYQO9-3gC461JU6dR0uCxCiv2axCeACIsUkhm-cT3gm5dmBqp-HdxxrhNrufwSRt6SeZH5L2Cy0sRXPe6HDgstJubh7pyAz8iVpDgsHfNJGcYkQQe5kYvoCeCN6a16ydr_Dlq1j0SWZlQxp8arRvIFHrWW6gzDxSla6UmhDvcBU0BksAvHl2l1cv0OChfE6LjQihJJyzjG/download
# spinnaker_python-1.27.0.48-Ubuntu16.04-cp27-cp27mu-linux_armv7l.tar.gz
# https://flir.app.boxcn.net/v/SpinnakerSDK/folder/74728406949
wget -O ${PYSPINNAME} \
  https://public.boxcloud.com/d/1/b1\!ApKOjI7Rlh1FXPhMsP2XbqkMvFqmkB-9i7nL3eF5U6R8gJOxkPRcJ5-raj8albEw-TIbP0HJ2a_j65dMzaa4VKxMJoA2fI9kAYpRY3KMQrnUzyg0NXxkOn5Wq_WraxH5B3-s5phMz-VBrjTxQUAj3aNVYlQVZnLsKk7mh56zVgBKZpPEp-jUq9JnbOAkLxV0txkzOzW7y1R3XOo1qZ0lbZcB-F9osMUbJFTGmPvC0uR1gWYCFfn-jAfgbsP1oBOnYW3fQE9LB2M78HZi_nS1HfZJIR9IZtCtloyzBa5QMSRuDca88I4xugGLAOkeNvlRec6QBmjZDCjiI5TgQoYOjn2Rw7kM0iCMdIFLMAXmB2G3Bhd0ubVr2Xzg5BbCnr8Tw5BNUV2vTB8R7kVzsU1vzE5TwyvuVldzacxSdxelMXAisGrwKfxB9cBJDrELz73dzWnWhW_yGYEl0-7tI-KEKecXEY1EWL82vzs6KLTYxdcrzSyIy7tdiIjnFFWFFgNN-EgVgjeJkzjvXk-A-lYsnTw-HUoZlSCNBqOTX7Nd5_tkAFCao6XXeqC-IU18Dbl87tPzOvgNde78nBT6uTqmpvUgxniSkgQmmiymd9GkoRrfsjtRtnx1fJXM3Jpek35z3BRweYwbRm79H7IkuziS1lXONxgNvNXhnUmL0goo8Mg-nFIgQAofDSw0FRIxhZWkXZrgwF9hTGEVLKEOUvD0vfLQZp2oUEqPYG6vqJW59ywtk_O1cl4KHfO27EEUcR0gy4LU8L_wx5YQdCksHFqDLOjvztOT6XQjus1BUVINq6jobXjqf7S57xQEZQamCQItoG35D7Lw68rUU678GihuBgj3Jq2eHKiCZpH5dvyf2fH8VPqC807FvvxkfJhsmvtOzyvuKogoRsKFpKvLCA3EwqsxxUkpRfQsoEaEGA2ojtQqxpIC7pU-TbDj0aKz7flU6Bz31zsNxw4wD1IxxiEv4duaZ0aZNOw0l_zsQvb0vh8ikpZSyN4MTx210Mwax-uGlgYk9rkC7r1IQEY0y25xZ3ZKNIi0xvr-bKckCq8s73w272gz5gI9tW2wCtmsaDQBhwU9di542rKHSvqLSV3AKEcI5tlCUxVT64i7O0U_u29th9beVL9_mMqZOny-zyL4GNMHMvJkA6iDFBWCR3jhlMuAJ8pBDxGBB_raT2tEFlwCIxG6kEjGd3U2ICTxcJrD3cn3JS3BNkPbnFnZi3-6YOG8b2rvTOn8Pn490RX89-r-JY2wUv7uPANMfKodlSktR_ahRIpD8Yf6dcQxnm8BpVzv0-oCFrXyGiVbt5YGLHpPlxKRmAULCXmOPFeAuXVwqS1uKEc9jRCPprzsUCfPyw../download

# check if we were able to get it
got_spin=true
if [ ! -f ${SPINNAME} ]; then
    got_spin=false
fi
if [ ! -f ${PYSPINNAME} ]; then
    got_spin=false
fi

# and it's also not just a stub/error page
min_size=1000
spin_size="$(wc -c < ${SPINNAME})"
pyspin_size="$(wc -c < ${PYSPINNAME})"

if [ $spin_size -le $min_size ]; then
    got_spin=false
fi
if [ $pyspin_size -le $min_size ]; then
    got_spin=false
fi

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
tar -xvf ${SPINNAME} -C spinnaker
cd spinnaker
cd *
sudo sh install_spinnaker_arm.sh

cd ../../
mkdir pyspin
tar -xvf ${PYSPINNAME} -C pyspin
cd pyspin
python -m pip install spinnaker_*.whl




