"""
Data models (and transformations?) for experimental subject biographies
"""
import typing
from typing import Optional, Literal
from datetime import datetime, timedelta, date
from pydantic import Field

from autopilot.data.modeling.base import Data
from autopilot.data.units.base import Mass

SEX = Literal['F', 'M', 'U', 'O']
"""
(F)emale, (M)ale, (U)nknown, (O)ther
"""

ZYGOSITY = Literal['Heterozygous', 'Homozygous']


class Enclosure(Data):
    """
    Where does the subject live?
    """
    box: typing.Union[str, int]
    building: Optional[str] = None
    room: Optional[str] = None


class Breeding(Data):
    """
    Information about the breeding conditions of the subject
    """
    mother: str
    father: str
    litter: typing.Union[str, int]


class Gene(Data):
    """
    An individual (trans)gene that an animal may have
    """
    name: str
    zygosity: ZYGOSITY


class Genotype(Data):
    """
    Genotyping information
    """
    strain: str
    genes: Optional[typing.List[Gene]]


class Baselines(Data):
    """
    Experimental measured baselines
    """
    mass: typing.Optional[Mass] = None
    minimum_pct: typing.Optional[float] = None

    @property
    def minimum_mass(self) -> float:
        if self.mass is None or self.minimum_pct is None:
            raise ValueError("Cant compute minimum mass without a baseline mass or minimum percent!")
        return self.mass * self.minimum_pct



class Biography(Data):
    """
    Definition of experimental subject biography

    **Development Goals**

    - Replace the implicit biographical structure in the :class:`.gui.New_Subject_Wizard` (embarrassing)
    - Interface with the NWB biographical information schema.
    """
    id: str
    start_date: datetime = Field(default_factory=datetime.now)
    dob: Optional[datetime] = None
    sex: SEX = 'U'
    description: Optional[str] = None
    species: Optional[str] = None
    breeding: Optional[Breeding] = None
    enclosure: Optional[Enclosure] = None
    baselines: Optional[Baselines] = None
    genotype: Optional[Genotype] = None

    @property
    def age(self) -> timedelta:
        """Difference between now and :attr:`.dob` """
        return datetime.now() - self.dob
