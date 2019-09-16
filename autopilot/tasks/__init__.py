# from taskontrol.templates.nafc import Nafc
from autopilot.tasks.task import Task
from autopilot.tasks.nafc import Nafc, Nafc_Wheel
from autopilot.tasks.gonogo import GoNoGo
from autopilot.tasks.free_water import Free_Water
from autopilot.tasks.graduation import GRAD_LIST
from autopilot.tasks.children import Wheel_Child


TASK_LIST = {'2AFC':Nafc,
             'Free Water':Free_Water,
             '2AFC_Wheel': Nafc_Wheel,
             'GoNoGo': GoNoGo}
             #'Gap 2AFC':Gap_2AFC}

CHILDREN_LIST = {
    'Wheel Child':Wheel_Child
}

