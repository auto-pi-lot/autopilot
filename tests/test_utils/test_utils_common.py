from autopilot.utils.common import flatten_dict

def test_flatten_dict():
    """
    Test that flatten dict does indeed flatten dictionaries
    """
    nested_dict = {
        'a':0,
        'b':[1,2],
        'c':{
            'd':3,
            'e':{
                'f':4,
                'g':5.5,
            },
            ('h','i'): 6,
            'j':'klmn'
        }
    }

    flat = flatten_dict(nested_dict)

    assert list(flat.items()) == [
         (('a',), 0),
         (('b',), [1, 2]),
         (('c', 'd'), 3),
         (('c', 'e', 'f'), 4),
         (('c', 'e', 'g'), 5.5),
         (('c', ('h', 'i')), 6),
         (('c', 'j'), 'klmn')
    ]
