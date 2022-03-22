"""
Timeseries transformations, filters, etc.
"""
import typing
from time import time
from collections import deque
from autopilot.transform.transforms import Transform
from scipy import signal
import numpy as np
from copy import copy, deepcopy

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
        coefs (np.ndarray): filter coefficients, depending on :attr:`.coef_type`
        buffer (collections.deque): buffer of stored values to filter
        coef_type (str): type of filter coefficients to use (see :func:`scipy.signal.sosfilt` and :func:`scipy.signal.lfilt`)
        axis (int): which axis to filter over? (default: 0 because when passing arrays to filter, want to filter samples over time)
        ftype (str): filter type, see ``ftype`` of :func:`scipy.signal.iirfilter` for available filters
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


class Gammatone(Transform):
    """
    Single gammatone filter based on :cite:`slaneyEfficientImplementationPattersonHoldsworth1997`

    Thin wrapper around :class:`scipy.signal.gammatone` !! (started rewriting this and realized they had made a legible
    version <3 ty scipy team, additional implementations in the references)

    Examples:

        .. plot::

            import matplotlib.pyplot as plt
            import numpy as np

            from autopilot.transform.timeseries import Gammatone
            gamma_1k = Gammatone(1000, fs=44100)
            gamma_15k = Gammatone(15000, fs=44100)

            signal = (np.random.rand(44100)-0.5)*2
            filt_1k = gamma_1k.process(signal)
            filt_15k = gamma_15k.process(signal)

            fig, ax = plt.subplots(1,3, subplot_kw={'aspect':'equal'})
            ax[0].set_title('White Noise')
            ax[0].specgram(signal, Fs=44100)

            ax[1].set_title('1kHz Gammatone Filter')
            ax[1].axes.yaxis.set_visible(False)
            ax[1].specgram(filt_1k, Fs=44100)

            ax[2].set_title('15kHz Gammatone Filter')
            ax[2].axes.yaxis.set_visible(False)
            ax[2].specgram(filt_15k, Fs=44100)

            plt.tight_layout()
            plt.show()


    References:

        * :cite:`slaneyEfficientImplementationPattersonHoldsworth1997`
        * `Brian2hears implementation <https://github.com/brian-team/brian2hears/blob/131fd6d86c3ec460c45b42ea9c2f3b62c62d0631/brian2hears/filtering/filterbanklibrary.py#L26>`_
        * `detly/gammatone <https://github.com/detly/gammatone>`_
    """
    def __init__(self,
                 freq:float,
                 fs:int,
                 ftype:str="iir",
                 filtfilt:bool=True,
                 order:int=None,
                 numtaps:int=None,
                 axis:int=-1,
                 **kwargs):
        """
        Args:
            freq (float): Center frequency of the filter in Hz
            fs (int): Sampling rate of the signal to process
            ftype (str): Type of filter to return from :func:`scipy.signal.gammatone`
            filtfilt (bool): If ``True`` (default), use :func:`scipy.signal.filtfilt`, else use :func:`scipy.signal.lfilt`
            order (int): From scipy docs: The order of the filter. Only used when ``ftype='fir'``.
                Default is 4 to model the human auditory system. Must be between
                0 and 24.
            numtaps (int): From scipy docs: Length of the filter. Only used when ``ftype='fir'``.
                Default is ``fs*0.015`` if `fs` is greater than 1000,
                15 if `fs` is less than or equal to 1000.
            axis (int): Axis of input signal to apply filter over (default ``-1``)
            **kwargs: passed to :func:`scipy.signal.filtfilt` or :func:`scipy.signal.lfilt`
        """

        self._filter_a = None
        self._filter_b = None

        self.freq = float(freq)
        self.fs = int(fs)
        self.ftype = str(ftype)
        self.axis = int(axis)
        self.filtfilt = bool(filtfilt)

        self.order = order
        self.numtaps = numtaps
        self.kwargs = kwargs

        self._init_arrays()

    def _init_arrays(self):
        self._filter_b, self._filter_a = signal.gammatone(
            self.freq, self.ftype, self.order, self.numtaps, self.fs
        )

    def process(self, input:typing.Union[np.ndarray, list]) -> np.ndarray:
        if self.filtfilt:
            return signal.filtfilt(self._filter_b, self._filter_a, input,
                                   axis=self.axis, **self.kwargs)
        else:
            return signal.lfilter(self._filter_b, self._filter_a, input,
                                  axis=self.axis, **self.kwargs)







class Kalman(Transform):
    """
    Kalman filter!!!!!

    Adapted from https://github.com/rlabbe/filterpy/blob/master/filterpy/kalman/kalman_filter.py
    simplified and optimized lovingly <3

    Each of the arrays is named with its canonical letter and a short description, (eg. the x_state
    vector ``x_state`` is ``self.x_state``

    Args:
        dim_state (int): Dimensions of the state vector
        dim_measurement (int): Dimensions of the measurement vector
        dim_control (int): Dimensions of the control vector

    Attributes:
        x_state (:class:`numpy.ndarray`): Current state vector
        P_cov (:class:`numpy.ndarray`): Uncertainty Covariance
        Q_proc_var (:class:`numpy.ndarray`): Process Uncertainty
        B_control (:class:`numpy.ndarray`): Control transition matrix
        F_state_trans (:class:`numpy.ndarray`): State transition matrix
        H_measure (:class:`numpy.ndarray`): Measurement function
        R_measure_var (:class:`numpy.ndarray`): Measurement uncertainty
        M_proc_measure_xcor (:class:`numpy.ndarray`): process-measurement cross correlation
        z_measure (:class:`numpy.ndarray`):
        K (:class:`numpy.ndarray`): Kalman gain
        y (:class:`numpy.ndarray`):
        S (:class:`numpy.ndarray`): System uncertainty
        SI (:class:`numpy.ndarray`): Inverse system uncertainty
        x_prior (:class:`numpy.ndarray`): State prior
        P_prior (:class:`numpy.ndarray`): Uncertainty prior
        x_post (:class:`numpy.ndarray`): State posterior probability
        P_post (:class:`numpy.ndarray`): Uncertainty posterior probability

    References:
        Roger Labbe. "Kalman and Bayesian Filters in Python" - https://github.com/rlabbe/Kalman-and-Bayesian-Filters-in-Python
        Roger Labbe. "FilterPy" - https://github.com/rlabbe/filterpy
    """

    def __init__(self, dim_state: int, dim_measurement: int = None, dim_control: int=0,
                 *args, **kwargs):
        super(Kalman, self).__init__(*args, **kwargs)

        self.dim_state = dim_state # type: int
        if dim_measurement is None:
            self.dim_measurement = self.dim_state # type: int
        else:
            self.dim_measurement = dim_measurement # type: int
        self.dim_control = dim_control # type: int

        # initialize arrays!!!
        self._init_arrays()


    def _init_arrays(self, state=None):
        """
        Initialize the arrays!
        """

        # State arrays
        if state is not None:
            # TODO: check it's the right shape
            self.x_state = state
        else:
            self.x_state = np.zeros((self.dim_state, 1))

        # initialize kalman arrays
        self.P_cov               = np.eye(self.dim_state)                           # uncertainty covariance
        self.Q_proc_var          = np.eye(self.dim_state)                           # process uncertainty
        self.B_control           = np.eye(self.dim_control)                         # control transition matrix
        self.F_state_trans       = np.eye(self.dim_state)                           # x_state transition matrix
        if self.dim_state == self.dim_measurement:
            self.H_measure = np.eye(self.dim_measurement)
        else:
            self.H_measure           = np.zeros((self.dim_measurement, self.dim_state)) # measurement function
        self.R_measure_var       = np.eye(self.dim_measurement)                     # measurement uncertainty
        self._alpha_sq           = 1.                                               # fading memory control
        self.M_proc_measure_xcor = np.zeros((self.dim_state, self.dim_measurement)) # process-measurement cross correlation
        self.z_measure           = np.array([[None] * self.dim_measurement]).T

        # gain and residual are computed during the innovation step. We
        # save them so that in case you want to inspect them for various
        # purposes
        self.K = np.zeros((self.dim_state, self.dim_measurement)) # kalman gain
        self.y = np.zeros((self.dim_measurement, 1))
        self.S = np.zeros((self.dim_measurement, self.dim_measurement)) # system uncertainty
        self.SI = np.zeros((self.dim_measurement, self.dim_measurement)) # inverse system uncertainty

        # identity matrix. Do not alter this.
        self._I = np.eye(self.dim_state)

        # these will always be a copy of x_state,P_cov after predict() is called
        self.x_prior = self.x_state.copy()
        self.P_prior = self.P_cov.copy()

        # these will always be a copy of x_state,P_cov after update() is called
        self.x_post = self.x_state.copy()
        self.P_post = self.P_cov.copy()


    def predict(self, u=None, B=None, F=None, Q=None):
        """
        Predict next x_state (prior) using the Kalman filter x_state propagation
        equations.

        Update our state and uncertainty priors, :attr:`.x_prior` and :attr:`.P_prior`

        Parameters
        ----------

        u : np.array, default 0
            Optional control vector.

        B : np.array(dim_state, dim_u), or None
            Optional control transition matrix; a value of None
            will cause the filter to use `self.B_control`.

        F : np.array(dim_state, dim_state), or None
            Optional x_state transition matrix; a value of None
            will cause the filter to use `self.F_state_trans`.

        Q : np.array(dim_state, dim_state), scalar, or None
            Optional process noise matrix; a value of None will cause the
            filter to use `self.Q_proc_var`.
        """

        if B is None:
            B = self.B_control
        if F is None:
            F = self.F_state_trans
        if Q is None:
            Q = self.Q_proc_var
        elif np.isscalar(Q):
            Q = np.eye(self.dim_state) * Q



        # x_state = Fx + Bu
        if B is not None and u is not None:
            # make sure control vector is column
            u = np.atleast_2d(u)
            if u.shape[1] > u.shape[0]:
                u = u.T
            self.x_state = np.dot(F, self.x_state) + np.dot(B, u)
        else:
            self.x_state = np.dot(F, self.x_state)

        # P_cov = FPF' + Q_proc_var
        self.P_cov = self._alpha_sq * np.dot(np.dot(F, self.P_cov), F.T) + Q

        # save prior
        np.copyto(self.x_prior, self.x_state)
        np.copyto(self.P_prior, self.P_cov)


    def update(self, z:np.ndarray, R=None, H=None) -> np.ndarray:
        """
        Add a new measurement (z_measure) to the Kalman filter.

        If z_measure is None, nothing is computed. However, x_post and P_post are
        updated with the prior (x_prior, P_prior), and self.z_measure is set to None.

        Args:
            z (:class:`numpy.ndarray`): measurement for this update. z_measure can be a scalar if dim_measurement is 1,
                otherwise it must be convertible to a column vector.

                If you pass in a value of H_measure, z_measure must be a column vector the
                of the correct size.
            R (:class:`numpy.ndarray`, int, None): Optionally provide R_measure_var to override the measurement noise for this
                one call, otherwise  self.R_measure_var will be used.
            H (:class:`numpy.ndarray`, None): Optionally provide H_measure to override the measurement function for this
                one call, otherwise self.H_measure will be used.
        """

        # set to None to force recompute
        self._log_likelihood = None
        self._likelihood = None
        self._mahalanobis = None

        if z is None:
            self.z_measure = np.array([[None] * self.dim_measurement]).T
            np.copyto(self.x_post, self.x_state)
            np.copyto(self.P_post, self.P_cov)
            self.y = np.zeros((self.dim_measurement, 1))
            return

        if R is None:
            R = self.R_measure_var
        elif np.isscalar(R):
            R = np.eye(self.dim_measurement) * R

        if H is None:
            z = self._reshape_z(z, self.dim_measurement, self.x_state.ndim)
            H = self.H_measure

        # y = z_measure - Hx
        # error (residual) between measurement and prediction
        self.y = z - np.dot(H, self.x_state)

        # common subexpression for speed
        PHT = np.dot(self.P_cov, H.T)

        # S = HPH' + R_measure_var
        # project system uncertainty into measurement space
        self.S = np.dot(H, PHT) + R
        self.SI = np.linalg.inv(self.S)
        # K = PH'inv(S)
        # map system uncertainty into kalman gain
        self.K = np.dot(PHT, self.SI)

        # x_state = x_state + Ky
        # predict new x_state with residual scaled by the kalman gain
        self.x_state = self.x_state + np.dot(self.K, self.y)

        # P_cov = (I-KH)P_cov(I-KH)' + KRK'
        # This is more numerically stable
        # and works for non-optimal K vs the equation
        # P_cov = (I-KH)P_cov usually seen in the literature.

        I_KH = self._I - np.dot(self.K, H)
        self.P_cov = np.dot(np.dot(I_KH, self.P_cov), I_KH.T) + np.dot(np.dot(self.K, R), self.K.T)

        # save measurement and posterior x_state
        np.copyto(self.z_measure, z)
        np.copyto(self.x_post, self.x_state)
        np.copyto(self.P_post, self.P_cov)
        return self.x_state

    def _reshape_z(self, z, dim_z, ndim):
        """ ensure z is a (dim_z, 1) shaped vector"""

        z = np.atleast_2d(z)
        if z.shape[1] == dim_z:
            z = z.T

        if z.shape != (dim_z, 1):
            raise ValueError('z (shape {}) must be convertible to shape ({}, 1)'.format(z.shape, dim_z))

        if ndim == 1:
            z = z[:, 0]

        if ndim == 0:
            z = z[0, 0]

        return z

    def process(self, z, **kwargs):
        """
        Call predict and update, passing the relevant kwargs

        Args:
            z ():
            **kwargs ():

        Returns:
            np.ndarray: self.x_state
        """

        # prepare args for predict and call
        predict_kwargs = {k:kwargs.get(k, None) for k in ("u", "B", "F", "Q")}
        self.predict(**predict_kwargs)

        # same thing for update
        update_kwargs = {k: kwargs.get(k, None) for k in ('R', 'H')}
        return self.update(z, **update_kwargs)








    def residual_of(self, z):
        """
        Returns the residual for the given measurement (z_measure). Does not alter
        the x_state of the filter.
        """
        return z - dot(self.H_measure, self.x_prior)

    def measurement_of_state(self, x):
        """
        Helper function that converts a x_state into a measurement.

        Parameters
        ----------

        x : np.array
            kalman x_state vector

        Returns
        -------

        z_measure : (dim_measurement, 1): array_like
            measurement for this update. z_measure can be a scalar if dim_measurement is 1,
            otherwise it must be convertible to a column vector.
        """

        return dot(self.H_measure, x)

    @property
    def alpha(self):
        """
        Fading memory setting. 1.0 gives the normal Kalman filter, and
        values slightly larger than 1.0 (such as 1.02) give a fading
        memory effect - previous measurements have less influence on the
        filter's estimates. This formulation of the Fading memory filter
        (there are many) is due to Dan Simon [1]_.
        """
        return self._alpha_sq**.5

    @alpha.setter
    def alpha(self, value):
        if not np.isscalar(value) or value < 1:
            raise ValueError('alpha must be a float greater than 1')

        self._alpha_sq = value**2



class Integrate(Transform):
    def __init__(self, decay=1, dt_scale = False, *args, **kwargs):
        super(Integrate, self).__init__(*args, **kwargs)
        self._value = None
        self.decay = decay
        self.dt_scale = dt_scale

        self.last_time = None

    def process(self, input):
        if self._value is None:
            self._value = input
            self.last_time = time()

        else:
            if self.dt_scale:
                new_time = time()
                input *= new_time-self.last_time
                self.last_time = new_time

            self._value += input
            self._value *= self.decay

        return self._value.copy()


















