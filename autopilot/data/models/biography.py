"""
Data models for experimental subject biographies
"""
import typing
from typing import Optional, Literal, List, Union
from datetime import datetime, timedelta, date
from pydantic import Field
import uuid

from autopilot.data.modeling.base import Data, Attributes
from autopilot.data.units.base import Mass

SEX = Literal['F', 'M', 'U', 'O']
"""
- (F)emale
- (M)ale, 
- (U)nknown, 
- (O)ther. 

We are following the Neurodata Without Borders suggestions here, but note that these
are not prescriptive and will be happily expanded whenever needed.
"""

ZYGOSITY = Literal['heterozygous', 'homozygous']

class Enclosure(Data):
    """
    Where does the subject live?
    """
    box: Optional[typing.Union[str, int]] = Field(None, description="The number or name of the box this subject lives in, if any")
    building: Optional[str] = Field(None, description="The name of the building that the subject is housed in")
    room: Optional[Union[str,int]] = Field(None, description="The room number that the animal is housed in")


class Breeding(Data):
    """
    Information about the breeding conditions of the subject
    """
    parents: List[str] = Field(..., description="The IDs of the parents of this subject, if any")
    litter: Union[str, int] = Field(..., description="The identifying number or tag of the litter this subject was born in")


class Gene(Data):
    """
    An individual (trans)gene that an animal may have.

    I am not a geneticist, lmk what this should look like
    """
    name: str = Field(..., description="The name of this gene")
    zygosity: ZYGOSITY = Field(None, description=f"One of {ZYGOSITY}")


class Genotype(Data):
    """
    Genotyping information, information about a subject's background and (potentially multiple) :class:`.Gene` s of interest

    .. todo::

        Call Jax's API to get a list of available strain names

    """
    strain: Optional[str] = Field(None, description="The strain or background line of this subject, if any")
    genes: Optional[List[Gene]] = Field(None, description="A list of any transgenes that this animal has")


class Baselines(Data):
    """
    Baseline health measurements for animal care regulation. In the future this
    will be integrated with a TrialManager class to titrate trials to ensure experimental
    subjects remain healthy.
    """
    mass: Optional[Mass] = Field(None, description="Mass (grams) of the animal before any experimental manipulation")
    minimum_pct: Optional[float] = Field(None, description="The proportion (0-1) of the baseline mass that the animal is not allowed to fall under")

    @property
    def minimum_mass(self) -> float:
        """
        The minimum mass (g), computed as :attr:`.mass` * :attr:`.minimum_pct`
        """
        if self.mass is None or self.minimum_pct is None:
            raise ValueError("Cant compute minimum mass without a baseline mass or minimum percent!")
        return self.mass * self.minimum_pct



class Biography(Attributes):
    """
    The combined biographical, health, genetic, and other details that define an experimental subject.

    This is stored within the ``/info`` node in a typical :class:`.Subject` file as
    metadata attributes, and accessible from :attr:`.Subject.info`

    **Development Goals**

    - Interface with the NWB biographical information schema.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="The indentifying string, name, subject_id, etc. for this subject. " + \
                                      "This value is also used to name the related Subject file, like {id}.h5, so these are typically expected to be unique. " + \
                                      "If None is provided, a uuid.uuid4() will be generated (which will be ugly so you probably want to give an id).")
    start_date: Optional[datetime] = Field(default_factory=datetime.now, description="The date that this subject file was created. Not that this is not necessarily the date " + \
                                 "that the subject began training, which is more reliably determined from the timestamps within the data. If none is provided, generated from current time.")
    dob: Optional[datetime] = Field(None, description="The subject's date of birth. A datetime is allowed, but hours and minutes are typically not reliable. A time of midnight formally indicates " + \
                                    "that the hour and minute is not precise.")
    sex: SEX = Field('U', description=f"Sex of the subject, one of {SEX}. See :data:`.SEX`")
    description: Optional[str] = Field(None, description="Some lengthier description of the subject, idk go hogwild.")
    tags: Optional[dict]= Field(None, description="Any additional key/value tags that apply to this subject. Idiosyncratic metadata can be " + \
                                "stored here, but caution should be taken to not overload this field and instead extend the Biography class because " + \
                                "these values will not be included in any resulting schema.")
    species: Optional[str] = Field(None, description="Species of subject, no recommendation common vs. latin names, but will be integrated with linked data schemas in the future")
    breeding: Optional[Breeding] = None
    enclosure: Optional[Enclosure] = None
    baselines: Optional[Baselines] = None
    genotype: Optional[Genotype] = None

    @property
    def age(self) -> timedelta:
        """Difference between now and :attr:`.dob`"""
        return datetime.now() - self.dob
