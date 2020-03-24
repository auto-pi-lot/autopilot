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
    # modified from https://mirkokiefer.com/cmake-by-example-f95eb47d45b1
    # with some witchcraft from https://stackoverflow.com/a/35935971/13113166

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
        CONFIGURE_COMMAND ./waf configure --alsa=yes  --prefix=${CMAKE_INSTALL_PREFIX}
        BUILD_COMMAND ./waf build -j6
        INSTALL_COMMAND ./waf install --destdir=${project_jack_DESTDIR}
        )

    ExternalProject_Get_Property(project_jack install_dir)

    add_library(jack SHARED IMPORTED)

    set_property(TARGET jack PROPERTY IMPORTED_LOCATION ${install_dir}/lib/libjackserver.so.0)


    add_dependencies(jack project_jack)

    include_directories(${install_dir}/lib)

    install(DIRECTORY ${project_jack_DESTDIR}/${CMAKE_INSTALL_PREFIX}/
        DESTINATION "./autopilot/external/jack"
        FILE_PERMISSIONS OWNER_EXECUTE OWNER_WRITE OWNER_READ
     	            GROUP_EXECUTE GROUP_READ))

    #install( DIRECTORY ${CMAKE_BINARY_DIR}/jack/bin ${CMAKE_BINARY_DIR}/jack/include ${CMAKE_BINARY_DIR}/jack/lib
    # 	DESTINATION autopilot/external/jack/bin
    # 	DESTINATION autopilot/external/jack/include
    # 	DESTINATION autopilot/external/jack/lib
    # 	FILE_PERMISSIONS OWNER_EXECUTE OWNER_WRITE OWNER_READ
    # 	            GROUP_EXECUTE GROUP_READ)



    #target_link_libraries(autopilot jack)

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

