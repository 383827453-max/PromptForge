"""主题样式：深色科技风 / 浅色。"""

DARK = """
* { font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif; }
QMainWindow, QDialog, QWidget { background-color: #0f1420; color: #d8dee9; font-size: 13px; }
QTabWidget::pane { border: 1px solid #1e2635; background: #0f1420; }
QTabBar::tab { background: #141b2b; color: #8a93a6; padding: 8px 22px; border: 1px solid #1e2635; border-bottom: none; margin-right: 2px; }
QTabBar::tab:selected { background: #0f1420; color: #4fc3f7; border-top: 2px solid #4fc3f7; }
QPlainTextEdit, QTextEdit, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #141b2b; color: #d8dee9; border: 1px solid #263043; border-radius: 6px; padding: 6px 8px;
    selection-background-color: #2b5c8a;
}
QPlainTextEdit:focus, QTextEdit:focus, QLineEdit:focus { border: 1px solid #4fc3f7; }
QPlainTextEdit:read-only, QTextEdit:read-only { background-color: #111726; }
QPushButton { background-color: #1d2a44; color: #d8dee9; border: 1px solid #2b3c5e; border-radius: 6px; padding: 7px 18px; }
QPushButton:hover { background-color: #24365c; border-color: #4fc3f7; }
QPushButton:pressed { background-color: #16223a; }
QPushButton:disabled { background-color: #161d2c; color: #5a6478; border-color: #1e2635; }
QPushButton#primaryBtn { background-color: #0e639c; border: none; color: white; font-weight: bold; }
QPushButton#primaryBtn:hover { background-color: #1177bb; }
QPushButton#primaryBtn:disabled { background-color: #1a2a3f; color: #5a6478; }
QPushButton#dangerBtn { background-color: #5c2430; border-color: #7a3040; }
QPushButton#dangerBtn:hover { background-color: #742d3d; }
QLabel#titleLabel { font-size: 18px; font-weight: bold; color: #4fc3f7; }
QLabel#hintLabel { color: #6b7589; font-size: 12px; }
QLabel#statusOk { color: #66bb6a; }
QLabel#statusErr { color: #ef5350; }
QGroupBox { border: 1px solid #1e2635; border-radius: 8px; margin-top: 12px; padding-top: 8px; font-weight: bold; color: #8fb8d8; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
QListWidget, QTreeWidget, QTableWidget { background-color: #141b2b; border: 1px solid #263043; border-radius: 6px; outline: none; }
QListWidget::item { padding: 6px 8px; border-radius: 4px; }
QListWidget::item:selected { background-color: #1d3a5f; color: #d8dee9; }
QListWidget::item:hover { background-color: #1a2438; }
QHeaderView::section { background-color: #141b2b; color: #8a93a6; border: none; border-bottom: 1px solid #263043; padding: 6px; }
QScrollBar:vertical { background: #0f1420; width: 10px; }
QScrollBar::handle:vertical { background: #2b3c5e; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #3a5080; }
QScrollBar:horizontal { background: #0f1420; height: 10px; }
QScrollBar::handle:horizontal { background: #2b3c5e; border-radius: 5px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QStatusBar { background: #0c101a; color: #6b7589; border-top: 1px solid #1e2635; }
QMenuBar { background: #0c101a; color: #d8dee9; }
QMenuBar::item:selected { background: #1d2a44; }
QMenu { background: #141b2b; border: 1px solid #263043; }
QMenu::item { padding: 6px 24px; }
QMenu::item:selected { background: #1d3a5f; }
QCheckBox::indicator, QRadioButton::indicator { width: 15px; height: 15px; }
QSplitter::handle { background: #1e2635; width: 3px; }
QToolTip { background-color: #1d2a44; color: #d8dee9; border: 1px solid #4fc3f7; padding: 4px; }
QProgressBar { background: #141b2b; border: 1px solid #263043; border-radius: 5px; text-align: center; color: #d8dee9; height: 12px; }
QProgressBar::chunk { background: #4fc3f7; border-radius: 4px; }
"""

LIGHT = """
* { font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif; }
QMainWindow, QDialog, QWidget { background-color: #f5f7fa; color: #2c3e50; font-size: 13px; }
QTabWidget::pane { border: 1px solid #dde3ea; background: #ffffff; }
QTabBar::tab { background: #e8edf3; color: #6b7a8d; padding: 8px 22px; border: 1px solid #dde3ea; border-bottom: none; margin-right: 2px; }
QTabBar::tab:selected { background: #ffffff; color: #0e639c; border-top: 2px solid #0e639c; }
QPlainTextEdit, QTextEdit, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #ffffff; color: #2c3e50; border: 1px solid #cfd8e3; border-radius: 6px; padding: 6px 8px;
}
QPlainTextEdit:focus, QTextEdit:focus, QLineEdit:focus { border: 1px solid #0e639c; }
QPushButton { background-color: #e8edf3; color: #2c3e50; border: 1px solid #cfd8e3; border-radius: 6px; padding: 7px 18px; }
QPushButton:hover { background-color: #dce6f2; border-color: #0e639c; }
QPushButton#primaryBtn { background-color: #0e639c; border: none; color: white; font-weight: bold; }
QPushButton#primaryBtn:hover { background-color: #1177bb; }
QPushButton#dangerBtn { background-color: #c0392b; color: white; border: none; }
QLabel#titleLabel { font-size: 18px; font-weight: bold; color: #0e639c; }
QLabel#hintLabel { color: #8a97a8; font-size: 12px; }
QGroupBox { border: 1px solid #dde3ea; border-radius: 8px; margin-top: 12px; padding-top: 8px; font-weight: bold; color: #34608a; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
QListWidget, QTreeWidget, QTableWidget { background-color: #ffffff; border: 1px solid #cfd8e3; border-radius: 6px; }
QListWidget::item { padding: 6px 8px; border-radius: 4px; }
QListWidget::item:selected { background-color: #cfe3f5; color: #2c3e50; }
QStatusBar { background: #e8edf3; color: #6b7a8d; }
QScrollBar:vertical { background: #f5f7fa; width: 10px; }
QScrollBar::handle:vertical { background: #c3cedb; border-radius: 5px; min-height: 30px; }
QSplitter::handle { background: #dde3ea; width: 3px; }
"""


def apply_theme(app, name: str) -> None:
    app.setStyleSheet(DARK if name == "dark" else LIGHT)