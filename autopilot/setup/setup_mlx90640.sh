# make sure pigpio is installed

sudo apt-get update
sudo apt-get install -y libi2c-dev swig

# enable i2c module
sudo sed -i 's/^#dtparam=i2c_arm=on/dtparam=i2c_arm=on/g' /boot/firmware/config.txt

# increase baudrate
sudo sed -i '$s/$/\ndtparam=i2c_arm_baudrate=1000000/' /boot/firmware/config.txt

#cd ~/git
# clone submodules if we haven't already
git submodule init && git submodule update

# assuming this is being run from either the autopilot root or the setup folder...
# cd to the library dir.
if [ $(basename $PWD) == "setup" ]; then
  cd ../external/mlx90640-library
elif [ $(basename $PWD) == "autopilot" ]; then
  cd autopilot/external/mlx90640-library
fi

# disable building examples, extra dependencies
make all I2C_MODE=RPI
sudo make install

cd python/library
make build
sudo make install



