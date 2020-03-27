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
    #include(cmake/jack.cmake)
    

    set(project_jack_SOURCE_DIR ${CMAKE_CURRENT_BINARY_DIR}/lib/project_jack)
    set(project_jack_DESTDIR ${CMAKE_CURRENT_BINARY_DIR}/lib/project_jack_install)
    include(ExternalProject)
    ExternalProject_Add(project_jack
        # PREFIX ${CMAKE_BINARY_DIR}/jack
        # INSTALL_DIR autopilot/external/jack
        GIT_REPOSITORY git://github.com/jackaudio/jack2
        GIT_SHALLOW 1
        #SOURCE_DIR ${CMAKE_BINARY_DIR}/jack-src
        SOURCE_DIR ${project_jack_SOURCE_DIR}
        BUILD_IN_SOURCE 1
        CONFIGURE_COMMAND ./waf configure --alsa=yes --prefix=${CMAKE_INSTALL_PREFIX}
        BUILD_COMMAND ./waf build -j6
        INSTALL_COMMAND ./waf install --destdir=${project_jack_DESTDIR}
        )

    ExternalProject_Get_Property(project_jack install_dir)

    add_library(jack SHARED IMPORTED)

    #set_property(TARGET jack PROPERTY IMPORTED_LOCATION ${install_dir}/lib/libjackserver.so.0)


    add_dependencies(jack project_jack)

    include_directories(${install_dir}/lib)

    install(DIRECTORY ${project_jack_DESTDIR}/${CMAKE_INSTALL_PREFIX}/
        DESTINATION "autopilot/external/jack"
        FILE_PERMISSIONS OWNER_EXECUTE OWNER_WRITE OWNER_READ
                    GROUP_EXECUTE GROUP_READ)

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

