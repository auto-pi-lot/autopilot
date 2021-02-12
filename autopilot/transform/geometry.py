import typing
from time import time

import numpy as np
from scipy.spatial import distance
from scipy.spatial.transform import Rotation as R

from autopilot.transform.transforms import Transform
from autopilot.transform.timeseries import Kalman


class Distance(Transform):
    """
    Given an n_samples x n_dimensions array, compute pairwise or mean distances
    """
    format_in = {'type': np.ndarray}
    format_out = {'type': np.ndarray}

    def __init__(self,
                 pairwise: bool=False,
                 n_dim: int = 2,
                 metric: str='euclidean',
                 squareform: bool=True,
                 *args, **kwargs):
        """

        Args:
            pairwise (bool): If False (default), return mean distance. if True, return all distances
            n_dim (int): number of dimensions (input array will be filtered like ``input[:,0:n_dim]``
            metric (str): any metric acceptable to :func:`scipy.spatial.distance.pdist
            squareform (bool): if pairwise is True, if True return square distance matrix, otherwise return compressed distance matrix (dist(X[i], X[j] = y[i*j])
            *args:
            **kwargs:
        """

        super(Distance, self).__init__(*args, **kwargs)

        self.pairwise = pairwise
        self.n_dim = n_dim
        self.metric = metric
        self.squareform = squareform

    def process(self, input: np.ndarray):

        # filter to input_dimension
        input = input[:,0:self.n_dim]

        output = distance.pdist(input, metric=self.metric)

        if self.pairwise:
            if self.squareform:
                output = distance.squareform(output)
        else:
            output = np.mean(output)

        return output


class Angle(Transform):
    """
    Get angle between line formed by two points and horizontal axis
    """

    format_in = {'type': np.ndarray}
    format_out = {'type': float}

    def __init__(self, abs=True, degrees=True, *args, **kwargs):
        super(Angle, self).__init__(*args, **kwargs)
        self.abs = abs
        self.degrees = degrees

    def process(self, input):
        angle = np.arctan2(input[1][1]-input[0][1], input[1][0]-input[0][0])
        if self.abs:
            angle += np.pi
        if self.degrees:
            angle = angle*(180/np.pi)
        return angle


class IMU_Orientation(Transform):
    """
    Compute absolute orientation (roll, pitch) from accelerometer and gyroscope measurements
    (eg from :class:`.hardware.i2c.I2C_9DOF` )

    Uses a :class:`.timeseries.Kalman` filter, and implements :cite:`patonisFusionMethodCombining2018a` to fuse
    the sensors

    Can be used with accelerometer data only, or with combined accelerometer/gyroscope data for
    greater accuracy

    Arguments:
        invert_gyro (bool): if the gyroscope's orientation is inverted from accelerometer measurement, multiply
            gyro readings by -1 before using
        use_kalman (bool): Whether to use kalman filtering (True, default), or return raw trigonometric
            transformation of accelerometer readings (if provided, gyroscope readings will be ignored)

    Attributes:
        kalman (:class:`.transform.timeseries.Kalman`): If ``use_kalman == True`` , the Kalman Filter.

    References:
        :cite:`patonisFusionMethodCombining2018a`
        :cite:`abyarjooImplementingSensorFusion2015`
    """

    def __init__(self, use_kalman:bool = True, invert_gyro:bool=False, *args, **kwargs):
        super(IMU_Orientation, self).__init__(*args, **kwargs)

        self.invert_gyro = invert_gyro # type: bool
        self._last_update = None # type: typing.Optional[float]
        self._dt = 0 # type: float
        # preallocate orientation array for filtered values
        self.orientation = np.zeros((2), dtype=float) # type: np.ndarray
        # and for unfiltered values so they aren't ambiguous
        self._orientation = np.zeros((2), dtype=float)  # type: np.ndarray

        self.kalman = None # type: typing.Optional[Kalman]
        if use_kalman:
            self.kalman = Kalman(dim_state=2, dim_measurement=2, dim_control=2)  # type: typing.Optional[Kalman]

    def process(self, accelgyro:typing.Union[typing.Tuple[np.ndarray, np.ndarray], np.ndarray]) -> np.ndarray:
        """

        Args:
            accelgyro (tuple, :class:`numpy.ndarray`): tuple of (accelerometer[x,y,z], gyro[x,y,z]) readings as arrays, or
                an array of just accelerometer[x,y,z]

        Returns:
            :class:`numpy.ndarray`: filtered [roll, pitch] calculations in degrees
        """
        # check what we were given...
        if isinstance(accelgyro, (tuple, list)) and len(accelgyro) == 2:
            # combined accelerometer and gyroscope readings
            accel, gyro = accelgyro
        elif isinstance(accelgyro, np.ndarray) and np.squeeze(accelgyro).shape[0] == 3:
            # just accelerometer readings
            accel = accelgyro
            gyro = None
        else:
            # idk lol
            self.logger.exception(f'Need input to be a tuple of accelerometer and gyroscope readings, or an array of accelerometer readings. got {accelgyro}')
            return

        # convert accelerometer readings to roll and pitch
        pitch = 180*np.arctan2(accel[0], np.sqrt(accel[1]**2 + accel[2]**2))/np.pi
        roll = 180*np.arctan2(accel[1], np.sqrt(accel[0]**2 + accel[2]**2))/np.pi


        if self.kalman is None:
            # store orientations in external attribute if not using kalman filter
            self.orientation[:] = (roll, pitch)
            return self.orientation.copy()
        else:
            # if using kalman filter, use private array to store raw orientation
            self._orientation[:] = (roll, pitch)



        # TODO: Don't assume that we're fed samples instantatneously -- ie. once data representations are stable, need to accept a timestamp here rather than making one
        if self._last_update is None or gyro is None:
            # first time through don't have dt to scale gyro by
            self.orientation[:] = np.squeeze(self.kalman.process(self._orientation))
            self._last_update = time()

        else:
            if self.invert_gyro:
                gyro *= -1

            # get dt for time since last update
            update_time = time()
            self._dt = update_time-self._last_update
            self._last_update = update_time

            if self._dt>1:
                # if it's been really long, the gyro read is pretty much useless and will give ridiculous reads
                self.orientation[:] = np.squeeze(self.kalman.process(self._orientation))
            else:
                # run predict and update stages separately to incorporate gyro
                self.kalman.predict(u=gyro[0:2]*self._dt)
                self.orientation[:] = np.squeeze(self.kalman.update(self._orientation))

        return self.orientation.copy()


class Rotate(Transform):
    """
    Rotate in 3 dimensions using :class:`scipy.spatial.transform.Rotation`

    Args:
        rotation_type (str): Format of rotation input, must be one available to the :class:`~scipy.spatial.transform.Rotation` class
            (but currently only euler angles are supported)
    """

    def __init__(self, rotation_type="euler", *args, **kwargs):
        super(Rotate, self).__init__(*args, **kwargs)


