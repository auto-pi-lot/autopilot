#!/usr/bin/env python

'''
Container for non-graphical variables (like choice, outcome, etc)

'''

__version__ = '0.1'
__author__ = 'Santiago Jaramillo <sjara@uoregon.edu>'


from taskontrol.core import utils


class Container(dict):
    def __init__(self):
        super(Container, self).__init__()        
        self.labels = dict()
        ###self.currentTrial = 0
    def append_to_file(self, h5file,currentTrial):
        '''Returns True if successful '''
        if currentTrial<1:
            raise UserWarning('WARNING: No trials have been completed or currentTrial not updated.')
        resultsDataGroup = h5file.require_group('resultsData')
        resultsLabelsGroup = h5file.require_group('resultsLabels')
        for key,item in self.iteritems():
            dset = resultsDataGroup.create_dataset(key, data=item[:currentTrial])
        for key,item in self.labels.iteritems():
            # XXFIXME: Make sure items of self.labels are dictionaries
            utils.append_dict_to_HDF5(resultsLabelsGroup,key,item)

if __name__ == "__main__":
    import h5py
    import numpy as np
    c = Container()
    c['myvar1'] = np.arange(10)
    c.labels['myvar2labels'] = {'yes':1,'no':0}
    c['myvar2'] = np.array([0,1,1,1,0])
    h5file = h5py.File('/tmp/testh5.h5','w')
    h5file.create_group('resultsData')
    c.append_to_file(h5file,4)
    h5file.close()
