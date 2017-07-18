#!/usr/bin/env python

'''
Class for routing messages between modules.
'''


__version__ = '0.1.1'
__author__ = 'Santiago Jaramillo <sjara@uoregon.edu>'


import time
from PySide import QtCore 

class Message(object):
    '''
    Base container for a message.

    It contains the timestamp, the message and the sender.
    '''
    def __init__(self,text):
        self.text=text
        self.timestamp=time.localtime()
    def __str__(self):
        '''String representation of the message'''
        timeString = time.strftime('[%H:%M:%S] ',self.timestamp)
        return '%s%s'%(timeString,self.text)


class Messenger(QtCore.QObject):
    '''
    Class for keeping a log of messages.

    Previous implementation may have been better with
    Singleton or Borg pattern to keep track of messages:
    http://code.activestate.com/recipes/66531/
    '''
    timedMessage = QtCore.Signal(str)
    messages = []
    def __init__(self):
        super(Messenger, self).__init__()
        #self.messages = []

    @QtCore.Slot(str)
    def collect(self,text):
        newMessage = Message(text)
        Messenger.messages.append(newMessage)
        self.timedMessage.emit(str(newMessage))

    def stringlist(self):
        return [str(x) for x in Messenger.messages]

    def __str__(self):
        return '\n'.join(self.stringlist())
            

if __name__ == "__main__":

    onemsg = Message('My short message')
    print onemsg
 
    mess1 = Messenger()
    mess1.send('One message')

    mess2 = Messenger()
    mess2.send('Another message')

