"""
Here is how the sampling rate comes into play:
* If an autopilot.core.pilot.Pilot is initialized:
**  autopilot.core.pilot.Pilot.__init__ checks prefs.AUDIOSERVER,
    and calls autopilot.core.pilot.Pilot.init_audio.
**  autopilot.core.pilot.Pilot.init_audio calls 
    autopilot.external.__init__.start_jackd.
**  autopilot.external.__init__.start_jackd takes the JACKDSTRING pref 
    and replaces the token '-rfs' in it with the FS pref. The jackd
    process is launched and stored in autopilot.external.JACKD_PROCESS.
    That process may fail or not, we continue anyway.
**  Next, autopilot.core.pilot.Pilot.init_audio instantiates an
    autopilot.stim.sound.jackclient.JackClient()
**  autopilot.stim.sound.jackclient.JackClient.__init__ 
    initalizes a jack.Client
**  autopilot.stim.sound.jackclient.JackClient.fs 
    is set to jack.Client.samplerate
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

import numpy as np
import multiprocessing
import autopilot.prefs
import autopilot.external
import autopilot.stim.sound


## Ensure we get the same random sound every time
np.random.seed(0)


## Specify needed params to circumvent init_audio
sample_rate = 192000
block_size = 1024
autopilot.stim.sound.jackclient.FS = sample_rate
autopilot.stim.sound.jackclient.BLOCKSIZE = block_size

# These are only used in Jack_Sound.__del__
# Setting them here to avoid warnings
# Why is there one global PLAY and STOP, rather than sound-specific?
autopilot.stim.sound.jackclient.PLAY = multiprocessing.Event()
autopilot.stim.sound.jackclient.STOP = multiprocessing.Event()


## Define tests
def test_init_noise(duration_ms, check_duration_samples=None, 
    check_n_chunks_expected=None):
    """Initialize a noise and check its size
    
    duration_ms : passed as `duration`
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
    noise = autopilot.stim.sound.sounds.Noise(duration=duration_ms)

    
    ## Tests
    # The table should be float32
    assert noise.table.dtype == np.float32
    
    # The table should be 1-dimensional with length duration_samples
    assert noise.table.shape == (duration_samples,)
    
    # The table itself should NOT be zero-padded
    # Vanishingly unlikely that any real sample is exactly zero
    assert (noise.table != 0).all()

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
    assert (concatted[:len(noise.table)] == noise.table).all()


## Run the tests
# A typical duration, as int and float
test_init_noise(100, check_duration_samples=19200, check_n_chunks_expected=19)
test_init_noise(100., check_duration_samples=19200, check_n_chunks_expected=19)

# exactly one chunk
test_init_noise(
    5.33332, check_duration_samples=block_size, check_n_chunks_expected=1)

# Less than one chunk
test_init_noise(5, check_duration_samples=960, check_n_chunks_expected=1)
test_init_noise(5., check_duration_samples=960, check_n_chunks_expected=1)

# Length 1
test_init_noise(
    1/192000. - 1e-8, check_duration_samples=1, check_n_chunks_expected=1)

# Length 0
test_init_noise(0., check_duration_samples=0, check_n_chunks_expected=0)