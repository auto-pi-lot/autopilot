cmake_minimum_required(VERSION 3.13)
project(autopilot VERSION 0.3)
find_package(PythonExtensions REQUIRED)

option(PIGPIO "Install pigpio (only possible on the raspberry pi)" OFF)

if(PIGPIO)
    add_subdirectory(autopilot/external/pigpio)
    list(APPEND INSTALL_PACKAGES pigpio)
endif()


#set(tool_dest "bin")

install(TARGETS ${INSTALL_PACKAGES} LIBRARY DESTINATION "bin")

