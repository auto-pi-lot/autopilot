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
    libsamplerate0-dev \
    libsndfile1-dev \
    libreadline-dev \
    libasound-dev \
    i2c-tools \
    libportmidi-dev \
    liblo-dev \
    libhdf5-dev \
    python3-numpy \
    python3-pandas \
    python3-tables \
    python3-cffi \
    libzmq-dev \
    libffi-dev \
    blosc

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

if [ "$installjack" == "y" ]; then
    echo "\nInstalling jack audio"
    cd $HOME/git
    git clone git://github.com/jackaudio/jack2 --depth 1
    cd jack2
    ./waf configure --alsa=yes --libdir=/usr/lib/arm-linux-gnueabihf/
    ./waf build -j6
    sudo ./waf install
    sudo ldconfig

    # giving jack more juice
    sudo sh -c "echo @audio - memlock 256000 >> /etc/security/limits.conf"
    sudo sh -c "echo @audio - rtprio 75 >> /etc/security/limits.conf"

    # installing jack python packages
 a   pip3 install JACK-Client
fi

if [ "$setuphifi" == "y" ]; then
    # add pi user to i2c group
    sudo adduser pi i2c

    # turn onboard audio off
    sudo sed -i 's/^dtparam=audio=on/#dtparam=audio=on/g' /boot/config.txt

    # enable hifiberry stuff
    sudo sed -i '$s/$/\ndtoverlay=hifiberry-dacplus\ndtoverlay=i2s-mmap\ndtoverlay=i2c-mmap\ndtparam=i2c1=on\ndtparam=i2c_arm=on/' /boot/config.txt

    # edit alsa config so hifiberry is default sound card
    ALSAFILE=/etc/asound.conf
#    if [ ! -f "$ALSAFILE" ]; then
#        sudo touch $ALSAFILE
#    fi

    #sudo sed -i '1 i\pcm.!default {\n type hw card 0\n}\nctl.!default {\n type hw card 0\n}' $ALSAFILE

    echo -e 'pcm.!default {\n type hw card 0\n}\nctl.!default {\n type hw card 0\n}' | sudo tee $ALSAFILE
fi

#######
# setup visual stim
if [ "$visualstim" == "y" ]; then
    echo -e "\n${RED}Installing X11 Server.. ${NC}"
    sudo apt-get install -y xserver-xorg xorg-dev xinit xserver-xorg-video-fbdev python-opencv mesa-utils

    echo -e "\n${RED}Installing Psychopy dependencies.. ${NC}"
    pip3 install \
        pyopengl \
        pyglet \
        pillow \
        moviepy \
        configobj \
        json_tricks \
        arabic-reshaper \
        astunparse \
        esprima \
        freetype-py \
        gevent \
        gitpython \
        msgpack-numpy \
        msgpack-python \
        pyparallel \
        pyserial \
        python-bidi \
        python-gitlab \
        pyyaml \
        sounddevice \
        soundfile

    echo -e "\n${RED}Compiling glfw... ${NC}"
    cd $HOME/git
    git clone https://github.com/glfw/glfw
    cd glfw
    cmake .
    make -j7
    sudo -H make install

    echo -e "\n${RED}Installing Psychopy... ${NC}"

    pip3 install psychopy --no_deps

    sudo sh -c "echo winType = \"glfw\" >> /home/pi/.psychopy3/userPrefs.cfg"
fi



###########
# clone repo
#cd $GITDIR
#git clone https://github.com/wehr-lab/autopilot.git

echo -e "\n\n${RED}System needs to reboot for changes to take effect, reboot now? ${NC}"
read -p "reboot? (y/n): " DOREBOOT

if [ "$DOREBOOT" == "y" ]; then
    sudo reboot
fi

if [ "$visualstim" == "y" ]; then
  echo -e "\n${RED}    ***For visual stimuli, you will need to enable the GL driver for the raspberry pi: \n    sudo raspi-config and then select Advanced > Gl Driver > GL (fake KMS)\n${NC}"
fi











