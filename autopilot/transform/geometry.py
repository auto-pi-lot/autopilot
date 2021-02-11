import typing
from time import time

import numpy as np
from scipy.spatial import distance

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
    Transform accelerometer and gyroscope measurements (eg from :class:`.hardware.i2c.I2C_9DOF` )
    to absolute orientation

    Uses a :class:`.timeseries.Kalman` filter, and implements :cite:`patonisFusionMethodCombining2018a`
    """

    def __init__(self, *args, **kwargs):
        super(IMU_Orientation, self).__init__(*args, **kwargs)

        self._last_update = None
        self.kalman = Kalman(dim_state=2, dim_measurement=2, dim_control=2)

    def process(self, accelgyro:typing.Tuple[np.ndarray]):
        """

        Args:
            accelgyro (tuple): tuple of (orientation, gyro) readings such that orientation = [roll, pitch]
                (as from :meth:`.I2C_9DOF.rotation` ) and gyro = [x, y, z] readings from a gyroscope

        Returns:
            :class:`numpy.ndarray`: filtered [roll, pitch] calculations
        """

        # TODO: Don't assume that we're fed samples instantatneously -- ie. once data representations are stable, need to accept a timestamp here rather than making one
        if self._last_update is None:
            # first time through don't have dt to scale gyro by
            ret = self.kalman.process(accelgyro[0])
            self._last_update = time()

        else:
            update_time = time()
            dt = update_time-self._last_update
            self._last_update = update_time
            self.kalman.predict(u=accelgyro[1][0:2]*dt)
            ret = self.kalman.update(accelgyro[0])

        return ret



