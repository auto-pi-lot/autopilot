# from taskontrol.templates.nafc import Nafc
from rpilot.tasks.task import Task
from rpilot.tasks.nafc import Nafc
from rpilot.tasks.free_water import Free_Water
from rpilot.tasks.graduation import GRAD_LIST


TASK_LIST = {'2AFC':Nafc,
             'Free Water':Free_Water}
             #'Gap 2AFC':Gap_2AFC}
