from autopilot.tasks.task import Task
from autopilot.tasks.nafc import Nafc
from autopilot.tasks.gonogo import GoNoGo
from autopilot.tasks.parallax import Parallax
from autopilot.tasks.free_water import Free_Water
from autopilot.tasks.graduation import GRAD_LIST
from autopilot.tasks.children import Wheel_Child, Video_Child


TASK_LIST = {'2AFC':Nafc,
             'Free Water':Free_Water,
             'GoNoGo': GoNoGo,
             'Parallax': Parallax}
             # unfinished tasks
             # '2AFC_Wheel': Nafc_Wheel,
             #'Gap 2AFC':Gap_2AFC}

CHILDREN_LIST = {
    'Wheel Child':Wheel_Child,
    'Video Child':Video_Child
}

