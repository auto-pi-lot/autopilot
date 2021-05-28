"""
Qt Stylesheets for Autopilot GUI widgets

See:
https://doc.qt.io/qt-5/stylesheet-reference.html#
"""
import sys
# try to use Fira

if sys.platform == "darwin":
    FONT_FAMILY = 'Helvetica'
else:
    FONT_FAMILY = "FreeSans"

TERMINAL = f"""
* {{
    background: #fff;
	font-family: {FONT_FAMILY};
    color: #000;
}}

QWidget *, QDialog, QLayout {{
background: white;
}}



QPushButton {{
	color: #666;
	background-color: #eee;
	padding: 5px 5px;
	border-radius: 5px;
	border: 3px solid rgba(0,0,0,1);
	border-bottom-width: 3px;
	font-size: 14pt;
}}

QPushButton:hover {{
		background-color: #e3e3e3;
		border-color: rgba(0,0,0,0.5);
 }}
 
QPushButton:pressed {{
		background-color: #CCC;
		border-color: rgba(0,0,0,0.9);
}}

QMenuBar, QMenuBar * {{
 color: black;
}}

"""

PLOT = """
AxisItem
"""

CONTROL_PANEL = """
font-family: "FreeSans";
border-top: 1px solid #000;
border-left: 1px solid #000;


"""