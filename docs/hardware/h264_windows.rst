=====================================
Using OpenH264 on Windows with OpenCV
=====================================

*Collated Notes from `Jonny Saunders <https://github.com/sneakers-the-rat>`_ and `Chris Rodgers <https://github.com/cxrodgers>`_*

*By `Jeremy Delahanty <https://github.com/jmdelahanty>`_*

Using the powerful codec library `FFMPEG <https://ffmpeg.org/>`_ allows you to write compressed video
in real time to disk while gathering video data of your subjects. When used in conjunction with
`OpenCV <https://opencv.org/>`_, you can both write data to disk while also performing real time image
processing operations on your video streams. A commonly used open source implementation of H264 is
`Cisco's distribution <https://github.com/cisco/openh264>`_ which can be installed directly or is usable
by installing ``FFMPEG`` via `Conda <https://docs.conda.io/en/latest/>`.

***********
The Problem
***********

Unfortunately on Windows at least, there appear to be problems associated with the Anaconda distribution
of ``FFMPEG`` that doesn't provide the complete set of ``.dll`` files necessary for ``OpenCV`` to use
the codec. When trying to write files to disk, you will run into a message that states Python cannot use
H264 because it cannot find this particular file:

- ``openh264-Maj#.Min#.Min#-win64.dll``

The number signs will be specific for your installed version of ``OpenH264`` which is dependent upon the
installed version of ``FFMPEG`` used in your project.

**********
A Solution
**********

You can get this file from Cisco's git repository under their `releases <https://github.com/cisco/openh264/releases>`
and by downloaded the particular version that is required for your project. The downloaded file will be the full
binary release of the version.

In some cases, you might not be able to simply click on the link in the repository to download the file. It appears
that the download link simply doesn't initiate the process. To solve this on Linux is a simple call to ``wget``.
Windows has a function that's similar to ``wget`` called `Invoke-WebRequest <https://docs.microsoft.com/en-us/powershell/module/microsoft.powershell.utility/invoke-webrequest?view=powershell-7.2>`_
that's available through Powershell. Downloading the binary you need can thus be done by writing:

- ``Invoke-WebRequest -Uri http://ciscobinary.openh264.org/version#``

This will download the binary to your current directory. Once it's completed downloading, extract the folder
using decompression software and find the file shown above.

Once you have this file, it needs to be placed in a particular location in your conda environment:

- ``\path\to\anaconda\env\bin\openh264-Maj#.Min#.Min#-win64.dll``

Now that the file is in the correct spot, be sure to use the following ``fourcc`` flag in the ``OpenCV`` call:

- ``avc1``

It appears that ``avc1`` and ``H264`` are synonymous for the same codec.

******************************************************
Some Caveats: Should you use OpenCV for writing video?
******************************************************

``OpenCV`` is perfect for applications where you need to do realtime image processing during your experimental
acquisition. However, if all you're doing is gathering video, there are different solutions that are probably
more suitable for your usecase.

``OpenCV`` only allows you to specify the fourcc codec name as a parameter while ``FFMPEG`` allows you specify
a great number of parameters specific to how video is encoded. Check out `the docs <https://ffmpeg.org/ffmpeg-all.html>`_
to see them all.

If you want to use the full capacity of the library, there are several solutions which can be found on the
``Autopilot`` discussions page in `this post <https://github.com/wehr-lab/autopilot/discussions/156>`_. Here's
a basic rundown of the solutions proposed there:

- Use Spinnaker as ``Autopilot`` does by abstracting around genicam properties
- Use a wrapper around `skvideo <http://www.scikit-video.org/stable/io.html>`_
- Write frame buffers gathered as ``numpy`` arrays to an ``FFMPEG`` subprocess
- Use `ffmpeg-python <https://github.com/kkroening/ffmpeg-python>`_
- If you have direct access to the camera through ``FFMPEG``, collect video from it directly

*************************
Should I Use Compression?
*************************

Many people new to encoding video streams might be understandably concerned about data integrity if they were
to encode their video streams with compression. For most applications, storing raw video directly from a camera
is unnecessary. Dataset sizes can rapidly become quite large if written to disk without any compression enabled.
A good practice would be to empirically determine which level of compression begins interfering with the kind
of analyses you want to perform on your data. Enable compression so that you can reduce the footprint of your
datasets on your filesystems (your fellow researchers, IT teams, hardware, and analysis scripts will thank you!)
while still retaining your data's integrity.
