from PySide6 import QtWidgets

from autopilot.utils.loggers import init_logger
from autopilot.utils import registry, plugins


class Plugins(QtWidgets.QDialog):
    """
    Dialog window that allows plugins to be viewed and installed.

    Works by querying the `wiki <https://wiki.auto-pi-lot.com>`_ ,
    find anything in the category ``Autopilot Plugins`` , clone the
    related repo, and reload plugins.

    At the moment this widget is a proof of concept and will be made functional
    asap :)
    """

    def __init__(self):
        super(Plugins, self).__init__()

        self.logger = init_logger(self)
        self.plugins = {}

        self.init_ui()
        self.list_plugins()

    def init_ui(self):
        self.layout = QtWidgets.QGridLayout()

        # top combobox for selecting plugin type
        self.plugin_type = QtWidgets.QComboBox()
        self.plugin_type.addItem("Plugin Type")
        self.plugin_type.addItem('All')
        for ptype in registry.REGISTRIES:
            self.plugin_type.addItem(str(ptype.name).capitalize())
        self.plugin_type.currentIndexChanged.connect(self.select_plugin_type)

        # left panel for listing plugins
        self.plugin_list = QtWidgets.QListWidget()
        self.plugin_list.currentItemChanged.connect(self.select_plugin)
        self.plugin_details = QtWidgets.QFormLayout()

        self.plugin_list.setMinimumWidth(200)
        self.plugin_list.setMinimumHeight(600)

        self.status = QtWidgets.QLabel()
        self.download_button = QtWidgets.QPushButton('Download')
        self.download_button.setDisabled(True)

        # --------------------------------------------------
        # layout

        self.layout.addWidget(self.plugin_type, 0, 0, 1, 2)
        self.layout.addWidget(self.plugin_list, 1, 0, 1, 1)
        self.layout.addLayout(self.plugin_details, 1, 1, 1, 1)
        self.layout.addWidget(self.status, 2, 0, 1, 1)
        self.layout.addWidget(self.download_button, 2, 1, 1, 1)

        self.layout.setRowStretch(0, 1)
        self.layout.setRowStretch(1, 10)
        self.layout.setRowStretch(2, 1)

        self.setLayout(self.layout)

    def list_plugins(self):
        self.status.setText('Querying wiki for plugin list...')

        self.plugins = plugins.list_wiki_plugins()
        self.logger.info(f'got plugins: {self.plugins}')

        self.status.setText(f'Got {len(self.plugins)} plugins')

    def download_plugin(self):
        pass

    def select_plugin_type(self):
        nowtype = self.plugin_type.currentText()


        if nowtype == "Plugin Type":
            return
        elif nowtype == "All":
            plugins = self.plugins.copy()
        else:
            plugins = [plug for plug in self.plugins if plug['Is Autopilot Plugin Type'] == nowtype]

        self.logger.debug(f'showing plugin type {nowtype}, matched {plugins}')

        self.plugin_list.clear()
        for plugin in plugins:
            self.plugin_list.addItem(plugin['name'])

    def select_plugin(self):
        if self.plugin_list.currentItem() is None:
            self.download_button.setDisabled(True)
        else:
            self.download_button.setDisabled(False)

        plugin_name = self.plugin_list.currentItem().text()
        plugin = [p for p in self.plugins if p['name'] == plugin_name][0]

        while self.plugin_details.rowCount() > 0:
            self.plugin_details.removeRow(0)

        for k, v in plugin.items():
            if k == 'name':
                continue
            if isinstance(v, list):
                v = ", ".join(v)
            self.plugin_details.addRow(k, QtWidgets.QLabel(v))