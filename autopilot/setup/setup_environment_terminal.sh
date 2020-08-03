#!/bin/bash

# colors
RED='\033[0;31m'
NC='\033[0m'


echo -e "${RED}Installing system dependencies\n${NC}"
if [[ "$OSTYPE" == "linux-gnu" ]]; then
  echo -e "${RED}Installing XLib g++ and opencv...\n${NC}"
  sudo apt-get update
  sudo apt-get install -y libxext-dev python3-opencv g++
fi