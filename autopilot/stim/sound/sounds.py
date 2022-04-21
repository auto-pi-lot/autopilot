"""This module defines classes to generate different sounds.

These classes are currently implemented:
* Tone : a sinuosoidal pure tone
* Noise : a burst of white noise
* File : read from a file
* Speech
* Gap

The behavior of this module depends on `prefs.get('AUDIOSERVER')`.
* If this is 'jack', or True:
    Then import jack, define Jack_Sound, and all sounds inherit from that.
* If this is 'pyo':
    Then import pyo, define PyoSound, and all sounds inherit from that.
* If this is 'docs':
    Then import both jack and pyo, define both Jack_Sound and PyoSound,
    and all sounds inherit from `object`.
* Otherwise:
    Then do not import jack or pyo, or define either Jack_Sound or PyoSound,
    and all sounds inherit from `object`.

.. todo::

    Implement sound level and filter calibration
"""

# Re: The organization of this module
# We balance a few things:
# 1) using two sound servers with very different approaches to
# delivering sounds, and
# 2) having a similar API so other modules can query sound properties
# while still being agnostic to the sound server.
# 3) not have our classes split into a ton of Pyo_Tone, Jack_Tone
# copies so they have their parameters and behavior drift apart
#
# So, We have base classes, but they can't encapsulate all the
# behavior for making sounds, so use an init_audio() method that
# creates sound conditional on the type of audio server.


import os
import sys
import typing
from time import sleep
from scipy.io import wavfile
from scipy.signal import resample
import numpy as np
import threading
from itertools import cycle
from queue import Empty, Full

from autopilot import prefs
from autopilot.stim.sound.base import get_sound_class, Sound
import autopilot

BASE_CLASS = get_sound_class()


## The rest of the module defines actual sounds, which inherit from BASE_CLASS
class Tone(BASE_CLASS):
    """The Humble Sine Wave"""

    PARAMS = ['frequency','duration','amplitude']
    type = 'Tone'

    def __init__(self, frequency, duration, amplitude=0.01, **kwargs):
        """
        Args:
            frequency (float): frequency of sin in Hz
            duration (float): duration of the sin in ms
            amplitude (float): amplitude of the sound as a proportion of 1.
            **kwargs: extraneous parameters that might come along with instantiating us
        """
        super(Tone, self).__init__(**kwargs)

        self.frequency = float(frequency)
        self.duration = float(duration)
        self.amplitude = float(amplitude)

        self.init_sound()

    def init_sound(self):
        """
        Create a sine wave table using pyo or numpy, depending on the server type.
        """

        if self.server_type == 'pyo':
            sin = pyo.Sine(self.frequency, mul=self.amplitude)
            self.table = self.table_wrap(sin)
        elif self.server_type in ('jack', 'dummy'):
            self.get_nsamples()
            t = np.arange(self.nsamples)
            self.table = (self.amplitude*np.sin(2*np.pi*self.frequency*t/self.fs)).astype(np.float32)
            #self.table = np.column_stack((self.table, self.table))
            if self.server_type == 'jack':
                self.chunk()

        self.initialized = True

class Noise(BASE_CLASS):
    """Generates a white noise burst with specified parameters
    
    The `type` attribute is always "Noise".
    """
    # These are the parameters of the sound, I think this is used to generate
    # sounds automatically for a protocol
    PARAMS = ['duration','amplitude', 'channel']
    
    # The type of the sound
    type='Noise'
    
    def __init__(self, duration, amplitude=0.01, channel=None, **kwargs):
        """Initialize a new white noise burst with specified parameters.
        
        The sound itself is stored as the attribute `self.table`. This can
        be 1-dimensional or 2-dimensional, depending on `channel`. If it is
        2-dimensional, then each channel is a column.
        
        Args:
            duration (float): duration of the noise
            amplitude (float): amplitude of the sound as a proportion of 1.
            channel (int or None): which channel should be used
                If 0, play noise from the first channel
                If 1, play noise from the second channel
                If None, send the same information to all channels ("mono")
            **kwargs: extraneous parameters that might come along with instantiating us
        """
        # This calls the base class, which sets server-specific parameters
        # like samplign rate
        super(Noise, self).__init__(**kwargs)
        
        # Set the parameters specific to Noise
        self.duration = float(duration)
        self.amplitude = float(amplitude)
        try:
            self.channel = int(channel)
        except TypeError:
            self.channel = channel
        
        # Currently only mono or stereo sound is supported
        if self.channel not in [None, 0, 1]:
            raise ValueError(
                "audio channel must be 0, 1, or None, not {}".format(
                self.channel))

        # Initialize the sound itself
        self.init_sound()

    def init_sound(self):
        """Defines `self.table`, the waveform that is played. 
        
        The way this is generated depends on `self.server_type`, because
        parameters like the sampling rate cannot be known otherwise.
        
        The sound is generated and then it is "chunked" (zero-padded and
        divided into chunks). Finally `self.initialized` is set True.
        """
        # Depends on the server_type
        if self.server_type == 'pyo':
            noiser = pyo.Noise(mul=self.amplitude)
            self.table = self.table_wrap(noiser)
        
        elif self.server_type in ('jack', 'dummy'):
            # This calculates the number of samples, using the specified 
            # duration and the sampling rate from the server, and stores it
            # as `self.nsamples`.
            self.get_nsamples()
            
            # Generate the table by sampling from a uniform distribution
            # The shape of the table depends on `self.channel`
            if self.channel is None:
                # The table will be 1-dimensional for mono sound
                self.table = np.random.uniform(-1, 1, self.nsamples)
            else:
                # The table will be 2-dimensional for stereo sound
                # Each channel is a column
                # Only the specified channel contains data and the other is zero
                data = np.random.uniform(-1, 1, self.nsamples)
                self.table = np.zeros((self.nsamples, 2))
                assert self.channel in [0, 1]
                self.table[:, self.channel] = data
            
            # Scale by the amplitude
            self.table = self.table * self.amplitude
            
            # Convert to float32
            self.table = self.table.astype(np.float32)
            
            # Chunk the sound
            if self.server_type == 'jack':
                self.chunk()

        # Flag as initialized
        self.initialized = True

    def iter_continuous(self) -> typing.Generator:
        """
        Continuously yield frames of audio. If this method is not overridden,
        just wraps :attr:`.table` in a :class:`itertools.cycle` object and
        returns from it.

        Returns:
            np.ndarray: A single frame of audio
        """
        # preallocate
        if self.channel is None:
            table = np.empty(self.blocksize, dtype=np.float32)
        else:
            table = np.empty((self.blocksize, 2), dtype=np.float32)

        rng = np.random.default_rng()


        while True:
            if self.channel is None:
                table[:] = rng.uniform(-self.amplitude, self.amplitude, self.blocksize)
            else:
                table[:,self.channel] = rng.uniform(-self.amplitude, self.amplitude, self.blocksize)

            yield table

class File(BASE_CLASS):
    """
    A .wav file.

    TODO:
        Generalize this to other audio types if needed.
    """

    PARAMS = ['path', 'amplitude']
    type='File'

    def __init__(self, path, amplitude=0.01, **kwargs):
        """
        Args:
            path (str): Path to a .wav file relative to the `prefs.get('SOUNDDIR')`
            amplitude (float): amplitude of the sound as a proportion of 1.
            **kwargs: extraneous parameters that might come along with instantiating us
        """
        super(File, self).__init__(**kwargs)

        if os.path.exists(path):
            self.path = path
        elif os.path.exists(os.path.join(prefs.get('SOUNDDIR'), path)):
            self.path = os.path.join(prefs.get('SOUNDDIR'), path)
        else:
            Exception('Could not find {} in current directory or sound directory'.format(path))

        self.amplitude = float(amplitude)

        # because files can be v memory intensive, we only load the sound once we're called to buffer them
        # store our initialization status
        self.initialized = False

        #self.init_sound()

    def init_sound(self):
        """
        Load the wavfile with :mod:`scipy.io.wavfile` ,
        converting int to float as needed.

        Create a sound table, resampling sound if needed.
        """

        fs, audio = wavfile.read(self.path)
        if audio.dtype in ['int16', 'int32']:
            audio = int_to_float(audio)

        # load file to sound table
        if self.server_type == 'pyo':
            self.dtable = pyo.DataTable(size=audio.shape[0], chnls=prefs.get('NCHANNELS'), init=audio.tolist())

            # get server to determine sampling rate modification and duration
            server_fs = self.dtable.getServer().getSamplingRate()
            self.duration = float(self.dtable.getSize()) / float(fs)
            self.table = pyo.TableRead(table=self.dtable, freq=float(fs) / server_fs,
                                       loop=False, mul=self.amplitude)

        elif self.server_type == 'jack':
            # attenuate amplitude
            audio = audio*self.amplitude
            self.duration = float(audio.shape[0]) / fs
            # resample to match our audio server's sampling rate
            if fs != self.fs:
                new_samples = self.duration*self.fs
                audio = resample(audio, new_samples)

            self.table = audio

        self.initialized = True

class Gap(BASE_CLASS):
    """
    A silent sound that does not pad its final chunk -- used for creating precise silent
    gaps in a continuous noise.

    """

    type = "Gap"
    PARAMS = ['duration']

    def __init__(self, duration, **kwargs):
        """
        Args:
            duration (float): duration of gap in ms

        Attributes:
            gap_zero (bool): True if duration is zero, effectively do nothing on play.
        """
        super(Gap, self).__init__(**kwargs)

        self.duration = float(duration)
        self.gap_zero = False

        if self.duration == 0:
            self.gap_zero = True
            self.get_nsamples()
            self.chunks = []
            self.table = np.ndarray((0,),dtype=np.float32)
            self.initialized = True
        else:

            self.init_sound()

    def init_sound(self):
        """
        Create and chunk an array of zeros according to :attr:`.Gap.duration`
        """
        if self.server_type == "pyo":
            raise NotImplementedError("This sound has not been implemented for pyo sound server -- pyo is deprecated, and kept as a skeleton in the case interested programmers want to revive its use")

        # get the number of samples for the sound given our self.duration
        self.get_nsamples()
        self.table = np.zeros((self.nsamples,), dtype=np.float32)

        # chunk without padding -- jackclient will pad with ongoing continuous noise (or silence if none)
        self.chunk(pad=False)

        self.initialized = True

    def chunk(self, pad=False):
        """
        If gap is not duration == 0, call parent ``chunk``.
        Args:
            pad (bool): unused, passed to parent ``chunk``
        """
        if not self.gap_zero:
            super(Gap, self).chunk(pad)
        else:
            self.padded=False


    def buffer(self):
        if not self.gap_zero:
            super(Gap, self).buffer()
        else:
            self.buffered = True

    def play(self):
        if not self.gap_zero:
            super(Gap, self).play()
        else:
            if callable(self.trigger):
                threading.Thread(target=self.wait_trigger).start()


class Gammatone(Noise):
    """
    Gammatone filtered noise, using :class:`.timeseries.Gammatone` --
    see that class for the filter documentation.
    """

    type = "Gammatone"

    PARAMS = Noise.PARAMS.copy()
    PARAMS.insert(0, 'frequency')

    def __init__(self,
                 frequency:float, duration:float, amplitude:float=0.01,
                 channel:typing.Optional[int]=None,
                 filter_kwargs:typing.Optional[dict]=None,
                 **kwargs):
        """
        Args:
            frequency (float): Center frequency of filter, in Hz
            duration (float): Duration of sound, in ms
            amplitude (float): Amplitude scaling of sound (absolute value 0-1, default is .01)
            filter_kwargs (dict): passed on to :class:`.timeseries.Gammatone`
        """

        super(Gammatone, self).__init__(duration, amplitude, channel, **kwargs)

        self.frequency = float(frequency)
        self.kwargs = kwargs
        if 'jack_client' in self.kwargs.keys():
            del self.kwargs['jack_client']
        if filter_kwargs is None:
            filter_kwargs = {}


        self.filter = autopilot.get('transform', 'Gammatone')(
            self.frequency, self.fs, axis=0, **filter_kwargs
        )

        # superclass init calls its init sound, so we just call the gammatone filter part
        self._init_sound()

    def _init_sound(self):
        # just the gammatone specific parts so they can be called separately on init
        self.table = self.filter.process(self.table)
        if self.server_type == 'jack':
            self.chunk()





    # These parameters are strings not numbers... jonny should do this better
STRING_PARAMS = ['path', 'type', 'speaker', 'vowel', 'token', 'consonant']
"""
These parameters should be given string columns rather than float columns.

Bother Jonny to do this better bc it's really bad.
"""


## Helper function
def int_to_float(audio):
    """
    Convert 16 or 32 bit integer audio to 32 bit float.

    Args:
        audio (:class:`numpy.ndarray`): a numpy array of audio

    Returns:
        :class:`numpy.ndarray`: Audio that has been rescaled and converted to a 32 bit float.
    """
    if audio.dtype == 'int16':
        audio = audio.astype(np.float32)
        audio = audio / (float(2 ** 16) / 2)
    elif audio.dtype == 'int32':
        audio = audio.astype(np.float32)
        audio = audio / (float(2 ** 32) / 2)

    return audio
