# data



Autopilot's data handling system was revamped as of v0.5.0, and now is based on [pydantic](https://pydantic-docs.helpmanual.io/)
models and a series of interfaces that allow us to write data from the same abstract structures to several formats, initially
pytables and hdf5, but we have laid the groundwork for exporting to {mod}`.nwb` and {mod}`.datajoint` natively.

A brief narrative overview here, and more detailed documentations within the relevant module documentation.

## {mod}`.modeling` - Basic Data Types

```{inheritance-diagram} autopilot.data.modeling.base

```

Autopilot's models are built from [pydantic models](https://pydantic-docs.helpmanual.io/usage/models/). 

The {mod}`autopilot.root` module defines some of Autopilot's basic metaclasses, one of which is {class}`.Autopilot_Type`.
The {mod}`.data.modeling` module extends {class}`.Autopilot_Type` into several abstract modeling classes used for different
types of data:

* {class}`.modeling.base.Data` - Containers for data, generally these are used as containers for data, or else used to
  specify how data should be handled and typed. Its subtypes indicate different classes of data that have different 
  means of storage and representation depending on the interface.
    * {class}`.modeling.base.Attributes` - Static (usually metadata) attributes that are intended to be specified once
      per instance they are used (eg. the {class}`~.models.biography.Biography` class is used once per {class}`.Subject`)
    * {class}`.modeling.base.Table` - Tabular data specifies that there should be multiple values for each of the
      fields defined: in particular equal numbers of each of them. This is used for most data collected, as most data
      can be framed in a tabular format.
* {class}`.modeling.base.Group` and {class}`.modeling.base.Node` - Abstract specifications for hierarchical data
  interfaces - a Node is a particular element in a tree/network-like system, and a Group is a collection of Nodes.
  Some transitional work is still being done to generalize Autopilot's former data structures from H5F-specific
  groups and nodes, so for the moment there is some parallel functionality in the {class}`.H5F_Node` and {class}`.H5F_Group`
  classes
* {class}`.modeling.base.Schema` - Specifications for organization of other data structures, for data that isn't expected
  to ever be instantiated in its described form, but for scaffolding building other data structures together. Some transitional
  work is also being done here, eventually moving the Subject Schema to an abstract form ({class}`.Subject_Schema`)
  vs one tied to HDF5 ({class}`.Subject_Structure`)

## {mod}`.models` - The Models Themselves

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

## {mod}`.interfaces` - Bridging to Multiple Representations

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

## {class}`.Subject` - The Main Interface to Data Collection

Subject is the main object that most people will use to interact with their data, and it is used throughout Autopilot
to keep track of individual subjects data, the protocols they are run on, changes in code version over time, etc.

See the main {mod}`.data.subject` module page for further information.

## {mod}`~.data.units` - Explicit SI Unit representation

This too is just a stub, but we will be moving more of our models to using specific SI units when appropriate rather
than using generic `float`s and `int`s with human-readable descriptions of when they are a mL or a ms vs. second or Liter, etc.

## Transition Status

Transitioning to a uniform data modeling system is in progress! The following need to still be transitioned to formal models.

- `Task.PARAMS` and `Task.HARDWARE`
- `Task.PLOT` which should be merged into the TrialData field descriptions
- {mod}`autopilot.prefs` - which currently has a large dictionary of default prefs
- Hardware parameter descriptions - Need to find better way of having models that represent
  class arguments.
- {mod}`.graduation` objects.
- Verious GUI widgets need to use models rather than the zillions of ad-hoc representations:
  - {class}`.Protocol_Wizard`
- {mod}`.utils.plugins` needs its own model to handle dependencies, etc.
- {mod}`.agents` needs models for defining basic agent attributes.

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

