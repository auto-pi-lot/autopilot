# models

```{inheritance-diagram} autopilot.data.models.biography autopilot.data.models.protocol autopilot.data.models.researcher autopilot.data.models.subject
:top-classes: autopilot.root.Autopilot_Type
:parts: -2
```

Specific models are then built out of the basic modeling components! This will serve as the point where data models can be
added or modified by plugins (stay tuned).

Each of the modules contains several classes that are used together in some particular context:

* {mod}`.models.biography` - Defines biographical information for an individual {class}`.Subject`
* {mod}`.models.protocol` - Defines the data structure of how multiple {class}`.Task`s are stacked together into a training protocol,
  as well as how they are represented in the Subject's h5f file.
* {mod}`.models.subject` - Schemas that define how the multiple models that go into a subject are combined and structured on disk
* {mod}`.models.researcher` - Stubs for researcher information that will be used in future versions for giving explicit
  credit for data gathered by a particular researcher or research group...


```{eval-rst}
.. automodule:: autopilot.data.models
    :members:
    :undoc-members:
    :show-inheritance:
```

```{toctree}
biography
protocol
researcher
subject
```