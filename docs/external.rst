external
==========

Autopilot uses two lightly modified versions of existing libraries that are included in the repository as submodules.

* `mlx90640-library <https://github.com/sneakers-the-rat/mlx90640-library/>`_ - driver for the :class:`.hardware.i2c.MLX90640` that correctly sets the baudrate for 64fps capture
* `pigpio <https://github.com/sneakers-the-rat/pigpio>`_ - pigpio that is capable of returning full timestamps rather than system ticks in gpio callbacks.