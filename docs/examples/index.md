# Examples

We're working on writing more examples! Please let us know in the discussion board what you'd like to see :)

Also see the ``examples`` folder in the repository for jupyter notebooks we haven't set up Sphinx rendering for yet ;)


```{toctree}
:maxdepth: 1
:caption: Tasks

blink
gonogo
```


```{note}

For more examples, see
the [plugins on the wiki](https://wiki.auto-pi-lot.com/index.php/Autopilot_Plugins), two to get you started:

* [Autopilot Paper Plugin](https://wiki.auto-pi-lot.com/index.php/Plugin:Autopilot_Paper) - [Network_Latency ](https://github.com/auto-pi-lot/plugin-paper/blob/main/plugin_paper/tasks/network.py):
  for testing network latency between two pilots, demonstrates:

    * using a single task for two pilots with different roles,
    * Point-to-point networking with {class}`.Net_Node` s
    * Using the {class}`.Terminal_Station` to connect pilots without knowing their IP/Port

* [Wehrlab Plugin](https://wiki.auto-pi-lot.com/index.php/Wehrlab) - [Nafc_Gap](https://github.com/auto-pi-lot/autopilot-plugin-wehrlab/blob/29a7d04c7f0b6dc4234dc0f9e5f00d2edc102eb4/gap/nafc_gap.py#L13) ,
  [Nafc_Gap_Laser](https://github.com/auto-pi-lot/autopilot-plugin-wehrlab/blob/29a7d04c7f0b6dc4234dc0f9e5f00d2edc102eb4/gap/nafc_gap.py#L59):
  Extensions of the Nafc class to do experiments with gaps in continuous background noise, which demonstrate:

    * Extending the ``__init__`` and ``end`` methods of a task class to do additional things on initialization and teardown
      -- specifically starting and stopping background noise
    * Adding additional ``PARAMS``, ``HARDWARE`` objects, and ``TrialData`` fields
    * Extending task methods without rewriting them -- specifically adding optogentic stimulation to an existing task!

```