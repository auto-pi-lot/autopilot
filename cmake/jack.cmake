# modified from https://mirkokiefer.com/cmake-by-example-f95eb47d45b1
# with some witchcraft from https://stackoverflow.com/a/35935971/13113166

set(JACK_ROOT ${CMAKE_CURRENT_BINARY_DIR}/jack)
set(JACK_DESTDIR ${CMAKE_CURRENT_BINARY_DIR}/jack_install)
#set(project_jack_DESTDIR ${CMAKE_CURRENT_BINARY_DIR}/lib/project_jack_install)
include(ExternalProject)
ExternalProject_Add(jack
    GIT_REPOSITORY git://github.com/jackaudio/jack2
    GIT_SHALLOW 1
    BUILD_IN_SOURCE 1
    SOURCE_DIR ${JACK_ROOT}
    CONFIGURE_COMMAND ./waf configure --alsa=yes --prefix=${CMAKE_INSTALL_PREFIX}
    BUILD_COMMAND ./waf build -j6
    INSTALL_COMMAND ./waf install --destdir=${JACK_DESTDIR}
    )


ExternalProject_Get_Property(project_jack install_dir)

link_directories(${JACK_ROOT}/lib)
link_directories(${install_dir}/lib)

install(DIRECTORY ${JACK_DESTDIR}/${CMAKE_INSTALL_PREFIX}/
    DESTINATION "./autopilot/external/jack"
    FILE_PERMISSIONS OWNER_EXECUTE OWNER_WRITE OWNER_READ
                GROUP_EXECUTE GROUP_READ)
