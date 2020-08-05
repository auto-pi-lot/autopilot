import os
import sys
import typing
from datetime import datetime

import numpy as np

from autopilot import prefs
from autopilot.transform.transforms import Transform


class Image(Transform):
    """
    Metaclass for transformations of images
    """

    def __init__(self, shape=None, *args, **kwargs):
        super(Image, self).__init__(*args, **kwargs)
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


class DLC(Image):
    """
    Do pose estimation with ``DeepLabCut-Live``!!!!!

    Specify a ``model_dir`` (relative to ``<BASEDIR>/dlc`` or absolute) or a model name from the DLC model zoo.

    All other args and kwargs are passed on to :class:`dlclive.DLCLive`,
    see its documentation for details: https://github.com/DeepLabCut/DeepLabCut-live

    Attributes:
        model_type (str, 'local' or 'zoo'): whether a directory (local) or a modelzoo name (zoo) was passed
        live (:class:`dlclive.DLCLive`): the DLCLive object
    """

    def __init__(self, model_dir: str = None, model_zoo: str = None, *args, **kwargs):
        """
        Must give either ``model_dir`` or ``model_zoo``

        Args:
            model_dir (str): directory of model, either absolute or relative to ``<BASEDIR>/dlc``. if ``None``, use ``model_zoo``
            model_zoo (str): name of modelzoo model. if ``None``, use ``model_dir``

            *args: passed to DLCLive and superclass
            **kwargs: passed to DLCLive and superclass
        """
        super(DLC, self).__init__(*args, **kwargs)

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
        self.live.init_inference()

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
                autopilot_model_dir = os.path.join(self.dlc_dir, model_dir)
                if os.path.exists(autopilot_model_dir):
                    model_dir = autopilot_model_dir
                else:
                    # see if a model *starting* with the model name exists
                    autopilot_models = os.listdir(self.dlc_dir)
                    autopilot_models = [a for a in autopilot_models if a.startswith(model_dir)]
                    if len(autopilot_models)>0:
                        model_dir = os.path.join(self.dlc_dir,autopilot_models[0])

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
        if 'DLCDIR' in prefs.prefdict.keys():
            dlc_dir = prefs.DLCDIR
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