# data



Autopilot's data handling system was revamped as of v0.5.0, and now is based on [pydantic](https://pydantic-docs.helpmanual.io/)
models and a series of interfaces that allow us to write data from the same abstract structures to several formats, initially
pytables and hdf5, but we have laid the groundwork for exporting to {mod}`.nwb` and {mod}`.datajoint` natively.

A brief narrative overview here, and more detailed documentations within the relevant module documentation.



## {mod}`.modeling` - Basic Data Types

```{inheritance-diagram} autopilot.data.modeling.base

```

## {mod}`.models` - The Models Themselves

```{inheritance-diagram} autopilot.data.models.biography autopilot.data.models.protocol autopilot.data.models.researcher autopilot.data.models.subject
:top-classes: autopilot.root.Autopilot_Type
```

## {mod}`.interfaces` - Bridging to Multiple Representations

## {class}`.Subject` - The Main Interface to Data Collection

## {mod}`~.data.units` - Explicit SI Unit representation






```{eval-rst}
.. automodule:: autopilot.data
    :members:
    :undoc-members:
    :show-inheritance:
```

```{toctree}
subject
interfaces/index
modeling/index
models/index
units/index
```

