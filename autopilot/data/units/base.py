"""
Base units
"""
import inspect

class Autopilot_Unit:
    """
    Metaclass for units!

    .. todo::

        Allow declaration of specific subtypes, like with multiplication, ``unit & 'mg'``
    """

    @classmethod
    def _base_class(cls) -> type:
        """Base python type that this unit derives from"""
        mro = inspect.getmro(cls)
        return mro[mro.index(Autopilot_Unit)+1]



class Mass(Autopilot_Unit, float):
    """
    Base Unit: Grams
    """

    @property
    def kg(self) -> float:
        return self.real/1000

    @property
    def mg(self) -> float:
        return self.real*1000