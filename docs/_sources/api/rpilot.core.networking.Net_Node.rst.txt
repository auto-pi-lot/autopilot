Net_Node
========

.. currentmodule:: rpilot.core.networking

.. autoclass:: Net_Node
   :show-inheritance:

   .. rubric:: Attributes Summary

   .. autosummary::

      ~Net_Node.context
      ~Net_Node.do_logging
      ~Net_Node.id
      ~Net_Node.listens
      ~Net_Node.log_formatter
      ~Net_Node.log_handler
      ~Net_Node.logger
      ~Net_Node.loop
      ~Net_Node.loop_thread
      ~Net_Node.outbox
      ~Net_Node.port
      ~Net_Node.repeat_interval
      ~Net_Node.sock
      ~Net_Node.timers
      ~Net_Node.upstream

   .. rubric:: Methods Summary

   .. autosummary::

      ~Net_Node.handle_listen
      ~Net_Node.init_logging
      ~Net_Node.init_networking
      ~Net_Node.l_confirm
      ~Net_Node.prepare_message
      ~Net_Node.repeat
      ~Net_Node.send
      ~Net_Node.threaded_loop

   .. rubric:: Attributes Documentation

   .. autoattribute:: context
   .. autoattribute:: do_logging
   .. autoattribute:: id
   .. autoattribute:: listens
   .. autoattribute:: log_formatter
   .. autoattribute:: log_handler
   .. autoattribute:: logger
   .. autoattribute:: loop
   .. autoattribute:: loop_thread
   .. autoattribute:: outbox
   .. autoattribute:: port
   .. autoattribute:: repeat_interval
   .. autoattribute:: sock
   .. autoattribute:: timers
   .. autoattribute:: upstream

   .. rubric:: Methods Documentation

   .. automethod:: handle_listen
   .. automethod:: init_logging
   .. automethod:: init_networking
   .. automethod:: l_confirm
   .. automethod:: prepare_message
   .. automethod:: repeat
   .. automethod:: send
   .. automethod:: threaded_loop
