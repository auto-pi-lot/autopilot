.. _installation:

Installation
************

Warning:
    Jonny for the love of god split this out to a separate file.

Each runtime of Autopilot is called an "Agent,"
each of which performs different roles within a system,
and thus have different requirements.

Each Agent should have its own setup routine, currently in two parts:

- A **presetup** script that prepares the environment, and installs prerequisites -- essentially does all the things to prepare us to invoke Autopilot
- A **setup** routine that creates the prefs.json  file that governs Agent operation, creates any launch scripts and system services as needed.

We will be incorporating these into a unified agent system that makes setting up and switching between agents easier in future version (See :ref:`todo`).

Note:
    These instructions, like everything in Autopilot, is Linux and *nix only. They have only been tested on macOS and Ubuntu Linux.

Setting Up a Pilot
==================

Pilot Presetup
--------------

Note:
    These files are encapsulated in a :any:`rpilot.setup.preinstall_pilot.sh` bash script that should let you skip this whole section.

Rasbian Installation
~~~~~~~~~~~~~~~~~~~~

1. Download `Raspbian Lite <https://www.raspberrypi.org/downloads/raspbian/>`_ and unzip
    * `As a .torrent (faster, better for the soul of the universe) <https://downloads.raspberrypi.org/raspbian_lite_latest.torrent>`_
    * `Via http (slower) <https://downloads.raspberrypi.org/raspbian_lite_latest>`_
2. Use ``dd`` to write the Raspbian disk image to a microSD card. Note that ``dd`` can and will mess up your entire life if given the opportunity, be very careful that you don't run the command until you're sure your ``if=`` and ``of=`` are correct.
    * macOS::

        # get the number of the disk, should be something like /dev/disk2
        diskutil list

        # unmount the disk, using the disk # from before.
        sudo diskutil unmountDisk /dev/disk#

        # use dd to copy (use ctrl+t to check transfer status)
        # note the use of rdisk rather than disk the number should be the same
        sudo dd if=/path/to/raspbian.img of=/dev/rdisk# bs=1m

    * linux (use admin privileges when needed with ``sudo``)::

        # get the number of the disk, should be something like /dev/randomnumbersandletters
        fdisk -l

        # unmount the disk
        umount /dev/<your_disk>

        # use dd to copy (use ctrl+t to check transfer status)
        # note the use of rdisk rather than disk the number should be the same
        dd if=/path/to/raspbian.img of=/dev/<your_disk> bs=1M

3. Boot from the SD card. It should reboot once after it resizes the filesystem. Login with the default credentials:
    * username: ``pi``
    * password: ``raspberry``
4. Do an initial ``update`` and ``upgrade`` to grab any critical security fixes so we don't get sunk before we get started:
    * ``sudo apt-get update ** sudo apt-get upgrade -y``
5. **Optional:** Change the default password. You'll be sorry if you don't -- I got my credit card stolen this way.
    * ``passwd`` and follow the prompts
6. Install necessary system packages::

    sudo apt-get install -y \
        build-essential \
        cmake \
        git \
        python-pip \
        python2.7-dev \
        python3-distutils \
        libsamplerate0-dev \ # audio requirements are from here...
        libsndfile1-dev \    #
        libreadline-dev \    #
        libasound-dev \      #
        i2c-tools \          #
        libportmidi-dev \    #
        liblo-dev \          # to here.
        libhdf5-dev \
        python-numpy \       # install these python packages through apt,
        python-pandas \      # take forever to build them on the raspi
        python-tables \      # this one too
        libzmq-dev \
        libffi-dev \         # Allows us to call C functions from python
        python-cffi

7. And Python packages::

    sudo -H pip install -U \
        pyzmq \        # ZeroMQ wrapper
        npyscreen \    # ncurses wrapper used for setup menus
        JACK-Client \  # client for jack audio
        tornado \      # tornado message server
        inputs         # interactions with USB devices

8. Autopilot depends on `pigpio <http://abyz.me.uk/rpi/pigpio/>`_ for high performance GPIO access and control, so install it already::

    git clone https://github.com/joan2937/pigpio.git
    cd pigpio
    make -j6
    sudo -H make install



Rasbian Performance Improvements
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

All of these are, strictly speaking, optional, but there's not really a good reason not to do them...

8. Change the CPU Governor - Change the CPU Governor - normally the RPi keeps a low clock speed when not under load, raising it when load increases. this can cause audible glitches which are obviously to be avoided.
    * the RPi has a startup script (confusingly, /etc/init.d/raspi-config) that sets the cpu governor to on demand. disable it
        - ``sudo systemctl disable raspi-config``
    * Add a line to ``etc/rc.local``, which runs on boot, that changes the governor to "performance"
        - Either add this above 'exit 0'::

            echo "performance" | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

        - Or run this which does it for you::

            sudo sed -i '/^exit 0/i echo "performance" | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor' /etc/rc.local

9. Disable Bluetooth
    * Add ``dtoverlay=pi3-disable-bt`` to ``/boot/config.txt``, or use this::

        sudo sed -i '$s/$/\ndtoverlay=pi3-disable-bt/' /boot/config.txt

    * Disable other bluetooth services::

        sudo systemctl disable hciuart.service
        sudo systemctl disable bluealsa.service
        sudo systemctl disable bluetooth.service

10.  You can decrease the memory that is allocated to the video card, but keep in mind pigpio allocates its memory from the GPU store. Don't reduce to lower than ~8MB
    * ``sudo raspi-config`` > Advanced > Memory Split

Audio Setup
~~~~~~~~~~~

Autopilot uses `Jack Audio <http://jackaudio.org/>`_ to play sounds.

11. Clone jack::

    git clone git://github.com/jackaudio/jack2 --depth 1

12. Configure, build, install::

    cd jack2
    # use ./waf --help to list compile options
    ./waf configure --alsa=yes --libdir=/usr/lib/arm-linux-gnueabihf/
    ./waf build -j6
    sudo ./waf install
    sudo ldconfig #reconfigure links

13. Give jack some more juice::

    # let jack use more memory than Raspbian wants it to
    sudo sh -c "echo @audio - memlock 256000 >> /etc/security/limits.conf"

    # let jack take a higher priority than Raspbian wants it to
    sudo sh -c "echo @audio - rtprio 75 >> /etc/security/limits.conf"

14. Install the jack python wrapper::

    sudo -H pip install JACK-Client

We also use the the `Hifiberry Amp 2 <https://www.hifiberry.com/shop/boards/hifiberry-amp2/>`_ as our soundcard and amplifier.

15. Add pi user (or whatever username you're using) to i2c group::

    sudo adduser pi i2c

16. Turn onboard audio off and enable hifiberry overlays in ``/boot/config.txt``.

    Comment out::
        # dtparam=audio=on

    Add::
        dtoverlay=hifiberry-dacplus
        dtoverlay=i2s-mmap
        dtparam=i2c1=on
        dtparam=i2c_arm=on

    Or use these commands which do it for you::
        sudo sed -i 's/^dtparam=audio=on/#dtparam=audio=on/g' /boot/config.txt
        sudo sed -i '$s/$/\ndtoverlay=hifiberry-dacplus\ndtoverlay=i2s-mmap\ndtoverlay=i2c-mmap\ndtparam=i2c1=on\ndtparam=i2c_arm=on/' /boot/config.txt

17. Edit ALSA configuration (``/etc/asound.conf``) so hifiberry is default sound card. M

    Make it look like this::

        pcm.!default  {
         type hw card 0
        }
        ctl.!default {
         type hw card 0
        }

    Or use this::

        echo -e 'pcm.!default {\n type hw card 0\n}\nctl.!default {\n type hw card 0\n}' | sudo tee $ALSAFILE

18. Reboot and test with ``aplay -l`` which shoudl look something like this::

    pi@raspberrypi:~ $ aplay -l
    **** List of PLAYBACK Hardware Devices ****
    card 0: sndrpihifiberry [snd_rpi_hifiberry_dacplus], device 0: HiFiBerry DAC+ HiFi pcm512x-hifi-0 []
      Subdevices: 1/1
      Subdevice #0: subdevice #0

Video Setup
~~~~~~~~~~~

If you're using Autopilot to present visual stimuli, it runs in an X11 instance and uses `PsychoPy <https://www.psychopy.org/>`_

19. Psychopy and X11 both have quite a few dependencies::

    # X11 dependencies
    sudo apt-get install -y \
        xserver-xorg \             # graphics server
        xorg-dev \                 # development headers
        xinit \                    # interface for graphics server
        xserver-xorg-video-fbdev \ # frame buffer
        python-opencv \            # opencv python bindings
        mesa-utils

    # Psychopy dependencies
    sudo apt-get install -y
        pyopengl \
        pyglet \
        pillow \
        moviepy \
        configobj \
        psychopy \
        json_tricks \
        arabic-reshaper \
        astunparse \
        esprima \
        freetype-py \
        gevent \
        gitpython \
        msgpack-numpy \
        msgpack-python \
        pyosg \
        pyparallel \
        pyserial \
        python-bidi \
        python-gitlab \
        pyyaml \
        sounddevice \
        soundfile

20. To have reasonable video performance, enable the Raspberry pi's OpenGL driver:
    * ``sudo raspi-config`` > advanced > video options
    * then reboot

22. Psychopy uses a few video backends, but in our experience `glfw <https://www.glfw.org/>`_ is the fastest. We have to `compile it manually <https://www.glfw.org/docs/latest/compile_guide.html`_::

git clone https://github.com/glfw/glfw
cd glfw
cmake .
make -j7
sudo -H make install

23. Install Psychopy. At the time of writing there is a broken dependency in the Raspbian package repositories that makes this a real pain in the ass.::

    pip install psychopy --no-deps

Note:
    Jonny return here tomorrow










Optional Installation Steps
~~~~~~~~~~~~~~~~~~~~~~~~~~~

sudo dpkg-reconfigure locales
sudo dpkg-reconfigure keyboard-configuration

xxx. **Optional:** Setup SSH access






