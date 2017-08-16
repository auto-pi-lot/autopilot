# Classes that house hardware logic

import RPi.GPIO as GPIO

class Beambreak:
    # IR Beambreak sensor

    # Trigger map
    TRIGGER_MAP = {
        'U': GPIO.RISING,
        'D': GPIO.FALLING,
        'B': GPIO.BOTH
    }

    def __init__(self, pin, bounce=200, pull_ud='U', trigger_ud='D', event=None):

        # If the board mode hasn't already been set, set it
        if not GPIO.getmode():
            GPIO.setmode(GPIO.BOARD)

        try:
            pin = int(pin)
        except:
            Exception("Need pin as an integer")
            return

        self.pin = pin
        self.bounce = bounce # Bouncetime (ms)

        # TODO: Wrap pull_ud and trigger_ud as 'types' so can be set in prefs
        self.pull_ud = None
        if pull_ud == 'U':
            self.pull_ud = GPIO.PUD_UP
        elif pull_ud == 'D':
            self.pull_ud = GPIO.PUD_DOWN

        self.trigger_ud = self.TRIGGER_MAP[trigger_ud]
        if trigger_ud   == 'U':
            self.trigger_ud = GPIO.RISING
        elif trigger_ud == 'D':
            self.trigger_ud = GPIO.FALLING
        elif trigger_ud == 'B':
            self.trigger_ud = GPIO.BOTH

        # We can be passed a threading.Event object if we want to handle stage logic here
        # rather than in the parent as is typical.
        self.event = event

        # Setup as input
        GPIO.setup(self.pin, GPIO.IN, pull_up_down=self.pull_ud)

    def assign_cb(self, callback_fn, add=False, evented=False, manual_trigger=None):
        # If we aren't adding, we clear the existing callback
        if not add:
            GPIO.remove_event_detect(self.pin)

        # We can set the direction of the trigger manually,
        # for example if we want to set 'BOTH' only sometimes
        if not manual_trigger:
            trigger_ud = self.trigger_ud
        else:
            trigger_ud = self.TRIGGER_MAP[manual_trigger]

        # We can handle eventing here if we want (usually this is handled in the parent)
        # This won't work if we weren't init'd with an event.
        if evented:
            GPIO.add_event_detect(self.pin, trigger_ud,
                                  callback=self.event.set,
                                  bouncetime=self.bounce)

        GPIO.add_event_detect(self.pin, trigger_ud,
                              callback=callback_fn,
                              bouncetime=self.bounce)

    def clear_cb(self):
        GPIO.remove_event_detect(self.pin)





# TODO: Subclass nosepoke that knows about waiting for mouse leaving