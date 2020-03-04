#!/bin/bash

# colors
RED='\033[0;31m'
NC='\033[0m'

GITDIR=$(git rev-parse --show-toplevel)
if [[ ! -d $GITDIR ]]; then
  read -p "Can't detect git directory (probably being run from outside the repo), where is the autopilot repository?: " GITDIR
fi




echo -e "${RED}Installing system dependencies\n${NC}"
if [[ "$OSTYPE" == "linux-gnu" ]]; then
  echo -e "${RED}Installing XLib g++ and opencv...\n${NC}"
  sudo apt-get update
  sudo apt-get install -y libxext-dev python-opencv g++
fi

echo -e "${RED}Installing Python dependencies\n${NC}"
sudo -H pip3 install -r "${GITDIR}/requirements_terminal.txt"

echo -e "${RED}Installing Development version of pyqtgraph\n${NC}"
pip3 install git+https://github.com/pyqtgraph/pyqtgraph@develop




