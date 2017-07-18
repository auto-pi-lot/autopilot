.. highlight:: python

The state-transition matrix
===========================

The state-transition matrix (sometimes called the *state matrix*), defines the sequence of events the machine will follow given actions generated externally (by the subject) or internally (e.g., timers).

In TASKontrol, the transition matrix is represented as a list of lists

.. code-block:: python

    #                Ci  Co  Li  Lo  Ri  Ro  Tup
    stateMatrix = [ [ 0,  0,  0,  0,  0,  0,  1 ] ,
                    [ 2,  1,  1,  1,  1,  1,  2 ] ,
                    [ 2,  2,  1,  2,  2,  2,  1 ] ]
