"""
Qt Stylesheets for Autopilot GUI widgets

See:
https://doc.qt.io/qt-5/stylesheet-reference.html#
"""

# try to use Fira



TERMINAL = """
* {
    background: #fff;
	font-family: FreeSans;
}

QWidget *, QDialog, QLayout {
background: white;
}



QPushButton {
	color: #666;
	background-color: #eee;
	padding: 5px 5px;
	border-radius: 5px;
	border: 3px solid rgba(0,0,0,1);
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

CONTROL_PANEL = """
font-family: "FreeSans";
border-bottom: 1px solid #000;
border-right: 1px solid #000;


"""