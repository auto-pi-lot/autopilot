"""
Data transformations.

Experimental module.

Reusable transformations from one representation of data to another.
eg. converting frames of a video to locations of objects,
or locations of objects to area labels

.. todo::

    This is a preliminary module and it purely synchronous at the moment. It will be expanded to ...
    * support multiple asynchronous processing rhythms
    * support automatic value coercion

    The following design features need to be added
    * recursion checks -- make sure a child hasn't already been added to a processing chain.
"""
import os
from datetime import datetime
import sys
import types
import typing
import pdb
# import cv2
import numpy as np
from enum import Enum, auto

from autopilot import prefs

class TransformRhythm(Enum):
    """
    Attributes:
        FIFO: First-in-first-out, process inputs as they are received, potentially slowing down the transformation pipeline
        FILO: First-in-last-out, process the most recent input, ignoring previous (lossy transformation)
    """
    FIFO = auto()
    FILO = auto()





class Transform(object):
    """
    Metaclass for data transformations

    Each subclass should define the following

    * :meth:`.process` - a method that takes the input of the transoformation as its single argument and returns the transformed output
    * :attr:`.format_in` - a `dict` that specifies the input format
    * :attr:`.format_out` - a `dict` that specifies the output format

    Arguments:
        rhythm (:class:`TransformRhythm`): A rhythm by which the transformation object processes its inputs

    Attributes:
        child (class:`Transform`): Another Transform object chained after this one
    """

    def __init__(self, rhythm : TransformRhythm = TransformRhythm.FILO, *args, **kwargs):
        self._child = None
        self._check = None
        self._rhythm = None
        self._process = None
        self._format_in = None
        self._parent = None
        self._coerce = None


        self.rhythm = rhythm

        # self._wrap_process()

    @property
    def rhythm(self) -> TransformRhythm:
        return self._rhythm

    @rhythm.setter
    def rhythm(self, rhythm: TransformRhythm):
        if rhythm not in TransformRhythm:
            raise ValueError(f'rhythm must be one of TransformRhythm, got {rhythm}')
        self._rhythm = rhythm

    @property
    def format_in(self) -> dict:
        raise NotImplementedError('Every subclass of Transform must define format_in!')

    @format_in.setter
    def format_in(self, format_in: dict):
        raise NotImplementedError('Every subclass of Transform must define format_in!')

    @property
    def format_out(self) -> dict:
        raise NotImplementedError('Every subclass of Transform must define format_out!')

    @format_out.setter
    def format_out(self, format_out: dict):
        raise NotImplementedError('Every subclass of Transform must define format_out!')

    @property
    def parent(self) -> typing.Union['Transform', None]:
        """
        If this Transform is in a chain of transforms, the transform that precedes it

        Returns:
            :class:`.Transform`, ``None`` if no parent.
        """
        return self._parent

    @parent.setter
    def parent(self, parent):
        if not issubclass(type(parent), Transform):
            raise TypeError('parents must be subclasses of Transform')
        self._parent = parent


    def process(self, input):
        raise NotImplementedError('Every subclass of Transform must define its own process method!')

    def reset(self):
        """
        If a transformation is stateful, reset state.
        """
        raise Warning('reset method not explicitly overridden in transformation, doing nothing!')

    def check_compatible(self, child: 'Transform'):
        """
        Check that this Transformation's :attr:`.format_out` is compatible with another's :attr:`.format_in`

        .. todo::

            Check for types that can be automatically coerced into one another and set :attr:`_coercion` to appropriate function

        Args:
            child (:class:`Transform`): Transformation to check compatibility

        Returns:
            bool
        """

        ret = False

        if self.format_out['type'] == child.format_in['type']:
            ret = True
        elif child.format_in['type'] == 'any':
            ret = True

        # if child has a specific requirement of parent transform class, ensure
        parent_req = child.format_in.get('parent', False)
        if parent_req:
            if not isinstance(self, parent_req):
                ret = False

        return ret

        # if self.format_out['type'] in (int, np.int, )

    def __add__(self, other):
        """
        Add another Transformation in the chain to make a processing pipeline

        Args:
            other (:class:`Transformation`): The transformation to be chained
        """
        if not issubclass(type(other), Transform):
            raise RuntimeError('Can only add subclasses of Transform to other Transforms!')

        if self._child is None:
            # if we haven't been chained at all yet, claim the child
            # first check if it aligns

            if not self.check_compatible(other):
                raise ValueError(f'Incompatible transformation formats: \nOutput: {self.format_out},\nInput: {other.format_in}')


            self._child = other
            self._child.parent = self

            # override our process method with one that calls recursively
            # back it up first
            self._process = self.process

            def new_process(self, input):
                return self._child.process(self._process(input))

            self.process = types.MethodType(new_process, self)

        else:
            # we already have a child,
            # add it to our child instead (potentially recursively)
            self._child = self._child + other

        return self


class T_Image(Transform):
    """
    Metaclass for transformations of images
    """

    def __init__(self, shape=None, *args, **kwargs):
        super(T_Image, self).__init__(*args, **kwargs)
        self._shape = shape # type: typing.Tuple[int, int]

    @property
    def format_in(self) -> dict:
        return {
            'type': np.ndarray,
            'shape': self.shape
        }


    @format_in.setter
    def format_in(self, format_in: dict):
        if 'shape' in format_in.keys():
            self.shape = format_in['shape']

    @property
    def format_out(self) -> dict:
        raise NotImplementedError('Every subclass of Transform must define format_out!')

    @format_out.setter
    def format_out(self, format_out: dict):
        raise NotImplementedError('Every subclass of Transform must define format_out!')

    @property
    def shape(self) -> typing.Tuple[int, int]:
        return self._shape

    @shape.setter
    def shape(self, shape):
        if not isinstance(shape, tuple) and not len(shape) == 2:
            raise ValueError('shape must be a tuple of two integers')

        self._shape = (round(shape[0]), round(shape[1]))


class T_DLC(T_Image):
    """
    Do pose estimation with ``DeepLabCut-Live``

    All args and kwargs are passed on to :class:`dlclive.DLCLive`,
    see its documentation for details: https://github.com/DeepLabCut/DeepLabCut-live

    Attributes:
        model (str): name of model
        model_dir (str): directory of model
        model_type (str): 'local' - a local directory, or 'zoo' a DLC modelzoo model.
    """

    def __init__(self, model_dir: str = None, model_zoo: str = None, *args, **kwargs):
        """
        Must give either ``model_dir`` or ``model_zoo``

        Args:
            model_dir (str): Path of model directory, either an absolute path or a path relative to ``prefs.DLC_DIR``
            model_zoo (str): Name of DLC model zoo model to use
            *args: passed to DLCLive and superclass
            **kwargs: passed to DLCLive and superclass
        """
        super(T_DLC, self).__init__(*args, **kwargs)

        self._model = None
        self._model_dir = None
        self._deeplabcut = None
        self.model_type = None
        self.initialized = False

        if not model_dir and not model_zoo:
            raise ValueError('Either model_dir or model_zoo must be given!')
        elif model_dir and model_zoo:
            raise ValueError('Only model_dir OR model_zoo can be given!!')

        try:
            from dlclive import DLCLive
        except ImportError as e:
            print('dlclive not found! dlclive must be installed before using this transform')
            raise e

        self.import_dlc()
        self.deeplabcut = sys.modules['deeplabcut']

        if model_dir:
            # figure out what model to use!
            self.model_type = 'local'
            self.model = model_dir
            self.model_dir = model_dir

        elif model_zoo:
            # check if valid
            self.model_type = "zoo"
            self.model = model_zoo
            # self.model_dir = os.path.join(self.dlc_dir, model_zoo)

        #makes sure model is exported, doesn't do anything if already exported

        self.export_model()

        self.live = DLCLive(self.dlc_paths['export_dir'], *args, **kwargs)


    def process(self, input: np.ndarray) -> np.ndarray:
        if not self.live.is_initialized:
            output = self.live.init_inference(input)
        else:
            output = self.live.get_pose(input)

        return output




    @property
    def model(self) -> str:
        return self._model

    @model.setter
    def model(self, model: str):
        if self.model_type == 'zoo':
            if model not in self.list_modelzoo():
                raise ValueError(f'model "{model}" not found in available models: {self.list_modelzoo()}')

            # check if we already have the model downloaded
            models = os.listdir(self.dlc_dir)
            models = [m for m in models if m.startswith(model)]
            if len(models) == 0:
                cfg_path = self.create_modelzoo(model)
                self.model_dir = os.path.dirname(cfg_path)
            elif len(models) == 1:
                self.model_dir = os.path.join(self.dlc_dir,models[0])
            else:
                # more than one, pick the most recent one
                most_recent = datetime(1970,1,1)
                for i, test_model_dir in enumerate(models):
                    pieces = test_model_dir.split('-')
                    this_date = datetime(int(pieces[-3]), int(pieces[-2]), int(pieces[-1]))
                    if this_date > most_recent:
                        model_dir = test_model_dir
                        most_recent = this_date
                self.model_dir = model_dir



        elif self.model_type == 'local':
            pass

        self._model = model

    @property
    def model_dir(self) -> str:
        return self._model_dir

    @model_dir.setter
    def model_dir(self, model_dir):
        if self.model_type == 'zoo':
            pass

            # if not os.path.exists(model_dir):
            #
            #     # self.create_modelzoo()

        elif self.model_type == 'local':
            if not os.path.exists(model_dir):
                # if we were given a path that can be resolved, use it
                # otherwise, check if the model is in our DLC_DIR
                model_dir = os.path.join(self.dlc_dir, model_dir)

        if not os.path.exists(model_dir):
            raise ValueError(f'model_dir given, but model could not be found!\nmodel_dir: {model_dir}')

        self._model_dir = model_dir

    @property
    def dlc_paths(self) -> dict:
        """
        paths used by dlc in manipulating/using models

        * config: <model_dir>/config.yaml
        * train_pose_cfg: <model_dir>/dlc-models/iteration-<n>/<name>/train/pose_cfg.yaml,
        * export_pose_cfg: <model_dir>/exported-models/<name>/pose_cfg.yaml
        * export_dir: <model_dir>/exported-models/<name>

        Returns:
            dict
        """
        config = os.path.join(self.model_dir, 'config.yaml')

        # get pose_cfg in training folder
        train_pose_cfg = None
        # get latest iteration
        dlc_models = os.path.join(self.model_dir, 'dlc-models')
        iteration = sorted([it for it in os.listdir(dlc_models) if it.startswith('iteration')])
        if len(iteration)>0:
            # within an iteration, maybe multiple training sessions
            iteration = os.path.join(dlc_models, iteration[-1])
            training_session = sorted(os.listdir(iteration))
            if len(training_session)>0:
                test_train_pose_cfg = os.path.join(iteration, training_session[-1], 'train', 'pose_cfg.yaml')
                if os.path.exists(test_train_pose_cfg):
                    train_pose_cfg = test_train_pose_cfg

        # get exported pose_cfg.yaml
        exported_pose_cfg = None
        exported_dir = os.path.join(self.model_dir, 'exported-models')
        exported_model_dir = None
        if os.path.exists(exported_dir):
            # FIXME: assuming only one exported model for now
            exported_subdirs = sorted([subd for subd in os.listdir(exported_dir) if \
                                       os.path.isdir(os.path.join(exported_dir,subd))])
            test_exported_pose_cfg = os.path.join(exported_dir,
                                                  exported_subdirs[-1],
                                                  'pose_cfg.yaml')
            if os.path.exists(test_exported_pose_cfg):
                exported_pose_cfg = test_exported_pose_cfg
                exported_model_dir = os.path.join(exported_dir, exported_subdirs[-1])


        return {
            'config':config,
            'train_pose_cfg': train_pose_cfg,
            'export_pose_cfg': exported_pose_cfg,
            'export_dir': exported_model_dir
        }

    @property
    def dlc_dir(self) -> str:
        """
        ``{prefs.BASE_DIR}/dlc``
        Returns:
            str
        """
        if 'DLC_DIR' in prefs.prefdict.keys():
            dlc_dir = prefs.DLC_DIR
        else:
            dlc_dir = os.path.join(prefs.BASEDIR, 'dlc')
            if not os.path.exists(dlc_dir):
                try:
                    os.mkdir(dlc_dir)

                except OSError as e:
                    raise OSError(f'No DLC dir found and one could not be created!\n{e}')
            prefs.add('DLC_DIR', dlc_dir)

        return dlc_dir

    @classmethod
    def list_modelzoo(cls):
        """
        List available modelzoo model names in local deeplabcut version

        Returns:
            list: names of available modelzoo models
        """
        __deeplabcut = __import__('deeplabcut')
        return __deeplabcut.create_project.modelzoo.Modeloptions

    #
    # @property
    # def deeplabcut(self):
    #     if not self._deeplabcut:
    #         try:
    #             os.environ['DLClight'] = "True"
    #             os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
    #             self._deeplabcut = __import__('deeplabcut')
    #         except ImportError as e:
    #             print('deeplabcut not found! deeplabcut must be installed before using this transform!')
    #             raise e
    #     return self._deeplabcut

    def import_dlc(cls):
        if 'deeplabcut' not in sys.modules.keys():
            try:
                os.environ['DLClight'] = "True"
                os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
                import deeplabcut
            except ImportError as e:
                print('deeplabcut not found! deeplabcut must be installed before using this transform!')
                raise e

    def create_modelzoo(self, model):
        self.model_type = "zoo"
        cfg_path, _ = self.deeplabcut.create_pretrained_project(
            model,
            'autopilot',
            [],
            model=model,
            working_directory=self.dlc_dir,
            analyzevideo=False,
            createlabeledvideo=False,
            exportmodel=True)
        return cfg_path

    def load_model(self):
        pass

    def export_model(self):
        # pdb.set_trace()
        if not self.dlc_paths['export_pose_cfg']:
            try:
                self.deeplabcut.export_model(self.dlc_paths['config'])
            except FileExistsError:
                pass

    @property
    def format_in(self) -> dict:
        return {
            'type': np.ndarray
        }

    @property
    def format_out(self) -> dict:
        return {
            'type': np.ndarray
        }


class T_Slice(Transform):
    """
    Generic selection processor
    """
    format_in = {'type': 'any'}
    format_out = {'type': 'any'}

    def __init__(self, select, *args, **kwargs):
        """


        Args:
            select (slice, tuple[slice]): a slice or tuple of slices
            *args:
            **kwargs:
        """
        super(T_Slice, self).__init__(*args, **kwargs)

        self.check_slice(select)

        self.select = select

    def check_slice(self, select):
        if isinstance(select, tuple):
            if not all([isinstance(inner, slice) for inner in select]):
                raise ValueError('Selections require slices or tuples of slices')
        elif not isinstance(select, slice):
            raise ValueError('Selections require slices or tuples of slices')



    def process(self, input):
        return input[self.select]


class T_DLCSlice(T_Slice):
    """
    like
    """
    format_in = {'type': np.ndarray,
                 'parent': T_DLC}
    format_out = {'type': np.ndarray}

    def __init__(self, select, min_probability: float = 0,  *args, **kwargs):
        super(T_DLCSlice, self).__init__(select, *args, **kwargs)

        self.select_index = None
        self.min_probability = np.clip(min_probability, 0, 1)

    def check_slice(self, select):
        if self._parent:
            # only check if we've already gotten a parent
            if select not in self._parent.live.cfg['all_joints_names']:
                raise ValueError('DLC selections must be names of joints!')

    def process(self, input: np.ndarray):
        if self.select_index is None:
            self.select_index = self._parent.live.cfg['all_joints_names'].index(self.select)

        point_row = input[self.select_index, :]
        if point_row[2] > self.min_probability:
            return point_row[0:2]
        else:
            return False


class T_Condition(Transform):
    """
    Compare the input against some condition
    """


    def __init__(self, minimum=None, maximum=None, elementwise=False, *args, **kwargs):
        """

        Args:
            minimum:
            maximum:
            elementwise (bool): if False, return True only if *all* values are within range. otherwise return bool for each tested value
            *args:
            **kwargs:
        """

        if minimum is None and maximum is None:
            raise ValueError("need either a maximum or minimum!")

        super(T_Condition, self).__init__(*args, **kwargs)

        self._minimum = None
        self._maximum = None
        self._shape = None
        self.elementwise = elementwise

        if minimum is not None:
            self.minimum = minimum

        if maximum is not None:
            self._maximum = maximum


    def process(self, input):

        if self.minimum is not None:
            is_greater = np.greater(input, self.minimum)
            if self.maximum is None:
                combined = is_greater

        if self.maximum is not None:
            is_lesser = np.less(input, self.maximum)
            if self.minimum is None:
                combined = is_lesser

        if self.minimum is not None and self.maximum is not None:
            combined = np.logical_and(is_greater, is_lesser)

        if not self.elementwise:
            combined = np.all(combined)

        return combined






    @property
    def minimum(self) -> [np.ndarray, float]:
        return self._minimum

    @minimum.setter
    def minimum(self, minimum: [np.ndarray, float]):
        if isinstance(minimum, float) or isinstance(minimum, int):
            shape = (1,)
        elif isinstance(minimum, np.ndarray):
            shape = minimum.shape
        else:
            raise ValueError('minimum must be a float or ndarray')

        if self._shape:
            if shape != self._shape:
                raise ValueError('cant change shape!')


        self._shape = shape
        self._minimum = minimum

    @property
    def maximum(self) -> [np.ndarray, float]:
        return self._maximum

    @maximum.setter
    def maximum(self, maximum: [np.ndarray, float]):
        if isinstance(maximum, float) or isinstance(maximum, int):
            shape = (1,)
        elif isinstance(maximum, np.ndarray):
            shape = maximum.shape
        else:
            raise ValueError('maximum must be a float or ndarray')

        if self._shape:
            if shape != self._shape:
                raise ValueError('cant change shape!')

        self._shape = shape
        self._maximum = maximum

    @property
    def format_in(self) -> dict:
        if self._shape == (1,):
            ret = {
                'type': float,

            }
        else:
            ret = {
                'type': np.ndarray
            }

        ret['shape'] = self._shape

        return ret


    @property
    def format_out(self) -> dict:
        if self._shape == (1,):
            ret = {
                'type': bool,
            }
        else:
            ret = {
                'type': np.ndarray
            }

        if self.elementwise:
            ret['shape'] = self._shape
        else:
            ret['type'] = bool
            ret['shape'] = (1,)

        return ret







class Img2Loc_binarymass(object):
    METHODS = ('largest')
    def __init__(self, dark_object=True, method="largest"):
        """

        Args:
            dark_object (bool): Is the object dark on a light background (default) or light on a dark background?
            method (str): one of "largest" (find the largest object in each frame)
        """

        self.dark_object = dark_object

        if method in self.METHODS:
            self.method = method
            self.method_fn = getattr(self, self.method)
        else:
            Exception("Unknown method, must be one of {}, got : {}".format(self.METHODS, method))

    def __call__(self, *args, **kwargs):
        return self.method_fn(*args, **kwargs)

    def largest(self, input, return_image=False):

        # TODO: Check if rgb or gray, convert if so

        # blur and binarize with otsu's method
        blur = cv2.GaussianBlur(input, (3,3),0)
        ret, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU)

        # get connected components
        n_components, labels, stats, centroids = cv2.connectedComponentsWithStats(thresh)

        # find largest component
        largest_ind = np.argmax(stats[:,-1])

        # return centroid of largest object
        if return_image:
            return centroids[largest_ind], thresh
        else:
            return centroids[largest_ind]






#
# class Transform(object):
#     """
#     https://blog.usejournal.com/playing-with-inheritance-in-python-73ea4f3b669e
#     """
#
#     def __new__(cls, *args, **kwargs):
#         """
#         Choose a flavor of the particular transform.
#         Flavors should be named This2That_Flavor.
#
#         Args:
#             *args ():
#             **kwargs ():
#
#         Returns:
#
#         """
#         our_name = cls.__name__
#         print(cls)
#         print(our_name)
#
#         flavor = kwargs.get("flavor")
#
#         search_string = "_".join([our_name, flavor])
#
#         # find if there are any matches in our subclasses
#         if cls in Transform.__subclasses__():
#             print('getting subclass')
#             for i in cls.__subclasses__():
#                 if i.__name__ == search_string:
#                     print(i)
#                     #return super(cls).__new__(i)
#                     return i
#         else:
#             # otherwise we are the subclass
#             return super(cls).__new__(cls, *args, **kwargs)
#
#
#
#
# class Img2Loc(Transform):
#     def __init__(self, *args, **kwargs):
#         print('Img2Loc class')
#
# class Img2Loc_binarymass(Img2Loc):
#     def __init__(self, *args, **kwargs):
#         super(Img2Loc_binarymass, self).__init__()
#         print('binarymass class')
#

