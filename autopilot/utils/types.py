"""
Basic types for a basic types of bbs
"""

from validators.url import url

class URL(str):

    def __new__(cls, content):
        if url(content):
            return str.__new__(cls, content)
        else:
            raise ValueError(f'given string was not a url: {content}')

