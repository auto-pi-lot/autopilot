from collections import OrderedDict as odict

class Free_Water:

    PARAMS = odict()
    PARAMS['reward'] = {'tag':'Reward Duration (ms)',
                        'type':'int'}
    PARAMS['repeat_ports'] = {'tag':'Allow Repeated Ports',
                              'type':'check'}

    def __init__(self, reward=50, repeat_ports=False):
        pass