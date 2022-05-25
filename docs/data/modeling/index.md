# modeling


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


```{eval-rst}
.. automodule:: autopilot.data.modeling
    :members:
    :undoc-members:
    :show-inheritance:
```

## basic classes

```{eval-rst}
.. automodule:: autopilot.data.modeling.base
    :members:
    :undoc-members:
    :show-inheritance:
```