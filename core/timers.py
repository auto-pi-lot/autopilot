#!/usr/bin/python2.7

'''
function handlers for timers, taken out of RPilot for clarity

'''

# TODO ditto on the function decorator thing from triggers

# From RPilot
def handle_timers(self, timerdict):
    # Handle timers depending on type (key of timerdict)
    if not isinstance(timerdict, dict):
        raise TypeError("Timers need to be returned as a dictionary of form {'type':params}")
    for k, v in timerdict.items():
        if k == 'too_early':
            # TODO don't know how to implement this best, come back later
            pass
        elif k == 'timeout':
            if 'sound' in v.keys():
                self.timers[k] = threading.Timer((v['duration'] / 1000), self.bail_trial, args=(v['sound'],))
                self.timers[k].start()
            else:
                self.timers[k] = threading.Timer((v['duration'] / 1000), self.bail_trial)
        elif k == 'inf':
            # Just don't do anything.
            pass
        elif k == None:
            pass

        else:
            # TODO implement timeout
            raise RuntimeError("Don't know how to handle this type of timer")


