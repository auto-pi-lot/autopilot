GUI
=====

GUI Modules used by the :class:`.Terminal` agent.

Each of the submodules contains GUI objects of different types, and will continue to be refined
to allow for extensions by plugins.

* :mod:`.gui.menus` - Widgets and dialogues available from the Terminal menubar
* :mod:`.gui.plots` - Widgets and graphical primitives used for task plots
* :mod:`.gui.widgets` - General purpose widgets that make up the Terminal GUI
* :mod:`.gui.dialog` - Convenience function for popping standard modal/nonmodal dialogues
* :mod:`.gui.styles` - Qt Stylesheets (css-like) for the Terminal

.. automodule:: autopilot.gui
    :members:
    :undoc-members:
    :show-inheritance:

.. toctree::

    menus
    plots/index
    widgets/index
    dialog