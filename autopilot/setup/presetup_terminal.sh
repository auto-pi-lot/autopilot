#!/bin/bash

# colors
RED='\033[0;31m'
NC='\033[0m'

echo -e "${RED}Installing dependencies\n${NC}"
if [[ "$OSTYPE" == "linux-gnu" ]]; then
  echo -e "${RED}Installing XLib...\n${NC}"
  sudo apt-get update
  sudo apt-get install -y libxext-dev python-opencv
fi



echo -e "${RED}Qt4 and PySide will be Compiled and installed...\n${NC}"



echo -e "${RED}Downloading & Compiling Qt4\n${NC}"

wget https://download.qt.io/archive/qt/4.8/4.8.7/qt-everywhere-opensource-src-4.8.7.zip

unzip -a ./qt-everywhere-opensource-src-4.8.7.zip

cd qt-everywhere-opensource-src-4.8.7

# make and install Qt4
./configure -debug -opensource -optimized-qmake -separate-debug-info -no-webkit -opengl
make -j10
sudo -H make install

echo -e "${RED}Downloading & Compiling PySide\n${NC}"

git clone https://github.com/PySide/pyside-setup.git pyside-setup
cd pyside-setup
python setup.py bdist_wheel --standalone --qmake=$(which qmake)
sudo -H pip install dist/$(ls PySide*.whl)

# install blosc
sudo -H pip install blosc

# TODO: Add option to delete download filed






