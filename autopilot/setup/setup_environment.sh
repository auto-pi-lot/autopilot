#!/bin/bash

# colors
RED='\033[0;31m'
NC='\033[0m'

echo -e "${RED}-----------------------------------------\n
welcome to autopilot, checking dependencies.\n
if some system dependencies are not found, you\n
will be asked for root permission to install\n
them with apt\n
------------------------------------------------\n${NC}"




DO_APT_UPDATE=false
APT_INSTALL_PACKAGES=""


# check for cmake and install if not
if hash cmake 2>/dev/null; then
  echo -e "${RED}cmake found, not installing${NC}"
else
  echo -e "${RED}cmake NOT found, attempting to install${NC}"
  DO_APT_UPDATE=true
  APT_INSTALL_PACKAGES="cmake"
fi

# build-essential
BUILD_ESSENTIAL_OK=$(dpkg-query -W --showformat='${Status}\n' build-essential|grep "install ok installed")
if [ "" == "$BUILD_ESSENTIAL_OK" ]; then
  echo -e "${RED}build-essential NOT found, attempting to install${NC}"
  DO_APT_UPDATE=true
  APT_INSTALL_PACKAGES="$APT_INSTALL_PACKAGES cmake"
else
  echo -e "${RED}build-essential found, not installing${NC}"
fi


if [ $DO_APT_UPDATE == "true" ]; then
  echo -e "${RED}Missing dependencies found, attempting to install\n    ${APT_INSTALL_PACKAGES} ${NC}"
  sudo apt update
  sudo apt install -y "$APT_INSTALL_PACKAGES"
fi




