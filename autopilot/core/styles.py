"""
Qt Stylesheets for Autopilot GUI widgets

See:
https://doc.qt.io/qt-5/stylesheet-reference.html#
"""

# try to use Fira



TERMINAL = """
* {
background: white;

	font-family: "FreeSans";
}

QWidget *, QDialog, QLayout {
background: white;
}

QWidget {
}

QPushButton {
	color: #666;
	background-color: #eee;
	font: normal "FreeSans" 20px;
	padding: 5px 5px;
	border-radius: 5px;
	border: 1px solid rgba(0,0,0,0.3);
	border-bottom-width: 3px;
}

QPushButton:hover {
		background-color: #e3e3e3;
		border-color: rgba(0,0,0,0.5);
 }
 
QPushButton:pressed {
		background-color: #CCC;
		border-color: rgba(0,0,0,0.9);
}

QMenuBar, QMenuBar * {
 color: black;
}

"""

PLOT = """
AxisItem
"""