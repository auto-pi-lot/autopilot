import numpy as np
from autopilot.transform.transforms import Transform

class Add(Transform):
    def __init__(self, value=0, *args, **kwargs):
        super(Add, self).__init__(*args, **kwargs)

        self.value = value

    def process(self, input):
        return input + self.value