from docutils.parsers import rst



import os
from subprocess import call

from docutils import nodes
from docutils.parsers.rst import directives

try:
    from sphinx.util.compat import Directive
except ImportError:
    from docutils.parsers.rst import Directive  # pylint: disable=C0412

try:
    from PIL import Image as IMAGE
except ImportError:  # pragma: no cover
    IMAGE = None

import pdb

# debugging with IPython
# ~ try:
# ~ from IPython import embed
# ~ except ImportError as e:
# ~ pass


class UMLGenerateDirective(Directive):
    """UML directive to generate a pyreverse diagram

    Modified to use python sys.path
    """

    required_arguments = 1
    optional_arguments = 2
    has_content = False
    DIR_NAME = "uml_images"
    # a list of modules which have been parsed by pyreverse
    generated_modules = []

    def _validate(self):
        """ Validates that the RST parameters are valid """
        valid_flags = {":classes:", ":packages:"}
        unkown_arguments = set(self.arguments[1:]) - valid_flags
        if unkown_arguments:
            raise ValueError(
                "invalid flags encountered: {0}. Must be one of {1}".format(
                    unkown_arguments, valid_flags
                )
            )

    def run(self):
        # pdb.set_trace()
        doc = self.state.document
        env = doc.settings.env
        # the top-level source directory
        base_dir = env.srcdir
        # the directory of the file calling the directive
        src_dir = os.path.dirname(doc.current_source)
        uml_dir = os.path.abspath(os.path.join(base_dir, self.DIR_NAME))

        if not os.path.exists(uml_dir):
            os.mkdir(uml_dir)

        env.uml_dir = uml_dir
        module_name = self.arguments[0]

        self._validate()

        if module_name not in self.generated_modules:
            print(
                call(
                    ["pyreverse", "-o", "png", "-p", module_name, module_name],
                    cwd=uml_dir, env=os.environ.copy()
                )
            )
            # avoid double-generating
            self.generated_modules.append(module_name)

        res = []
        for arg in self.arguments[1:]:
            img_name = arg.strip(":")
            res.append(self.generate_img(img_name, module_name, base_dir, src_dir))

        return res

    def generate_img(self, img_name, module_name, base_dir, src_dir):
        """ Resizes the image and returns a Sphinx image """
        path_from_base = os.path.join(self.DIR_NAME, "{1}_{0}.png").format(
            module_name, img_name
        )
        # use relpath to get sub-directory of the main 'source' location
        src_base = os.path.relpath(base_dir, start=src_dir)
        uri = directives.uri(os.path.join(src_base, path_from_base))
        scale = 100
        max_width = 1000
        # if IMAGE:
        #     i = IMAGE.open(os.path.join(base_dir, path_from_base))
        #     image_width = i.size[0]
        #     if image_width > max_width:
        #         scale = max_width * scale / image_width
        return nodes.image(uri=uri, scale=scale)
