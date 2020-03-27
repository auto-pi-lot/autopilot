#!/bin/bash

# colors
RED='\033[0;31m'
NC='\033[0m'


################
# update and install packages
echo -e "\n\n${RED}Installing necessary packages...\n\n ${NC}"

sudo apt-get update
sudo apt-get install -y \
    build-essential \
    cmake \
    git \
    python3-dev \
    libatlas-base-dev \
    libsamplerate0-dev \
    libsndfile1-dev \
    libreadline-dev \
    libasound-dev \
    i2c-tools \
    libportmidi-dev \
    liblo-dev \
    libhdf5-dev \
    libzmq-dev \
    libffi-dev

    # python3-pip \

#    python3-distutils \
#    python3-setuptools \

# install necessary python packages
echo -e "\n\n${RED}Initializing submodules\n\n ${NC}"

# clone submodules if we haven't already
git submodule init && git submodule update


#############
# performance




############
# audio



#######
# setup visual stim
#if [ "$visualstim" == "y" ]; then
#    echo -e "\n${RED}Installing X11 Server.. ${NC}"
#    sudo apt-get install -y xserver-xorg xorg-dev xinit xserver-xorg-video-fbdev python-opencv mesa-utils
#
#    echo -e "\n${RED}Installing Psychopy dependencies.. ${NC}"
#    pip3 install \
#        pyopengl \
#        pyglet \
#        pillow \
#        moviepy \
#        configobj \
#        json_tricks \
#        arabic-reshaper \
#        astunparse \
#        esprima \
#        freetype-py \
#        gevent \
#        gitpython \
#        msgpack-numpy \
#        msgpack-python \
#        pyparallel \
#        pyserial \
#        python-bidi \
#        python-gitlab \
#        pyyaml \
#        sounddevice \
#        soundfile
#
#    echo -e "\n${RED}Compiling glfw... ${NC}"
#    cd $HOME/git
#    git clone https://github.com/glfw/glfw
#    cd glfw
#    cmake .
#    make -j7
#    sudo -H make install
#
#    echo -e "\n${RED}Installing Psychopy... ${NC}"
#
#    pip3 install psychopy --no_deps
#
#    sudo sh -c "echo winType = \"glfw\" >> /home/pi/.psychopy3/userPrefs.cfg"
#fi


#
############
## clone repo
##cd $GITDIR
##git clone https://github.com/wehr-lab/autopilot.git
#
#echo -e "\n\n${RED}System needs to reboot for changes to take effect, reboot now? ${NC}"
#read -p "reboot? (y/n): " DOREBOOT
#
#if [ "$DOREBOOT" == "y" ]; then
#    sudo reboot
#fi
#
#if [ "$visualstim" == "y" ]; then
#  echo -e "\n${RED}    ***For visual stimuli, you will need to enable the GL driver for the raspberry pi: \n    sudo raspi-config and then select Advanced > Gl Driver > GL (fake KMS)\n${NC}"
#fi











