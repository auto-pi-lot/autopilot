"""
Timeseries transformations, filters, etc.
"""
from collections import deque
from autopilot.transform.transforms import Transform
from scipy import signal
import numpy as np

class Filter_IIR(Transform):
    """
    Simple wrapper around :func:`scipy.signal.iirfilter`

    Creates a streaming filter -- takes in single values, stores them, and uses them to filter future values.

    Args:
        ftype (str): filter type, see ``ftype`` of :func:`scipy.signal.iirfilter` for available filters
        buffer_size (int): number of samples to store when filtering
        coef_type ({'ba', 'sos'}): type of filter coefficients to use (see :func:`scipy.signal.sosfilt` and :func:`scipy.signal.lfilt`)
        axis (int): which axis to filter over? (default: 0 because when passing arrays to filter, want to filter samples over time)
        **kwargs: passed on to :func:`scipy.signal.iirfilter` , eg.

            * ``N`` - filter order
            * ``Wn`` - array or scalar giving critical frequencies
            * ``btype`` - type of band: ``['bandpass', 'lowpass', 'highpass', 'bandstop']``

    Attributes:
        b (np.ndarray): b coefficients of filter
        a (np.ndarray): a coefficients of filter
        buffer (collections.deque): buffer of stored values to filter
    """

    def __init__(self, ftype="butter", buffer_size=256, coef_type='sos', axis=0, *args, **kwargs):
        super(Filter_IIR, self).__init__(*args, **kwargs)

        self.ftype = ftype
        self.coef_type = coef_type
        self.axis = axis
        self.coefs = signal.iirfilter(ftype=self.ftype, output=coef_type, **kwargs)
        self.buffer = deque(maxlen=buffer_size)

    def process(self, input:float):
        """
        Filter the new value based on the values stored in :attr:`.Filter.buffer`

        Args:
            input (float): new value to filter!

        Returns:
            float: the filtered value!
        """

        self.buffer.append(input)
        if self.coef_type == "ba":
            return signal.lfilter(self.coefs[0], self.coefs[1], self.buffer, axis=self.axis)[-1]
        elif self.coef_type == "sos":
            return signal.sosfilt(self.coefs, self.buffer, axis=self.axis)[-1]










