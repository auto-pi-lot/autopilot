"""
Sometimes a GUI just doesn't cut it for making tasks, eg. those with many steps, many stimuli, etc.
"""

import copy
from autopilot import tasks
from autopilot.core import utils
import pandas as pd
import os
import itertools
import json

def manystep_speech(token_dir, out_fn):
    """
    Makes a protocol with ::

        * one free water step with 200 trials
        * one request rewards tone discrimination step 300 trials
        * one tone discim step 75% accuracy over 400 trials
        * many steps that introduce new tokens pairwise.

    Args:
        out_fn (str): where to write the task .json file
        token_dir (str): where the speech tokens are

    """

    # list all the speech tokens
    tokens = utils.listdir(token_dir, 'wav')

    # make df of token attributes
    token_relpath = [t.replace(token_dir, "").lstrip(os.sep) for t in tokens]
    speaker = [t.split(os.sep)[0] for t in token_relpath]
    consonant = [t.split(os.sep)[1][0] for t in token_relpath]
    vowel = [t.split(os.sep)[1][1:] for t in token_relpath]
    token = [os.path.splitext(t.split(os.sep)[2])[0].split('_')[-1] for t in token_relpath]

    token_df = pd.DataFrame({'path':tokens,
                             'relpath': token_relpath,
                             'speaker': speaker,
                             'consonant': consonant,
                             'vowel': vowel,
                             'token': token}, dtype=str)
    token_df.token = token_df.token.astype(int)
    token_df = token_df.sort_values(['speaker', 'consonant', 'vowel', 'token'])

    # we introduce tokens as the product of speaker, vowel, and token:
    # ie. introduce S1V1T(oken)1, 2, 3, then S1V2T1,2,3, S2V1
    # but since product will exhaust the speaker first (ie. introduce all vowels
    # and tokens from S1 before S2) we have to stack a few iterations
    speakers_1 = ['Brynna']
    vowels_1   = ['a', 'i']
    tokens_1   = [0, 1, 2]

    speakers_2 = ['Jonny']

    speakers_3 = ['Brynna', 'Jonny']
    vowels_3   = ['u']

    speakers_4 = ['Anna']
    vowels_4   = ['a', 'i', 'u']

    order_1 = itertools.product(speakers_1, vowels_1, tokens_1)
    order_2 = itertools.product(speakers_2, vowels_1, tokens_1)
    order_3 = itertools.product(speakers_3, vowels_3, tokens_1)
    order_4 = itertools.product(speakers_4, vowels_4, tokens_1)

    order = list(itertools.chain(order_1, order_2, order_3, order_4))

    # make steps of task
    base_task = {
        "graduation": {
            "type": "accuracy",
            "value": {
                "threshold": ".80",
                "window": "1000",
                "type": "accuracy"
            }
        },
        "reward": {'type': 'volume',
                   'value': '2.5'},
        "req_reward": False,
        "correction": True,
        "bias_mode": False,
        "punish_dur": "5000",
        "task_type": "2AFC",
        "step_name": "speech_1",
        "pct_correction": "10",
        "stim": {
            "manager": "proportional",
            "type": "sounds",
            "groups": [
                {"name": "training",
                 "frequency": 0.98,
                 "sounds": {
                     'R': [],
                     'L': []
                 }},
                {"name": "generalization",
                 "frequency": 0.02,
                 "sounds": {
                     'R': [],
                     'L': []
                 }}
                ]
        },
        "punish_sound": False
    }

    # make a dictionary to describe every token so we can add them to the task later
    token_dicts = {}
    for i, row in token_df.iterrows():
        new_tok = {
            'token': str(row.token),
            'speaker': str(row.speaker),
            'vowel': str(row.vowel),
            'path': row.relpath,
            'consonant': row.consonant,
            'type': 'Speech',
            'amplitude': '0.02'
        }
        token_dicts[row.relpath] = new_tok



    steps = []
    relpaths = [] # keep track of which relpaths are in our task
    step_num = itertools.count(1)
    for speaker, vowel, token in order:
        # get /b/ and /g/ relpaths
        b_path = token_df[(token_df.speaker == speaker) &
                          (token_df.vowel == vowel) &
                          (token_df.token == token) &
                          (token_df.consonant == "b")].relpath.values[0]
        g_path = token_df[(token_df.speaker == speaker) &
                          (token_df.vowel == vowel) &
                          (token_df.token == token) &
                          (token_df.consonant == "g")].relpath.values[0]

        relpaths.append(b_path)
        relpaths.append(g_path)

        # add sounds to task
        if len(steps) == 0:
            step_dict = copy.deepcopy(base_task)
        else:
            step_dict = copy.deepcopy(steps[-1])

        # first add new training tokens
        step_dict['stim']['groups'][0]['sounds']['R'].append(token_dicts[b_path])
        step_dict['stim']['groups'][0]['sounds']['L'].append(token_dicts[g_path])

        # then add generalization tokens
        b_gens = [v for k, v in token_dicts.items() if k not in relpaths and v['consonant'] == 'b']
        g_gens = [v for k, v in token_dicts.items() if k not in relpaths and v['consonant'] == 'g']
        step_dict['stim']['groups'][1]['sounds']['R'] = b_gens
        step_dict['stim']['groups'][1]['sounds']['L'] = g_gens

        # change step name
        step_dict['step_name'] = 'speech_' + str(next(step_num))


        steps.append(step_dict)

    # free water stage
    reward_dict = {'type':'volume',
                   'value':2.5}

    fw_params = {
        "task_type": "Free Water",
        "allow_repeat": False,
        "reward": {'type':'volume', 'value':5.0},
        "step_name": "Free Water",
        "graduation": {
            "type": "n_trials",
            "value": {
                "current_trial": "0",
                "type": "n_trials",
                "n_trials": "200"
            }
        }
    }

    # req rewards stage
    req_rewards = {
        "graduation": {
            "type": "n_trials",
            "value": {
                "current_trial": "0",
                "type": "n_trials",
                "n_trials": "300"
            }
        },
        "reward": reward_dict,
        "req_reward": True,
        "correction": False,
        "bias_mode": 0,
        "punish_dur": "500",
        "task_type": "2AFC",
        "step_name": "reqrewards",
        "stim": {
            "sounds": {
                "R": [
                    {
                        "duration": "100",
                        "frequency": "10000",
                        "type": "Tone",
                        "amplitude": "0.01"
                    }
                ],
                "L": [
                    {
                        "duration": "100",
                        "frequency": "5000",
                        "type": "Tone",
                        "amplitude": "0.01"
                    }
                ]
            }
        },
        "punish_sound": False
    }

    # tone discrim stage
    tone_discrim = {
        "graduation": {
            "type": "accuracy",
            "value": {
                "threshold": "0.75",
                "window": "400",
                "type": "accuracy"
            }
        },
        "reward": "20",
        "req_reward": False,
        "correction": True,
        "bias_mode": 0,
        "punish_dur": "3500",
        "task_type": "2AFC",
        "step_name": "tonediscrim",
        "pct_correction": "10",
        "stim": {
            "sounds": {
                "R": [
                    {
                        "duration": "100",
                        "frequency": "10000",
                        "type": "Tone",
                        "amplitude": "0.01"
                    }
                ],
                "L": [
                    {
                        "duration": "100",
                        "frequency": "5000",
                        "type": "Tone",
                        "amplitude": "0.01"
                    }
                ]
            }
        },
        "punish_sound": False
    }

    # combine all
    task = [fw_params, req_rewards, tone_discrim]
    task.extend(steps)

    with open(out_fn, 'w') as outf:
        json.dump(task, outf)

    print('wrote task with {} steps to {}'.format(len(task), out_fn))



