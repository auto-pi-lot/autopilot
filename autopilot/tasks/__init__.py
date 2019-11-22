from autopilot.tasks.task import Task
from autopilot.tasks.nafc import Nafc, Nafc_Gap
from autopilot.tasks.gonogo import GoNoGo
from autopilot.tasks.free_water import Free_Water
from autopilot.tasks.graduation import GRAD_LIST
from autopilot.tasks.children import Wheel_Child


TASK_LIST = {'2AFC':Nafc,
             '2AFC_Gap':Nafc_Gap,
             'Free Water':Free_Water,
             'GoNoGo': GoNoGo,
             }
             # unfinished tasks
             # '2AFC_Wheel': Nafc_Wheel,
             #'Gap 2AFC':Gap_2AFC}

CHILDREN_LIST = {
    'Wheel Child':Wheel_Child
}

