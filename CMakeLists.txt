cmake_minimum_required(VERSION 3.10)
project(autopilot VERSION 0.3)
#find_package(PythonExtensions REQUIRED)

option(PIGPIO "Install pigpio (only possible on the raspberry pi)" OFF)
option(JACK "Install jack audio" OFF)


if(PIGPIO)
    add_subdirectory(src/pigpio)
    list(APPEND INSTALL_AUTOPILOT_PACKAGES pigpio)
endif()

if(JACK)
    include(ExternalProject)
    ExternalProject_Add(project_jack
        PREFIX ${CMAKE_CURRENT_BINARY_DIR}/jack
        INSTALL_DIR autopilot/external/jack
        GIT_REPOSITORY git://github.com/jackaudio/jack2
        SOURCE_DIR ${CMAKE_BINARY_DIR}/jack-src
        BINARY_DIR ${CMAKE_BINARY_DIR}/jack-build
        CONFIGURE_COMMAND waf configure --alsa=yes
        BUILD_COMMAND waf build -j6
        INSTALL_COMMAND ./waf install
        )

    ExternalProject_Get_Property(project_jack install_dir)

    add_library(jack STATIC IMPORTED)

    set_property(TARGET jack PROPERTY IMPORTED_LOCATION autopilot/external/jack)

    add_dependencies(jack project_jack)

    target_link_libraries(autopilot jack)

    #list(APPEND INSTALL_AUTOPILOT_PACKAGES jack)

    #add_subdirectory(
    #    "${CMAKE_BINARY_DIR}/jack-src"
    #    "${CMAKE_BINARY_DIR}/jack-build"
    #    )
endif()





if(INSTALL_AUTOPILOT_PACKAGES)
    install(TARGETS ${INSTALL_AUTOPILOT_PACKAGES} LIBRARY DESTINATION autopilot/external)
else()
    install(FILES "nofile" LIBRARY DESTINATION autopilot/external OPTIONAL)
endif()

