# this is strictly a placeholder module to
# allow global access to prefs without explicit passing.
#
# DO NOT hardcode prefs here.
#
# A prefs.json file should be generated with an appropriate setup routine
# (see setup dir)
# then you should call prefs.init(prefs.json) if the if __name__=="__main__" block

import json

prefdict = None

def init(fn):
    with open(fn, 'r') as pfile:
        prefs = json.load(pfile)

    try:
        assert(isinstance(prefs, dict))
    except AssertionError:
        print(prefs)
        Exception('prefs must return a dict')

    # assign key values to module globals so can access with prefs.pref1
    for k, v in prefs.items():
        globals()[k] = v

    # also store as a dictionary so other modules can have one if they want it
    globals()['prefdict'] = prefs




