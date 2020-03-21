cmake_minimum_required(VERSION 3.10)
project(autopilot VERSION 0.3)
#find_package(PythonExtensions REQUIRED)

option(PIGPIO "Install pigpio (only possible on the raspberry pi)" OFF)

if(PIGPIO)
    add_subdirectory(src/pigpio)
    list(APPEND INSTALL_AUTOPILOT_PACKAGES pigpio)
endif()



if(INSTALL_AUTOPILOT_PACKAGES)
    install(TARGETS ${INSTALL_PACKAGES} LIBRARY DESTINATION autopilot/external)
else()
    install(FILES "nofile" LIBRARY DESTINATION autopilot/external OPTIONAL)
endif()

