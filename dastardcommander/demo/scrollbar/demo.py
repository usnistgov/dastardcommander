"""
scrollbar/demo.py

Demonstrate how to get a Qt5 scrollbar to appear.

Uses a QScrollArea object to scroll through lots of buttons, by adding them to the QScrollArea's
contents widget's layout. Whew!

The point is that this can be a model for objects like the grid of count rate buttons on the Observe Tab.
"""

import os
import sys

# Qt5 imports
import PyQt5.uic
from PyQt5 import QtCore, QtGui, QtWidgets

class DemoDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        QtWidgets.QDialog.__init__(self, parent)
        self.setWindowIcon(QtGui.QIcon("dc.png"))
        PyQt5.uic.loadUi(
            os.path.join(os.path.dirname(__file__), "demo.ui"), self
        )
        # xwidth = ywidth = 50
        for row in range(16):
            for col in range(5):
                button = QtWidgets.QPushButton(f"R{row}C{col}")
                # button.setFixedSize(xwidth, ywidth)
                button.setFlat(False)

                self.scrollAreaWidgetContents_2.layout().addWidget(button, row, col)

def main():
    app = QtWidgets.QApplication(sys.argv)
    dd = DemoDialog()
    dd.show()
    retval = app.exec_()
    # print("Return: ", retval)



if __name__=="__main__":
    main()