from autopilot.tasks.task import Task
from autopilot.tasks.nafc import Nafc, Nafc_Gap
from autopilot.tasks.gonogo import GoNoGo
from autopilot.tasks.parallax import Parallax
from autopilot.tasks.free_water import Free_Water
from autopilot.tasks.graduation import GRAD_LIST
from autopilot.tasks.children import Wheel_Child, Video_Child, Transformer
from autopilot.tasks.test import DLC_Latency, DLC_Hand


TASK_LIST = {'2AFC':Nafc,
             '2AFC_Gap':Nafc_Gap,
             'Free Water':Free_Water,
             'GoNoGo': GoNoGo,
             'Parallax': Parallax,
             'Test_DLC_Latency': DLC_Latency,
             'Test_DLC_Hand':DLC_Hand}
"""
Link between string task names used in protocol descriptions and task classes
"""

CHILDREN_LIST = {
    'Wheel Child':Wheel_Child,
    'Video Child':Video_Child,
    'Transformer': Transformer
}
"""
Link between string child names used in protocol descriptions and task classes
"""

