"""
Base units
"""

class Autopilot_Unit:
    """
    Metaclass for units!

    .. todo::

        Allow declaration of specific subtypes, like with multiplication, ``unit & 'mg'``
    """



class Mass(Autopilot_Unit, float):
    """
    Base Unit: Grams
    """
