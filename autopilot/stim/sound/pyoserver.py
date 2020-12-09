from autopilot import prefs

try:
    import pyo
    PYO = True
except ImportError:
    PYO = False

def pyo_server(debug=False):
    """
    Returns a booted and started pyo audio server

    Warning:
        Use of pyo is generally discouraged due to dropout issues and
        the general opacity of the module.

    Args:
        debug (bool): If true, setVerbosity of pyo server to 8.
    """
    # Jackd should already be running from the launch script created by setup_pilot, we we just
    pyo_server = pyo.Server(audio='jack', nchnls=int(prefs.get('NCHANNELS')),
                            duplex=0, buffersize=4096, sr=192000, ichnls=0)

    # Deactivate MIDI because we don't use it and it's expensive
    pyo_server.deactivateMidi()

    # We have to set pyo to not automatically try to connect to inputs when there aren't any
    pyo_server.setJackAuto(False, True)

    # debug
    if debug:
        pyo_server.setVerbosity(8)

    # Then boot and start
    pyo_server.boot()
    pyo_server.start()

    return pyo_server

