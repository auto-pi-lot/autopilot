"""
Test the subject data interface
"""
from datetime import datetime
from pathlib import Path
import uuid

import pytest

import numpy as np

from autopilot.data.models import subject as sub_models, biography
from autopilot.data.subject import Subject
from autopilot import prefs

from .fixtures import default_dirs

@pytest.fixture
def dummy_biography() -> biography.Biography:
    """
    A biography object with everything filled in with random data
    """
    enclosure = biography.Enclosure(
        box=np.random.randint(1,1000),
        building='science incorporated hq',
        room=101
    )

    breeding = biography.Breeding(
        parents = ['mr apple', 'mrs banana'],
        litter = 'a very special anniversary for the wonderful couple'
    )

    genotype = biography.Genotype(
        strain='black 6 (directors cut)',
        genes = [
            biography.Gene(name='strength', zygosity='homozygous'),
            biography.Gene(name='speed',    zygosity='heterozygous')
        ]
    )

    baselines = biography.Baselines(mass=np.random.rand()*10, minimum_pct=0.8)

    bio = biography.Biography(
        id='junior-' + str(uuid.uuid4()),
        dob=datetime(year=np.random.randint(2000,2020), month=np.random.randint(1,12), day=np.random.randint(1,28)),
        sex=np.random.choice(['M', 'F', 'U', 'O']),
        description="our little baby, we are so proud of them",
        tags={'anything': 'extra', 'we': 'thought', 'u': [1, 2, 3, True, None, 6.5], 'should': 'know'},
        species='cockroach',
        breeding=breeding,
        enclosure=enclosure,
        baselines=baselines,
        genotype=genotype
    )
    return bio

def test_new(dummy_biography: biography.Biography, default_dirs):
    """
    Test that we can make a new file from dummy biography and default structure
    """
    out_path = Path(prefs.get('DATADIR')).resolve() / (dummy_biography.id + '.h5')
    if out_path.exists():
        out_path.unlink()

    assert not out_path.exists()

    sub = Subject.new(dummy_biography)

    assert out_path.exists()
    assert sub.info == dummy_biography

    out_path.unlink()





