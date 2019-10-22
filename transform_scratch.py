
import cv2
import numpy as np
from Queue import Queue

def coroutine(func):
    def start(*args,**kwargs):
        cr = func(*args,**kwargs)
        cr.next()
        return cr
    return start

class Pipeline(object):
    """
    https://brett.is/writing/about/generator-pipelines-in-python/
    """

    def __init__(self, transforms):
        """

        Args:
            transforms (list, dict): A list of dictionaries, or a single dictionary specifying transforms.
        """

        self._transforms = []
        self._pipeline = None
        self._output = Queue()

        if isinstance(transforms, list):
            for tfm in reversed(transforms):
                self.add_transform(tfm)

        elif isinstance(transforms, dict):
            self.add_transform(transforms)

        else:
            Exception("Transforms need to either be a dict that specifies a transform or a list of them")

    # def list_transforms(self, print_list=False, return_what="names"):
    #     #tfms = [g for g in globals() if issubclass(g, Transform)]
    #
    #
    #     tfm_names = [type(tfm).__name__ for tfm in tfms]
    #     transform_list = '\n'.join(tfm_names)
    #
    #     if print_list:
    #         print(transform_list)
    #
    #     if return_what == "names":
    #         return transform_list
    #     elif return_what == "objects":
    #         return tfms
    #     elif return_what is None:
    #         pass

    @coroutine
    def receive(self):
        while True:
            output = yield
            print(output)
            yield output
            #self._output.put_nowait(output)

    @property
    def output(self):
        return self._output.get()


    def add_transform(self, transform, position=-1):
        """

        Args:
            transform (dict): a dictionary with a 'type':'transform_object_name' and 'params':'{'keyword':'parameters'}

        Returns:

        """

        # find the transform object
        try:
            tfm_obj = globals()[transform['type']]
        except AttributeError:
            AttributeError("Could not find transform named {}, available transforms:\n{}".format(transform['type'], self.list_transforms()))

        tfm = tfm_obj(**transform['params'])


        self._transforms.append(tfm)

        if self._pipeline is None:
            self._pipeline = tfm(self.receive())
        else:
            self._pipeline = tfm(self._pipeline)


    def __call__(self, input):
        #return self._pipeline(*args, **kwargs)
        return self._pipeline.send(input)
        #return self.receive()

class Transform(object):

    def __init__(self):
        pass

    @coroutine
    def __call__(self, target):
        """
        Needs to be overwritten with a generator expression
        Returns:

        """

        if not hasattr(self, 'process'):
            Exception('process() method not overwritten!')
        if not callable(getattr(self, 'process')):
            Exception('process is not callable!')

        while True:
            input = (yield)
            yield target.send(self.process(input))




class Test_Add_More(Transform):
    def __init__(self, start_n=0):
        super(Test_Add_More, self).__init__()
        self.n = start_n


    def process(self, input):

        self.n += 1
        #yield input + self.n
        return input + self.n
    #
    # @coroutine
    # def __call__(self, target):
    #     while True:
    #         input = (yield)
    #         self.n += 1
    #         #yield input + self.n
    #         target.send(input + self.n)

class Test_Multiply_More(Transform):
    def __init__(self, start_n=0):
        super(Test_Multiply_More, self).__init__()
        self.n = start_n


    def process(self, input):
        self.n += 1
        return input * self.n

    # @coroutine
    # def __call__(self, target):
    #     while True:
    #         input = (yield)
    #         self.n += 1
    #         target.send(input * self.n)

#
# @coroutine
# def Test_Add_More(target, start_n=0):
#     while True:
#         start_n += 1
#         incoming = (yield)
#         target.send(start_n + incoming)
#
# @coroutine
# def Test_Multiply_More(target, start_n=0):
#     while True:
#         start_n += 1
#         incoming = (yield)
#         target.send(start_n * incoming)

a = Pipeline([{'type':'Test_Add_More', 'params':{'start_n':0}}, {'type':'Test_Multiply_More', 'params':{'start_n':0}}])
