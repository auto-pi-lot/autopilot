#!/bin/sh

############
# user args

read -p "If you haven't changed it, you should change the default raspberry pi password. Change it now? (y/n): " changepw

if ["$changepw" == "y"]; then
    passwd
fi

read -p "Would you like to set your locale? Use the space bar to select/deselect items on the screen (y/n): " changelocale

if ["$changelocale" == "y"]; then
    sudo dpkg-reconfigure locales
    sudo dpkg-reconfigure keyboard-configuration
fi

read -p "Install jack audio? (y/n): " installjack

read -p "Setup hifiberry dac/amp? (y/n): " setuphifi

read -p "Disable bluetooth? (y/n): " disablebt

###########
# prelims

# create git folder if it don't already exist
GITDIR=$HOME/git
if [-d "$GITDIR"]; then
    echo "\nmaking git directory at $HOME/git"
    mkdir $GITDIR
fi


################
# update and install packages
echo "Installing necessary packages...\n"

sudo apt-get update
sudo apt-get install -y \
    build-essential \
    cmake \
    git \
    python-pip \
    python2.7-dev 
    libsamplerate0-dev \
    libsndfile1-dev \
    libreadline-dev \
    libasound-dev \
    i2c-tools \
    libportmidi-dev \
    liblo-dev \
    libhdf5-dev \
    python-numpy \
    python-pandas \
    python-tables \
    libzmq-dev \
    libffi-dev


# install necessary python packages
sudo -H pip install -U pyzmq npyscreen tornado inputs

# install pigpio
cd $GITDIR
git clone https://github.com/joan2937/pigpio.git
cd pigpio
make -j6
sudo -H make install


#############
# security
#


#############
# performance

echo "\nDoing performance enhancements"

echo "\nChanging CPU governer to performance"

# disable startup script that changes cpu governor
# note that this is not the same raspi-config as you're thinking
sudo systemctl disable raspi-config

sed -i '/^exit 0/i echo "performance" | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor' /etc/rc.local

if ["$disablebt" == "y"]; then
    echo "\nDisabling bluetooth.."
    sudo sed -i '$s/$/\ndtoverlay=pi3-disable-bt/' /boot/config.txt
    sudo systemctl disable hciuart.service
    sudo systemctl disable bluealsa.service
    sudo systemctl disable bluetooth.service
fi



############
# audio

if ["$installjack" == "y"]; then
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
    sudo apt-get install python-cffi
    sudo -H pip install JACK-Client
fi

if ["$setuphifi" == "y"]; then
    # add pi user to i2c group
    sudo adduser pi i2c

    # turn onboard audio off
    sudo sed -i 's/^dtparam=audio=on/#dtparam=audio=on/g' /boot/config.txt

    # enable hifiberry stuff
    sudo sed -i '$s/$/\ndtoverlay=hifiberry-dacplus\ndtoverlay=i2s-mmap\ndtoverlay=i2c-mmap\ndtparam=i2c1=on\ndtparam=i2c_arm=on/' /boot/config.txt

    # edit alsa config so hifiberry is default sound card
    ALSAFILE=/etc/asound.conf
    if [-f "$ALSAFILE"]; then
        sudo touch $ALSAFILE
    fi

    sudo sed -i '1 i\pcm.!default {\n type hw card 0\n}\nctl.!default {\n type hw card 0\n}' $ALSAFILE

fi

###########
# clone repo
cd $GITDIR
git clone https://github.com/wehr-lab/RPilot.git











