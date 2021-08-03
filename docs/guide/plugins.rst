.. _guide_plugins:

Plugins & The Wiki
*********************

Autopilot is integrated with a `semantic wiki <https://www.semantic-mediawiki.org/wiki/Semantic_MediaWiki>`_, a
powerful tool that merges human-readable text with computer-readable structured information, and blurs the lines between
the two in the empowering interface of a wiki that allows anyone to edit it. The autopilot wiki is available at:

https://wiki.auto-pi-lot.com

In addition to a system for storing, discussing, and knitting together a library of technical knowledge,
the wiki is used to manage Autopilot's plugin system. The integrated plugin/wiki system is designed to

* make it easier to extend and hack existing autopilot classes, particularly Hardware and Task classes, without needing to
  modify any of the core library code
* make it easier to share code across multiple rigs-in-use by allowing you to specify the name of the plugin on the
  autopilot wiki so you don't need to manually keep the code updated on all computers it's used on
* make a gentler scaffold between using and contributing to the library -- by developing in a plugin folder, your
  code is likely very close, if it isn't already, ready to integrate back into the main autopilot library. In the meantime,
  anyone that is curious
* make it possible to encode semantic metadata about the plugin so that others can discover, modify, and improve on it.
  eg. your plugin might control an array of stepper motors, and from that someone can cherrypick code to run a single one,
  even if it wasn't designed to do that.
* decentralize the development of autopilot, allowing anyone to extend it in arbitrary ways without needing to go through
  a fork/merge process that is ultimately subject to the whims of the maintainer(s) (me 😈), or even an approval process
  to submit or categorize plugins. Autopilot seeks to be as noncoercive as possible while embracing and giving tools
  to support the heterogeneity of its use.
* make it trivial for users to not only contribute *plugins* but design new *types of plugin-like public interfaces*.
  For example, if you wanted to design an interface where users can submit the parameters they use for different tasks,
  one would only need to build the relevant semantic mediawiki template and form, and then program the API calls
  to the wiki to index them.
* ``todo`` --- fully realize the vision of decentralized development by allowing plugins to replace existing core autopilot modules...

Plugins
========

Plugins are now the recommended way to use Autopilot! They make very few assumptions about the structure of your code,
so they can be used like familiar script-based experimental tools, but they also encourage the development of modular code that
can easily be used by others and cumulatively contribute to a shared body of tools.

Using plugins is simple! Anything inside of the directory indicated by ``prefs.get('PLUGINDIR')`` is a plugin! Plugins
provide objects that inherit from Autopilot classes supported by an entry in :data:`.registry.REGISTRIES` .

For example, we want to write a task that uses some special hardware that we need. We could start by making a directory
within ``'PLUGINDIR'`` like this::

    plugins
    ├── my-autopilot-plugin
    │   ├── README.md
    │   ├── test_hardware.py
    │   └── test_task.py

Where within ``test_hardware.py`` you define some custom hardware


Registries
==========


The Wiki API
============

Plugins on the Wiki
====================