"""
Data transformations.

Experimental module.

Reusable transformations from one representation of data to another.
eg. converting frames of a video to locations of objects,
or locations of objects to area labels

.. todo::

    This is a preliminary module and it purely synchronous at the moment. It will be expanded to ...
    * support multiple asynchronous processing rhythms
    * support automatic value coercion

    The following design features need to be added
    * recursion checks -- make sure a child hasn't already been added to a processing chain.
"""
# import cv2


# class Img2Loc_binarymass(object):
#     METHODS = ('largest')
#     def __init__(self, dark_object=True, method="largest"):
#         """
#
#         Args:
#             dark_object (bool): Is the object dark on a light background (default) or light on a dark background?
#             method (str): one of "largest" (find the largest object in each frame)
#         """
#
#         self.dark_object = dark_object
#
#         if method in self.METHODS:
#             self.method = method
#             self.method_fn = getattr(self, self.method)
#         else:
#             Exception("Unknown method, must be one of {}, got : {}".format(self.METHODS, method))
#
#     def __call__(self, *args, **kwargs):
#         return self.method_fn(*args, **kwargs)
#
#     def largest(self, input, return_image=False):
#
#         # TODO: Check if rgb or gray, convert if so
#
#         # blur and binarize with otsu's method
#         blur = cv2.GaussianBlur(input, (3,3),0)
#         ret, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU)
#
#         # get connected components
#         n_components, labels, stats, centroids = cv2.connectedComponentsWithStats(thresh)
#
#         # find largest component
#         largest_ind = np.argmax(stats[:,-1])
#
#         # return centroid of largest object
#         if return_image:
#             return centroids[largest_ind], thresh
#         else:
#             return centroids[largest_ind]
#





#
# class Transform(object):
#     """
#     https://blog.usejournal.com/playing-with-inheritance-in-python-73ea4f3b669e
#     """
#
#     def __new__(cls, *args, **kwargs):
#         """
#         Choose a flavor of the particular transform.
#         Flavors should be named This2That_Flavor.
#
#         Args:
#             *args ():
#             **kwargs ():
#
#         Returns:
#
#         """
#         our_name = cls.__name__
#         print(cls)
#         print(our_name)
#
#         flavor = kwargs.get("flavor")
#
#         search_string = "_".join([our_name, flavor])
#
#         # find if there are any matches in our subclasses
#         if cls in Transform.__subclasses__():
#             print('getting subclass')
#             for i in cls.__subclasses__():
#                 if i.__name__ == search_string:
#                     print(i)
#                     #return super(cls).__new__(i)
#                     return i
#         else:
#             # otherwise we are the subclass
#             return super(cls).__new__(cls, *args, **kwargs)
#
#
#
#
# class Img2Loc(Transform):
#     def __init__(self, *args, **kwargs):
#         print('Img2Loc class')
#
# class Img2Loc_binarymass(Img2Loc):
#     def __init__(self, *args, **kwargs):
#         super(Img2Loc_binarymass, self).__init__()
#         print('binarymass class')
#

