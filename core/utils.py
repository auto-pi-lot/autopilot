'''
Extra functions useful at different stages of the paradigm design.
'''

__version__ = '0.1'
__author__ = 'Santiago Jaramillo <sjara@uoregon.edu>'


import numpy as np

def find_state_sequence(states,stateSequence):
    '''
    Return an array with the indexes where state transitions are the same as stateSequence
    states is a 1D array of state IDs in the order they occurred.
    stateSequence is a 1D array containing some sequence of states.
    '''
    sequenceStartInd = []
    for ind in xrange(len(states)-len(stateSequence)+1):
        val = np.all(states[ind:ind+len(stateSequence)]==stateSequence)
        sequenceStartInd.append(val)
    return np.array(sequenceStartInd)

def find_transition(states,prevStateID,nextStateID):
    '''
    Return an array with the indexes of transitions from origEvent to destEvent
    (that is, the index of destEvent that is preceded by origEvent)
    states is a 1D array of state IDs in the order they occurred.
    prevStateID and nextStateID must be integers.

    For a similar method see: extracellpy/loadbehavior.time_of_state_transition
    '''
    prevStateInds = (np.r_[0,states[:-1]]==prevStateID)
    nextStateInds = (states==nextStateID)
    transitionInds = np.flatnonzero(prevStateInds & nextStateInds)
    return transitionInds

def find_event(events,states,eventID,currentStateID):
    '''
    Return an array with the indexes in which eventID occurred while in currentStateID
    events is a 1D array of event IDs in the order they occurred.
    states is a 1D array of state IDs in the order they occurred.
    eventID and currentStateID must be integers.

    For a similar method see: extracellpy/loadbehavior.time_of_state_transition
    '''
    eventInds = (events==eventID)
    currentStateInds = (np.r_[0,states[:-1]]==currentStateID)
    eventInds = np.flatnonzero(eventInds & currentStateInds)
    return eventInds
    

def append_dict_to_HDF5(h5fileGroup,dictName,dictData,compression=None):
    '''Append a python dictionary to a location/group in an HDF5 file
    that is already open.

    It creates one scalar dataset for each key in the dictionary,
    and it only works for scalar values.
    
    NOTE: An alternative would be use the special dtype 'enum'
    http://www.h5py.org/docs/topics/special.html
    '''
    dictGroup = h5fileGroup.create_group(dictName)
    for key,val in dictData.iteritems():
        ### if isinstance(val,np.array): dtype = val.dtype
        ### else: dtype = type(val)
        dtype = type(val)
        dset = dictGroup.create_dataset(key, data=val, dtype=dtype,
                                          compression=compression)


def dict_from_HDF5(dictGroup):
    newDict={}
    for k,v in dictGroup.iteritems():
        newDict[k]=v[()]
        newDict[v[()]]=k
    return newDict


if __name__=='__main__':
    states = np.arange(0,20,2)
    stateSequence = [4,6,8]
    print find_state_sequence(states,stateSequence)
