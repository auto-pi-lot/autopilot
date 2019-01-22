# from taskontrol.templates.nafc import Nafc
from task import Task
from nafc import Nafc, Gap_2AFC
from free_water import Free_Water
from graduation import GRAD_LIST


TASK_LIST = {'2AFC':Nafc,
             'Free Water':Free_Water,
             'Gap 2AFC':Gap_2AFC}

