import sys

import yaml
from PyQt5 import uic
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QApplication, QMessageBox, QWidget
from yaml.parser import ParserError
sys.path.append('/Users/fg/LPL/Code/Elchemi/elchemi')
from elchemi.view import VIEW_FOLDER


class ConfigWidget(QWidget):
    updated_config = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        uic.loadUi(VIEW_FOLDER/'GUI'/'config_widget.ui', self)
        self.button_apply.clicked.connect(self.verify_yaml)
        self.button_cancel.clicked.connect(self.close)

    def update_text(self, config):
        """ Updates the text displayed on the widget based on the information available in the config.

        Parameters
        ----------
        config : dict
            Will be rendered as a YAML-formated text
        """
        self.text.setPlainText(yaml.dump(config, default_flow_style=False))

    def verify_yaml(self):
        """ Tries to transform the text into a dictionary using yaml. If it fails, it raises an error message.
        """
        try:
            config = yaml.load(self.text.toPlainText(), Loader=yaml.FullLoader)
        except ParserError:
            dlg = QMessageBox(self)
            dlg.setWindowTitle("Wrong formatting!")
            dlg.setText("The text you entered is not YAML-compliant. Please check before applying.")
            button = dlg.exec()
        self.updated_config.emit(config)


if __name__ == "__main__":
    app = QApplication([])
    with open('../../examples/config.yml') as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
    wid = ConfigWidget()
    wid.update_text(config)
    wid.show()

    sys.exit(app.exec())