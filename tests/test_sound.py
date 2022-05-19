"""Tests for generating sound stimuli.

This script runs tests that generate different sound stimuli and verifies
that they are initialized correctly.

Currently these only work if AUDIOSERVER is 'jack'. 'pyo' is not tested.
'docs' doesn't actually generate waveforms.

This doesn't require (or test) a running jackd or even a JackClient.
Instead, these tests short-circuit those dependencies by manually setting
FS and BLOCKSIZE in autopilot.stim.sound.jackclient.

A TODO is to test the JackClient itself.

Currently only the sound Noise is tested.

These tests cover multiple durations and amplitudes of mono and
multi-channel Noise, including some edges cases like very short durations
or zero amplitude.

The rest of this docstring addresses the workaround used to short-circuit
jackd and JackClient.

Here is the sequence of events that leads to FS and BLOCKSIZE.
* If an autopilot.agents.pilot.Pilot is initialized:
**  autopilot.agents.pilot.Pilot.__init__ checks prefs.AUDIOSERVER,
    and calls autopilot.agents.pilot.Pilot.init_audio.
**  autopilot.agents.pilot.Pilot.init_audio calls
    autopilot.external.__init__.start_jackd.
**  autopilot.external.__init__.start_jackd takes the JACKDSTRING pref 
    and replaces the token '-rfs' in it with the FS pref. The jackd
    process is launched and stored in autopilot.external.JACKD_PROCESS.
    That process may fail or not, we continue anyway.
**  Next, autopilot.agents.pilot.Pilot.init_audio instantiates an
    autopilot.stim.sound.jackclient.JackClient()
**  autopilot.stim.sound.jackclient.JackClient.__init__ 
    initalizes a jack.Client
**  autopilot.stim.sound.jackclient.JackClient.fs 
    is set to jack.Client.samplerate. Note that this is either the
    requested sample rate, or some default value from jack (not Autopilot)
    if the client did not actually succeed in booting.
**  autopilot.stim.sound.jackclient.FS (a global variable) is set to 
    autopilot.stim.sound.jackclient.JackClient.fs

* Later, a sound (e.g., Noise) is initialized.
**  autopilot.stim.sound.sounds.Noise.__init__ calls super().__init__,
**  which is autopilot.stim.sound.sounds.Jack_Sound.__init__
**  autopilot.stim.sound.sounds.Jack_Sound.__init__ 
    sets `self.fs` to jackclient.FS
**  autopilot.stim.sound.sounds.Noise.__init__ calls 
    autopilot.stim.sound.sounds.Noise.init_sound
**  autopilot.stim.sound.sounds.Noise.init_sound calls 
    autopilot.stim.sound.sounds.Jack_Sound.get_nsamples
**  autopilot.stim.sound.sounds.Jack_Sound.get_nsamples 
    inspects `self.fs`

To remove the dependence on jackd2 and JackClient, the entire first block 
of code can be circumvented by setting these:
autopilot.stim.sound.jackclient.FS
autopilot.stim.sound.jackclient.BLOCKSIZE
"""

import pytest
import numpy as np
import multiprocessing
import autopilot.prefs
import autopilot.external
import autopilot.stim.sound
from autopilot.stim.sound import jackclient, sounds


## Ensure we get the same random sound every time
np.random.seed(0)


## Specify needed params to circumvent init_audio
sample_rate = 192000
block_size = 1024
jackclient.FS = sample_rate
jackclient.BLOCKSIZE = block_size

# These are only used in Jack_Sound.__del__
# Setting them here to avoid warnings during garbage collection
# Why is there one global PLAY and STOP, rather than sound-specific?
jackclient.PLAY = multiprocessing.Event()
jackclient.STOP = multiprocessing.Event()


## Define tests
@pytest.mark.parametrize(
    "duration_ms,amplitude,check_duration_samples,check_n_chunks_expected",
    (
        (100, 0.1, 19200, 19),
        (100., 0.1, 19200, 19),
        ((block_size/sample_rate)*1000, 0.1, block_size, 1), # exactly one chunk
        (5, 0.1, 960, 1),
        (5., 0.1, 960, 1),
        (1/192000. - 1e-8, 0.1, 1, 1),
        (0, 0.1, 0, 0),
        ###### amplitude = 1
        (100, 1, 19200, 19),
        (100., 1, 19200, 19),
        ((block_size / sample_rate) * 1000, 1, block_size, 1),  # exactly one chunk
        (5, 1, 960, 1),
        (5., 1, 960, 1),
        (1 / 192000. - 1e-8, 1, 1, 1),
        (0, 1, 0, 0),
        ###### amplitude = 10.
        (100, 10., 19200, 19),
        (100., 10., 19200, 19),
        ((block_size / sample_rate) * 1000, 10., block_size, 1),  # exactly one chunk
        (5, 10., 960, 1),
        (5., 10., 960, 1),
        (1 / 192000. - 1e-8, 10., 1, 1),
        (0, 10., 0, 0)
    )
)
def test_init_noise(duration_ms, amplitude, 
    check_duration_samples, check_n_chunks_expected):
    """Initialize and check a mono (single-channel) noise.
    
    A mono `Noise` is initialized with specified duration and amplitude.
    The following things are checked:
    * The attributes should be correctly set
    * The `table` should be the right dtype and the right duration, 
      given the sampling rate
    * The chunks should be correct, given the block size. The last chunk
      should be zero-padded.
    * The waveform should not exceed amplitude anywhere
    * As long as the waveform is sufficiently long, it should exceed
      90% of the amplitude somewhere
    * Concatenating the chunks should generate a result equal to the
      table, albeit zero-padded to a multiple of the block size.
    * Specifying channel as None should give identical results to leaving
      it unspecified.
    
    Arguments
    ---------
    duration_ms : passed as `duration`
    amplitude : passed as `amplitude`
    check_duration_samples : int or None
        If not None, the length of the sounds `table` should be this
    check_n_chunks_expected : int or None
        If not None, the length of the sounds `chunks` should be this
    """
    ## Calculate how long the sound should be
    duration_samples = int(np.ceil(duration_ms / 1000. * sample_rate))
    n_chunks_expected = int(np.ceil(duration_samples / block_size))

    # Compare versus the requested checks
    if check_duration_samples is not None:
        assert check_duration_samples == duration_samples
    if check_n_chunks_expected is not None:
        assert check_n_chunks_expected == n_chunks_expected
    
    # Calculate number of padded zeros expected
    n_padded_zeros = n_chunks_expected * block_size - duration_samples
    assert n_padded_zeros >= 0
    assert n_padded_zeros < block_size

    # Test both when channel is explicitly set as None, and when it
    # is left unspecified
    for specify_channel_as_none in [True, False]:
        ## Init sound
        if specify_channel_as_none:
            noise = autopilot.stim.sound.sounds.Noise(
                duration=duration_ms, amplitude=amplitude, channel=None)
        else:
            noise = sounds.Noise(
                duration=duration_ms, amplitude=amplitude)

        
        ## Test attributes
        assert noise.channel is None
        assert noise.duration == float(duration_ms)
        assert noise.amplitude == float(amplitude)
        assert noise.initialized is True
        
        
        ## Test waveform
        # The table should be float32
        assert noise.table.dtype == np.float32
        
        # The table should be 1-dimensional with length duration_samples
        assert noise.table.shape == (duration_samples,)
        
        # The table should not exceed `amplitude` anywhere
        assert np.all(np.abs(noise.table) < amplitude)
        
        # The table itself should NOT be zero-padded
        # Vanishingly unlikely that any real sample is exactly zero
        assert np.all(noise.table != 0)

        # As long as we have enough samples, almost certainly
        # the max value should be >90% of amplitude.
        if duration_samples > 100:
            assert (np.abs(noise.table).max() > .9 * amplitude)

        # The chunks should each be length block_size
        assert len(noise.chunks) == n_chunks_expected
        assert np.all(np.array(list(map(len, noise.chunks))) == block_size)

        # The last chunk should be padded with zeros
        if n_padded_zeros > 0:
            assert np.all(noise.chunks[-1][-n_padded_zeros:] == 0)

        # Concatenate the chunks
        if duration_samples > 0:
            concatted = np.concatenate(noise.chunks)
        else:
            # Special case because np.concatenate([]) is an error
            concatted = np.array([], dtype=np.float32)
        
        # The concatenated chunks should be equal to the table
        assert len(concatted) == len(noise.table) + n_padded_zeros
        assert np.all(concatted[:len(noise.table)] == noise.table)

@pytest.mark.parametrize(
    "duration_ms,amplitude,channel,check_duration_samples,check_n_chunks_expected",
    (
        ########
        ######## channel = 0
        (100, 0.1, 0, 19200, 19),
        (100., 0.1, 0, 19200, 19),
        ((block_size/sample_rate)*1000, 0.1, 0, block_size, 1), # exactly one chunk
        (5, 0.1, 0, 960, 1),
        (5., 0.1, 0, 960, 1),
        (1/192000. - 1e-8, 0.1, 0, 1, 1),
        (0, 0.1, 0, 0, 0),
        ###### amplitude = 1
        (100, 1, 0, 19200, 19),
        (100., 1, 0, 19200, 19),
        ((block_size / sample_rate) * 1000, 1, 0, block_size, 1),  # exactly one chunk
        (5, 1, 0, 960, 1),
        (5., 1, 0, 960, 1),
        (1 / 192000. - 1e-8, 1, 0, 1, 1),
        (0, 1, 0, 0, 0),
        ###### amplitude = 10.
        (100, 10., 0, 19200, 19),
        (100., 10., 0, 19200, 19),
        ((block_size / sample_rate) * 1000, 10., 0, block_size, 1),  # exactly one chunk
        (5, 10., 0, 960, 1),
        (5., 10., 0, 960, 1),
        (1 / 192000. - 1e-8, 10., 0, 1, 1),
        (0, 10., 0, 0, 0),
        #######
        ####### channel = 1
        (100, 0.1, 1, 19200, 19),
        (100., 0.1, 1, 19200, 19),
        ((block_size/sample_rate)*1000, 0.1, 1, block_size, 1), # exactly one chunk
        (5, 0.1, 1, 960, 1),
        (5., 0.1, 1, 960, 1),
        (1/192000. - 1e-8, 0.1, 1, 1, 1),
        (0, 0.1, 1, 0, 0),
        ###### amplitude = 1
        (100, 1, 1, 19200, 19),
        (100., 1, 1, 19200, 19),
        ((block_size / sample_rate) * 1000, 1, 1, block_size, 1),  # exactly one chunk
        (5, 1, 1, 960, 1),
        (5., 1, 1, 960, 1),
        (1 / 192000. - 1e-8, 1, 1, 1, 1),
        (0, 1, 1, 0, 0),
        ###### amplitude = 10.
        (100, 10., 1, 19200, 19),
        (100., 10., 1, 19200, 19),
        ((block_size / sample_rate) * 1000, 10., 1, block_size, 1),  # exactly one chunk
        (5, 10., 1, 960, 1),
        (5., 10., 1, 960, 1),
        (1 / 192000. - 1e-8, 10., 1, 1, 1),
        (0, 10., 1, 0, 0)
    )
)
def test_init_multichannel_noise(duration_ms, amplitude, channel, 
    check_duration_samples, check_n_chunks_expected):
    """Initialize and check a multi-channel noise.

    A multi-channel `Noise` is initialized with specified duration, amplitude,
    and channel. The following things are checked:
    * The attributes should be correctly set
    * The `table` should be the right dtype and the right duration, 
      given the sampling rate
    * The chunks should be correct, given the block size. The last chunk
      should be zero-padded.
    * The column `channel` should contain non-zero data and all other
      columns should contain zero data.
    * The waveform should not exceed amplitude anywhere
    * As long as the waveform is sufficiently long, it should exceed
      90% of the amplitude somewhere
    * Concatenating the chunks should generate a result equal to the
    
    Arguments
    ---------
    duration_ms : passed to `Noise` as `duration`
    amplitude : passed to `Noise` as `amplitude`
    channel : passed to `Noise` as `channel`
    check_duration_samples : int or None
        If not None, the length of the sounds `table` should be this
    check_n_chunks_expected : int or None
        If not None, the length of the sounds `chunks` should be this
    """
    ## Calculate how long the sound should be
    duration_samples = int(np.ceil(duration_ms / 1000. * sample_rate))
    n_chunks_expected = int(np.ceil(duration_samples / block_size))

    # Compare versus the requested checks
    if check_duration_samples is not None:
        assert check_duration_samples == duration_samples
    if check_n_chunks_expected is not None:
        assert check_n_chunks_expected == n_chunks_expected
    
    # Calculate number of padded zeros expected
    n_padded_zeros = n_chunks_expected * block_size - duration_samples
    assert n_padded_zeros >= 0
    assert n_padded_zeros < block_size

    
    ## Init sound
    noise = sounds.Noise(
        duration=duration_ms, amplitude=amplitude, channel=channel)


    ## Test attributes
    assert noise.channel == channel
    assert noise.duration == float(duration_ms)
    assert noise.amplitude == float(amplitude)
    assert noise.initialized is True
    
    
    ## Tests
    # The table should be float32
    assert noise.table.dtype == np.float32
    
    # The table should be 2-dimensional with length duration_samples
    assert noise.table.shape == (duration_samples, 2)

    # The table should not exceed `amplitude` anywhere
    assert (np.abs(noise.table) < amplitude).all()

    # Check each column of the table
    for n_col in range(noise.table.shape[1]):
        # Only the `channel` column should contain data
        if n_col == channel:
            # The table itself should NOT be zero-padded
            # Vanishingly unlikely that any real sample is exactly zero
            assert (noise.table[:, n_col] != 0).all()
            
            # As long as we have enough samples, almost certainly
            # the max value should be >90% of amplitude.
            if duration_samples > 100:
                assert (np.abs(noise.table[:, n_col]).max() > .9 * amplitude)
        else:
            # Other channels should be all zero
            assert (noise.table[:, n_col] == 0).all()

    # The chunks should each be shape (block_size, 2)
    assert len(noise.chunks) == n_chunks_expected
    for chunk in noise.chunks:
        assert chunk.shape == (block_size, 2)

    # The last chunk should be padded with zeros
    if n_padded_zeros > 0:
        assert np.all(noise.chunks[-1][-n_padded_zeros:, :] == 0)

    # Concatenate the chunks
    if duration_samples > 0:
        concatted = np.concatenate(noise.chunks)
    else:
        # Special case because np.concatenate([]) is an error
        # Make sure shape is (0, 2)
        concatted = np.array([[], []], dtype=np.float32).T
    
    # The concatenated chunks should be equal to the table
    assert concatted.shape == (len(noise.table) + n_padded_zeros, 2)
    assert (concatted[:len(noise.table)] == noise.table).all()

def test_unpadded_gap():
    """
    A gap in a continous sound should not be padded (had its last chunk filled with zeros).
    """

    # make a sound that is 1.5x the duration of a chunk
    nsamples = round(block_size*1.5)
    duration = round((nsamples/sample_rate)*1000)
    gap = sounds.Gap(duration)

    assert len(gap.chunks) == 2
    assert len(gap.chunks[1]) == nsamples % block_size
    assert len(gap.chunks[1]) != block_size
