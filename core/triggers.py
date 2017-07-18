#!/usr/bin/python2.7

'''
function handlers for triggers, taken out of RPilot for clarity

'''

# TODO make this a function decorator type nested function: return the 'inner' function with the args like reward duration, etc. built in
def reward():

# From RPilot
def handle_triggers(self, trigger):
    """
    When the pins can't speak for themselves...
    :return:
    """
    if 'reward' in trigger.keys():
        # TODO Temporary for laptop testing.
        print('rewarded {}ms'.format(trigger['reward']))
    elif 'punish' in trigger.keys():
        # Play sound if we have one, then lock the 'run' thread until the timer expires.
        if 'sound' in trigger.keys():
            trigger['sound']()
        self.trigger_lock.clear()
        self.timers['punish'] = threading.Timer((trigger['punish'] / 1000), self.trigger_lock.set)
    else:
        # TODO: error checking, etc.
        pass


def wrap_triggers(self, val):
    # TODO: Probably not necessary, just use handle_triggers
    """
    Some triggers can't be passed as as already-made bound methods. We can handle that without breaking the generality of run()
    Further, some of those triggers can be wrapped with information RPilot has, but others need arguments and so can't just be returned as blank function handles
        So, we try to handle them here, and if we can't, return the value and let handle_triggers handle them.
    Map a trigger to a handling function which can then be called independently.
    eg. x = wrap_trigger(trigger={'playsound':'yowza!'} - (everybody's favorite sound)
        y = wrap_trigger(trigger={'playsound':'dy-no-mite!'} - (yuck, who let you in my house?)
    x() and y() can then be used separately as triggers that the task instance is unable to make itself.
    """
    if isinstance(val, dict):
        if 'reward' in val.keys():
            # TODO: temporary for troubleshooting on laptop
            return_function = val
        elif 'punish' in val.keys():
            return_function = val
            pass
        else:
            return_function = None
            # TODO warning and error checking here.
    else:
        return_function = None

    return return_function