#!/usr/bin/env python

"""
Classes for graphical paradigm parameters.

Two parameters classes are defined:
- NumericParam: For a numeric entry and its label.
- StringParam: For entry of a string.
- MenuParam: For a menu entry and its label.

TODO:
- Make both label and text expanding horizontally

"""


__version__ = '0.1.1'
__author__ = 'Santiago Jaramillo <sjara@uoregon.edu>'


from PySide import QtCore 
from PySide import QtGui 
import imp
import numpy as np # To be able to save strings with np.string_()
import signal
import sys
import socket
import time
from taskontrol.core import utils
from taskontrol.settings import rigsettings

# XXFIXME: Add validation of numbers
#NUMERIC_REGEXP = 

class Container(dict):
    def __init__(self):
        super(Container, self).__init__()        
        self._groups = {}
        self._paramsToKeepHistory = []
        self.history = {}

    def __setitem__(self, paramName, paramInstance):
        # -- Check if there is already a parameter with that name --
        """
        Args:
            paramName:
            paramInstance:
        """
        if paramName in self:
            print 'There is already a parameter named %s'%paramName
            raise ValueError
        # -- Check if paramInstance is of valid type and has a group --
        try:
            groupName = paramInstance.get_group()
            historyEnabled = paramInstance.history_enabled()
        except AttributeError:
            print 'Container cannot hold items of type %s'%type(paramInstance)
            raise
        # -- Append name of parameter to group list --
        try:
            self._groups[groupName].append(paramName)
        except KeyError:  # If group does not exist yet
            self._groups[groupName] = [paramName]
        # -- Append name of parameter to list of params to keep history --
        if historyEnabled:
            try:
                self._paramsToKeepHistory.append(paramName)
            except KeyError:  # If group does not exist yet
                self._paramsToKeepHistory = [paramName]
             
        # -- Add paramInstance to Container --
        dict.__setitem__(self, paramName, paramInstance)

    def print_items(self):
        for key,item in self.iteritems():
            print '[%s] %s : %s'%(type(item),key,str(item.get_value()))

    def layout_group(self,groupName):
        """Create box and layout with all parameters of a given group

        Args:
            groupName:
        """
        groupBox = QtGui.QGroupBox(groupName)
        self.layoutForm = ParamGroupLayout()
        for paramkey in self._groups[groupName]:
            self.layoutForm.add_row(self[paramkey].labelWidget,self[paramkey].editWidget)

        groupBox.setLayout(self.layoutForm)
        return groupBox

    def update_history(self):
        """Append the value of each parameter (to track) for this trial."""
        for key in self._paramsToKeepHistory:
            try:
                self.history[key].append(self[key].get_value())
            except KeyError: # If the key does not exist yet (e.g. first trial)
                self.history[key] = [self[key].get_value()]

    def set_values(self,valuesdict):
        """Set the value of many parameters at once. valuesDict is a dictionary
        of parameters and their values. for example: {param1:val1, param2:val2}

        Args:
            valuesdict:
        """
        for key,val in valuesdict.iteritems():
            if key in self:
                if isinstance(self[key],MenuParam):
                    self[key].set_string(val)
                else:
                    self[key].set_value(val)
            else:
                print 'Warning! {0} is not a valid parameter.'.format(key)

    def from_file(self,filename,dictname='default'):
        """Set values from a dictionary stored in a file. filename: (string)
        file with parameters (full path) dictname: (string) name of dictionary
        in filename containing parameters

            If none is given, it will attempt to load 'default'

        Args:
            filename:
            dictname:
        """
        if filename is not None:
            paramsmodule = imp.load_source('module.name', filename)
            try:
                self.set_values(getattr(paramsmodule,dictname))
            except AttributeError:
                print "There is no '{0}' in {1}".format(dictname, filename)
                raise

    def append_to_file(self, h5file,currentTrial):
        """Append parameters' history to an HDF5 file. It truncates data to the
        trial before currentTrial

        Args:
            h5file:
            currentTrial:
        """
        dataParent = 'resultsData'      # Parameters from each trial
        itemsParent = 'resultsLabels'   # Items in menu parameters
        sessionParent = 'sessionData'   # Parameters for the whole session
        descriptionAttr = 'Description'
        # XXFIXME: the contents of description should not be the label, but the
        #        description of the parameter (including its units)
        trialDataGroup = h5file.require_group(dataParent)
        menuItemsGroup = h5file.require_group(itemsParent)
        sessionDataGroup = h5file.require_group(sessionParent)
        
        # -- Append date/time and hostname --
        dset = sessionDataGroup.create_dataset('hostname', data=socket.gethostname())
        dateAndTime = time.strftime('%Y-%m-%d %H:%M:%S',time.localtime())
        dset = sessionDataGroup.create_dataset('date', data=dateAndTime)
        
        # -- Append all other parameters --
        for key,item in self.iteritems():
            # -- Store parameters with history --
            if item.history_enabled():
                #h5file.createDataset(trialDataGroup, key, self.history[key], paramLabel)
                if key not in self.history:
                    raise ValueError('No history was recorded for "{0}". '.format(key) +\
                           'Did you use paramgui.Container.update_history() correctly?')
                dset = trialDataGroup.create_dataset(key, data=self.history[key][:currentTrial])
                dset.attrs['Description'] = item.get_label()
                if item.get_type()=='numeric':
                    dset.attrs['Units'] = item.get_units()
                # XXFIXME: not very ObjectOriented to use getType
                #        the object should be able to save itself
                if item.get_type()=='menu':
                    #h5file.createArray(menuItemsGroup, key, item.get_items(),
                    #                   '%s menu items'%paramLabel)
                    #menuItemsGroup.create_dataset(key, data=item.get_items())
                    menuList = item.get_items()
                    menuDict = dict(zip(menuList,range(len(menuList))))
                    utils.append_dict_to_HDF5(menuItemsGroup,key,menuDict)
                    dset.attrs['Description'] = '%s menu items'%item.get_label()
            else: # -- Store parameters without history (Session parameters) --
                if item.get_type()=='string':
                    dset = sessionDataGroup.create_dataset(key, data=np.string_(item.get_value()))
                else:
                    dset = trialDataGroup.create_dataset(key, data=item.get_value())
                dset.attrs['Description'] = item.get_label()

class ParamGroupLayout(QtGui.QGridLayout):
    def __init__(self,parent=None):
        """
        Args:
            parent:
        """
        super(ParamGroupLayout, self).__init__(parent)
        self.setVerticalSpacing(0)
    def add_row(self,labelWidget,editWidget):
        """
        Args:
            labelWidget:
            editWidget:
        """
        currentRow = self.rowCount()
        self.addWidget(labelWidget,currentRow,0,QtCore.Qt.AlignRight)
        self.addWidget(editWidget,currentRow,1,QtCore.Qt.AlignLeft)


class GenericParam(QtGui.QWidget):
    def __init__(self, labelText='', value=0, group=None,
                 history=True, labelWidth=80, parent=None):
        """
        Args:
            labelText:
            value:
            group:
            history:
            labelWidth:
            parent:
        """
        super(GenericParam, self).__init__(parent)
        self._group = group
        self._historyEnabled = history
        self._type = None
        self._value = None
        self.labelWidget = QtGui.QLabel(labelText)
        self.labelWidget.setObjectName('ParamLabel')
        self.editWidget = None

    def get_type(self):
        return self._type

    def get_label(self):
        return str(self.labelWidget.text())

    def get_group(self):
        return self._group

    def in_group(self,groupName):
        """
        Args:
            groupName:
        """
        return self._group==groupName

    def history_enabled(self):
        return self._historyEnabled

    def set_enabled(self,enabledStatus):
        """Enable/disable the widget

        Args:
            enabledStatus:
        """
        self.editWidget.setEnabled(enabledStatus)


class StringParam(GenericParam):
    def __init__(self, labelText='', value='', group=None,
                 labelWidth=80, parent=None):
        """
        Args:
            labelText:
            value:
            group:
            labelWidth:
            parent:
        """
        super(StringParam, self).__init__(labelText, value, group,
                                           history=False, labelWidth=labelWidth,  parent=parent)
        self._type = 'string'
        if self._historyEnabled:
            raise ValueError('Keeping a history for string parameters is not supported.\n'
                             +'When creating the instance use: history=False')

        # -- Define graphical interface --
        self.editWidget = QtGui.QLineEdit()
        self.editWidget.setObjectName('ParamEdit')

        # -- Define value --
        self.set_value(value)

    def set_value(self,value):
        """
        Args:
            value:
        """
        self._value = value
        self.editWidget.setText(str(value))

    def get_value(self):
        return str(self.editWidget.text())


class NumericParam(GenericParam):
    def __init__(self, labelText='', value=0, units='', group=None, decimals=None,
                 history=True, labelWidth=80, enabled=True, parent=None):
        """
        Args:
            labelText:
            value:
            units:
            group:
            decimals:
            history:
            labelWidth:
            enabled:
            parent:
        """
        super(NumericParam, self).__init__(labelText, value, group,
                                           history, labelWidth,  parent)
        self._type = 'numeric'
        self.decimals=decimals

        # -- Define graphical interface --
        self.editWidget = QtGui.QLineEdit()
        #self.editWidget.setToolTip('[{0}]'.format(units))
        self.editWidget.setToolTip('{0}'.format(units))
        self.editWidget.setObjectName('ParamEdit')
        self.set_enabled(enabled)

        # -- Define value --
        self.set_value(value)
        self._units = units

    def set_value(self,value):
        """
        Args:
            value:
        """
        self._value = value
        if self.decimals is not None:
            strFormat = '{{0:0.{0}f}}'.format(self.decimals)
            self.editWidget.setText(strFormat.format(value))
        else:
            self.editWidget.setText(str(value))

    def get_value(self):
        try:
            return int(self.editWidget.text())
        except ValueError:
            return float(self.editWidget.text())

    def get_units(self):
        return self._units

    def add(self,value):
        """
        Args:
            value:
        """
        self.set_value(self.get_value()+value)


class MenuParam(GenericParam):
    def __init__(self, labelText='', menuItems=(), value=0, group=None,
                 history=True, labelWidth=80, parent=None):
        """
        Args:
            labelText:
            menuItems:
            value:
            group:
            history:
            labelWidth:
            parent:
        """
        super(MenuParam, self).__init__(labelText, value, group,
                                        history, labelWidth, parent)
        self._type = 'menu'

        # -- Check if spaces in items --
        if ' ' in ''.join(menuItems):
            raise ValueError('MenuParam items cannot contain spaces')

        # -- Define graphical interface --
        self.editWidget = QtGui.QComboBox()
        self.editWidget.addItems(menuItems)
        self.editWidget.setObjectName('ParamMenu')

        # -- Define value --
        self._items = menuItems
        self.set_value(value)

    def set_value(self,value):
        """
        Args:
            value:
        """
        self._value = value
        self.editWidget.setCurrentIndex(value)

    def set_string(self,newstring):
        """
        Args:
            newstring:
        """
        # XXFIXME: graceful warning if wrong string (ValueError exception)
        try:
            value = self._items.index(newstring)
        except ValueError:
            print "'{0}' is not a valid menu item".format(newstring)
            raise
        self._value = value
        self.editWidget.setCurrentIndex(value)

    def get_value(self):
        return self.editWidget.currentIndex()

    def get_string(self):
        return str(self.editWidget.currentText())

    def get_items(self):
        return self._items

    #def appendToFile(self,h5file,dataParent,itemsParent):
    #    h5file.createArray(dataParent, key, paramContainer.history[key], paramLabel)
    #    h5file.createArray(menuItemsGroup, key, paramContainer[key].get_items(),
    #                               '%s menu items'%paramLabel)


# -----------------------------------------------------------------------------
def create_app(paradigmClass):
    """The paradigm file needs to run something like: (app,paradigm) =
    tasks.create_app(Paradigm)

    Args:
        paradigmClass:
    """
    signal.signal(signal.SIGINT, signal.SIG_DFL) # Enable Ctrl-C
    app=QtGui.QApplication.instance() # checks if QApplication already exists 
    if not app: # create QApplication if it doesnt exist 
        app = QtGui.QApplication(sys.argv)

    if len(sys.argv)==1:
        paramfile = None
        paramdictname = None
    elif len(sys.argv)==2:
        paramfile = rigsettings.DEFAULT_PARAMSFILE
        paramdictname = sys.argv[1]
    elif len(sys.argv)==3:
        paramfile = sys.argv[1]
        paramdictname = sys.argv[2]
    else:
        raise ValueError('Number of arguments must less than 3')

    #print '------------------------------------'
    #print paramfile,paramdictname

    if len(sys.argv)>1:
        paradigm = paradigmClass(paramfile=paramfile,paramdictname=paramdictname)
    else:
        paradigm = paradigmClass()
        
    paradigm.show()

    app.exec_()
    return (app,paradigm)


def create_app_only():
    """NOT FINISHED When using this version, the paradigm file needs to run the
    following:

        app = tasks.create_app_only() paradigm = Paradigm() paradigm.show()
        app.exec_()
    """
    signal.signal(signal.SIGINT, signal.SIG_DFL) # Enable Ctrl-C
    app=QtGui.QApplication.instance() # checks if QApplication already exists 
    if not app: # create QApplication if it doesnt exist 
        app = QtGui.QApplication(sys.argv)
    return app


def center_in_screen(widget):
    """
    Args:
        widget:
    """
    qr = widget.frameGeometry()
    cp = QtGui.QDesktopWidget().availableGeometry().center()
    qr.moveCenter(cp)
    widget.move(qr.topLeft())

'''
# XFIXME: I don't know yet how to connect signals to this function
def show_message(window,msg):
    window.statusBar().showMessage(str(msg))
    print msg
'''

if __name__ == "__main__":
    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    import sys
    try:
      app = QtGui.QApplication(sys.argv)
    except RuntimeError:
      app = QtCore.QCoreApplication.instance()
    form = QtGui.QDialog()
    params = Container()
    params['value1'] = NumericParam('OneParam',value=2,group='First group')
    params['value2'] = NumericParam('AnotherParam',value=3,group='First group')
    params['value3'] = NumericParam('ParamThree',value=2,group='Second group')
    params['value4'] = NumericParam('ParamFour',value=3,group='Second group')
    params['outcomeMode'] = MenuParam('Outcome mode',
                                               ['sides direct','direct','on next correct',
                                                'only if correct'],
                                               value=3,group='Second group')
    params['nohist'] = NumericParam('somevalue',value=5.4,group='First group',history=False)
    params['experimenter'] = StringParam('Experimenter',value='santiago',group='First group')
    firstGroup = params.layout_group('First group')
    secondGroup = params.layout_group('Second group')
    layoutMain = QtGui.QHBoxLayout()
    layoutMain.addWidget(firstGroup)
    layoutMain.addWidget(secondGroup)
    #params.set_values({'value1':99, 'value2':88})
    params.from_file('../examples/params_example.py','test002')
    form.setLayout(layoutMain)

    SAVE_DATA=1
    if SAVE_DATA:
        import h5py
        try:
            params.update_history()
            h5file = h5py.File('/tmp/testparamsave.h5','w')
            params.append_to_file(h5file,currentTrial=1)
        except:
            h5file.close()
            raise
        h5file.close()
            
    form.show()
    app.exec_()


    # To get the item (as string) of a menuparam for the last trial in the history:
    #protocol.params['chooseNumber'].get_items()[protocol.params.history['chooseNumber'][-1]]
