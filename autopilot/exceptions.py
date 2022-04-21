"""
Custom warnings and exceptions for better testing and diagnosis!
"""

import warnings

class DefaultPrefWarning(UserWarning):
    """
    Warn that a default pref value is being accessed
    """

