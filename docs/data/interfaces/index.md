# interfaces


```{inheritance-diagram} autopilot.data.interfaces.base autopilot.data.interfaces.tables autopilot.data.interfaces.datajoint autopilot.data.interfaces.nwb

```

Interfaces define mappings between basic python types and the classes in {mod}`.modeling`. 

This set of classes is still growing, and we're still exploring the best strategy to make generalizable interfaces
between very different formats, but in general, each interface consists of mappings between types and some means of converting
the particular data structures of one format and another.

* {class}`.Interface_Map` - A specific declaration that one type is equivalent to another, with some optional conversion or parameterization
* {class}`.Interface_Mapset` - A collection of {class}`.Interface_Map`s that define mappings for a collection of basic python Types
* {class}`.Interface` - A stub for a future class that will handle conversion of the basic modeling components, but 
  for this first pass we have just applied the mapsets directly to certain subtypes of modeling objects: See {func}`.tables.model_to_description`
  and {func}`.tables.description_to_model`

The only interface that is actively used within Autopilot is that for {mod}`~.interfaces.tables`, but we have 
started interfaces for {mod}`.nwb` and {mod}`.datajoint` (using a parallel project [datajoint-babel](https://github.com/auto-pi-lot/datajoint-babel)).
Both of these are provisional and very incomplete, but it is possible to generate a datajoint schema from any
table, and there are mappings and conversions for their different representations of types.

Our goal for future versions is to generalize data interfaces to the point where a similar API can be shared across
them, so a subject's data can be stored in HDF5 or in a datajoint database equivalently.

```{eval-rst}
.. automodule:: autopilot.data.interfaces
    :members:
    :undoc-members:
    :show-inheritance:
```


```{toctree}
base
tables
datajoint
nwb
```