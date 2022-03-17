import uuid
from datetime import datetime

import numpy as np
import pytest
from pathlib import Path

from autopilot.data.models import biography
from autopilot.prefs import _DEFAULTS, Scopes, get, set
from autopilot.external import start_jackd

@pytest.fixture
def default_dirs():
    for k, v in _DEFAULTS.items():
        if v['scope'] == Scopes.DIRECTORY and 'default' in v.keys():
            Path(v['default']).mkdir(parents=True, exist_ok=True)


@pytest.fixture(scope='session')
def jack_server():
    pass


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