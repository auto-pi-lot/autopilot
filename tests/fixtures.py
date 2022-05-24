import uuid
from datetime import datetime
import typing

import numpy as np
import pytest
from pathlib import Path
import json

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
        genotype=genotype,
        start_date = datetime(year=np.random.randint(2000,2020), month=np.random.randint(1,12), day=np.random.randint(1,28), hour=np.random.randint(0,23), minute=np.random.randint(0,59), second=np.random.randint(0,59)),
    )
    return bio

@pytest.fixture
def dummy_protocol() -> typing.List[dict]:
    protocol = [
        {
            "allow_repeat": True,
            "graduation": {
                "type": "NTrials",
                "value": {
                    "n_trials": "100",
                    "type": "NTrials"
                }
            },
            "reward": 10,
            "step_name": "Free_Water",
            "task_type": "Free_Water"
        },
        {
            "bias_mode": "None",
            "correction": True,
            "graduation": {
                "type": "Accuracy",
                "value": {
                    "threshold": ".99",
                    "type": "Accuracy",
                    "window": "1000"
                }
            },
            "punish_dur": 20,
            "punish_stim": True,
            "req_reward": True,
            "reward": 10,
            "step_name": "Nafc",
            "stim": {
                "sounds": {
                    "L": [
                        {
                            "amplitude": "0.1",
                            "duration": "100",
                            "frequency": "1000",
                            "type": "Tone"
                        }
                    ],
                    "R": [
                        {
                            "amplitude": "0.1",
                            "duration": "100",
                            "frequency": "2000",
                            "type": "Tone"
                        }
                    ]
                },
                "tag": "Sounds",
                "type": "sounds"
            },
            "task_type": "Nafc"
        }
    ]
    return protocol

@pytest.fixture
def dummy_protocol_file(dummy_protocol) -> Path:
    protocol_dir = Path(get('PROTOCOLDIR')).resolve()
    protocol_file = protocol_dir / 'dummy_protocol.json'
    if protocol_file.exists():
        protocol_file.unlink()

    with open(protocol_file, 'w') as pfile:
        json.dump(dummy_protocol, pfile)

    return protocol_file
