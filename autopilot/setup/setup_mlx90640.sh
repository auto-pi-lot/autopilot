# make sure pigpio is installed

sudo apt-get update
sudo apt-get install -y libi2c-dev swig

# enable i2c module
sudo sed -i 's/^#dtparam=i2c_arm=on/dtparam=i2c_arm=on/g' /boot/config.txt

# increase baudrate
sudo sed -i '$s/$/\ndtparam=i2c_arm_baudrate=1000000/' /boot/config.txt

cd ~/git
git clone https://github.com/sneakers-the-rat/mlx90640-library.git
cd mlx90640-library

# disable building examples, extra dependencies
sudo sed -i 's/^all: libMLX90640_API.a libMLX90640_API.so examples/all: libMLX90640_API.a libMLX90640_API.so/g' Makefile
make all I2C_MODE=LINUX
sudo make install

cd python/library
make build
sudo make install



