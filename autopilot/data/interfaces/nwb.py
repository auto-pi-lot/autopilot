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