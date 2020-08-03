from docutils.parsers import rst



import os
from subprocess import call
import sys

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

class RoadmapNode(nodes.General, nodes.Element):
    pass

class RoadmapDirective(Directive):
    """

    With respect to http://www.xavierdupre.fr/blog/2015-06-07_nojs.html

    """
    # priority, discussion board link
    # required_arguments = 3
    # optional_arguments = 0
    final_argument_whitespace = True
    option_spec = {
        'title'   : directives.unchanged,
        'priority': directives.unchanged,
        'dblink'  : directives.unchanged
    }
    has_content = True
    add_index = True

    roadmap_class = RoadmapNode

    def run(self):
        # options given to the directive
        options = self.options
        #
        # ## make section
        # # make id
        idb = nodes.make_id('roadmap-'+options['title'])
        section = nodes.section(ids=[idb], classes=['roadmap-'+options['priority']])
        #
        # # add title
        # header = nodes.section(ids=[nodes.make_id('roadmap-title-'+options['title'])],
        #                        classes=['roadmap-header-container'])

        header = nodes.inline()

        title = nodes.title(options['title'],options['title'], classes=['roadmap-title', 'roadmap-priority-'+options['priority']])

        # link = nodes.raw()
        link_str = '<span><a href="'+options['dblink']+'" class="roadmap-dblink">priority: '+options['priority']+' | discuss>></a></span>'
        link = nodes.raw(link_str,link_str, format='html')


        #
        # # add content
        par = nodes.paragraph()
        self.state.nested_parse(self.content, self.content_offset, par)
        #
        # node = self.__class__.roadmap_class()
        # node += section
        # node += par

        # node = nodes.paragraph()
        node = section


        title += link
        node += title
        # node += link

        node += header
        # node += link
        node += par
        return [node]



def visit_roadmap_node(self, node):
    self.visit_admonition(node)

def depart_roadmap_node(self, node):
    self.depart_admonition(node)


def setup(app):

    app.add_node(RoadmapNode)
    app.add_directive('roadmap', RoadmapDirective)