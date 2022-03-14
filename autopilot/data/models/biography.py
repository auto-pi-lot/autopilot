"""
Data models (and transformations?) for experimental subject biographies
"""
from datetime import datetime

from autopilot.data.modeling.base import Data

class Biography(Data):
    """
    Definition of experimental subject biography

    **Development Goals**

    - Replace the implicit biographical structure in the :class:`.gui.New_Subject_Wizard` (embarassing)
    - Interface with the NWB biographical information schema.
    """
    id: str
    dob: datetime
    start_date: datetime


class Baselines(Data):

