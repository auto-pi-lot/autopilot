import numpy as np
from scipy.spatial import distance

from autopilot.transform.transforms import Transform


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