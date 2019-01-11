# classes that yield sounds according to some rule
import prefs
import os



class Stim_Manager(object):
    stimuli = {}

    # Metaclass for managing stimuli...
    def __init__(self, stim):
        # for now, only one type of stimulus at a time
        if 'sounds' in stim.keys():
            self.init_sounds(stim['sounds'])



    def init_sounds(self, sounds):
        # sounds should be a dictionary like...
        # {
        # 'L': [{'type':'tone',...},{...}],
        # 'R': [{'type':'tone',...},{...}]
        # }

        # Iterate through sounds and load them to memory
        for k, v in sounds.items():
            # If multiple sounds on one side, v will be a list
            if isinstance(v, list):
                self.stimuli[k] = []
                for sound in v:
                    # We send the dict 'sound' to the function specified by 'type' and 'SOUND_LIST' as kwargs
                    self.stimuli[k].append(sounds.SOUND_LIST[sound['type']](**sound))
            # If not a list, a single sound
            else:
                self.stimuli[k] = [sounds.SOUND_LIST[v['type']](**v)]

    def set_triggers(self, trig_fn):
        # set a callback function for when the stimulus ends
        for k, v in self.stimuli:
            for stim in v:
                stim.set_trigger(trig_fn)


    def make_punishment(self, type, duration):
        # types: timeout, noise
        # If we want a punishment sound...
        # if self.punish_sound:
        #     self.stimuli['punish'] = sounds.Noise(self.punish_dur)
        #     #change_to_green = lambda: self.pins['LEDS']['C'].set_color([0, 255, 0])
        #     #self.stimuli['punish'].set_trigger(change_to_green)
        pass






class Jack_Manager(object):
    def __init__(self, sounds):
        pass
