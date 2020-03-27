cmake_minimum_required(VERSION 3.10)
project(autopilot VERSION 0.3)
#find_package(PythonExtensions REQUIRED)

# Global settings
set(GLOBAL_OUTPUT_PATH ${PROJECT_BINARY_DIR}/bin)
set(CMAKE_INSTALL_PREFIX ${PROJECT_BINARY_DIR}/install)

# include download project function from https://github.com/Crascit/DownloadProject/
# include(cmake/DownloadProject.cmake)

option(PIGPIO "Install pigpio (only possible on the raspberry pi)" OFF)
option(JACK "Install jack audio" OFF)

message(STATUS "CMAKE_BUILD_DIR: ${CMAKE_BUILD_DIR}")
message(STATUS "CMAKE_INSTALL_DIR: ${CMAKE_INSTALL_DIR}")
message(STATUS "SETUPTOOLS_INSTALL_DIR: ${SETUPTOOLS_INSTALL_DIR}")
message(STATUS "SKBUILD_DIR: ${SKBUILD_DIR}")


if(PIGPIO)
    add_subdirectory(src/pigpio)
    list(APPEND INSTALL_AUTOPILOT_PACKAGES pigpio)
endif()

if(JACK)
    include(cmake/jack.cmake)

    #download_project(
    #    PROJ jack
    #    GIT_REPOSITORY git://github.com/jackaudio/jack2
    #    CONFIGURE_COMMAND "./waf configure --alsa=yes"
    #    BUILD_COMMAND "./waf build -j6"
    #    INSTALL_COMMAND "./waf install"
    #)
    #
    #add_subdirectory(${jack_SOURCE_DIR} ${jack_BINARY_DIR})
    #list(APPEND INSTALL_AUTOPILOT_PACKAGES jack)
endif()






if(INSTALL_AUTOPILOT_PACKAGES)
    install(TARGETS ${INSTALL_AUTOPILOT_PACKAGES} LIBRARY DESTINATION autopilot/external)
else()
    install(FILES "nofile" LIBRARY DESTINATION autopilot/external OPTIONAL)
endif()

