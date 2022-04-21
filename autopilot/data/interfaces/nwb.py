"""

Sketch of the problem:

.. graphviz::

    digraph {

        subgraph cluster_subject {
            label = "Subject"

            subject_schema
            biography
            history_table
            hash_table
            trial_data
            extension_schema

            subject_object
        }

        subject_schema -> biography
        subject_schema -> history_table
        subject_schema -> hash_table
        subject_schema -> trial_data
        subject_schema -> extension_schema
        subject_object -> subject_schema

        subgraph cluster_task {
            label = "Task"

            task_schema
            task_timestamps[label="timestamps"]
            task_trial[label="TrialData"]
            task_continuous[label="ContinuousData"]
        }

        task_schema -> task_trial
        task_schema -> task_continuous
        task_schema -> task_timestamps
        subject_object -> task_schema



        subgraph cluster_interfaces {
            label = "Interfaces"

            generic_hdf5

            subgraph cluster_nwbconvert {

                nwbconverter
                nwbfile
                nwbcontainer
                NWBHDFIO

                nwbconverter -> nwbfile
                nwbfile -> nwbcontainer
                nwbcontainer -> NWBHDFIO

            }


        }

         generic_hdf5 -> subject_file
        biography -> generic_hdf5
        history_table -> generic_hdf5
        hash_table -> generic_hdf5
        trial_data -> generic_hdf5
        extension_schema -> generic_hdf5
        task_timestamps -> generic_hdf5
        task_trial -> generic_hdf5
        task_continuous -> generic_hdf5



        subgraph cluster_nwb {
            label = "NWB"
            nwb_schema
            nwb_container
            nwb_subject[label="file.Subject"]
            nwb_epoch[label=".BehavioralEpochs"]
            nwb_events[label="BehavioralEvents"]
            nwb_create_timeseries[label="create_timeseries"]
            nwb_create_intervals[label="create_interval_series"]
        }

        subgraph cluster_output {
            subject_file[shape=folder]
            nwb_file[shape=folder]
        }

        NWBHDFIO -> nwb_file


        nwb_container -> nwb_subject
        nwb_container -> nwb_epoch
        nwb_container -> nwb_events
        nwb_events -> nwb_create_timeseries
        nwb_epoch -> nwb_create_intervals
        nwb_create_timeseries -> nwbcontainer
        nwb_create_intervals -> nwbcontainer

        biography -> nwbfile
        task_trial -> nwb_create_timeseries [label="For each"]
        task_timestamps -> nwb_create_timeseries
        task_continuous -> nwb_create_intervals
    }
"""

from autopilot.root import Autopilot_Type
from autopilot.data.models.biography import Biography
import typing
from typing import List, Optional
from pathlib import Path
if typing.TYPE_CHECKING:
    from autopilot.data.subject import Subject

from pynwb import NWBFile
from pynwb.file import Subject as NWBSubject


def make_biography(bio:Biography) -> NWBSubject:
    """
    Make an NWB subject object from a biography

    .. todo::

        make this more flexible based on a mapping

    """
    samename = ['description', 'sex', 'species']
    kwargs = {k:getattr(bio, k) for k in samename}
    # get the ones with trivial differences
    kwargs['subject_id'] = bio.id
    kwargs['date_of_birth'] = bio.dob
    kwargs['age'] = str(bio.age)

    if bio.genotype is not None:
        kwargs.update({
            'genotype': str(bio.genotype.genes),
            'strain': bio.genotype.strain
        })

    if bio.baselines is not None:
        kwargs['weight'] = bio.baselines.mass / 1000

    return NWBSubject(**kwargs)


class NWB_Interface(Autopilot_Type):
    biography: Biography

    def make(self, sub: 'Subject', out_dir: Path) -> NWBFile:
        assert(out_dir.is_dir())

        # get biography object from subject
        bio = make_biography(sub.info)

        # TODO: Get rest of tables as dataframes and use
        # .add_scratch to add them

        # for each session, create a BehavioralEvents object and create_timeseries
        # for each of the columns.
        # try to extract stim params and



