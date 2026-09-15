"""应用入口：QApplication 初始化、主题应用、主窗口启动。"""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .config import load_settings
from .theme import apply_theme
from .ui.main_window import MainWindow

_app: QApplication | None = None


def resource_path(rel: str) -> str:
    """兼容开发环境与 PyInstaller 打包环境的资源路径解析。"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, rel)


def app_icon() -> QIcon:
    for rel in ("assets/icon.png", "assets/icon.ico"):
        p = resource_path(rel)
        if os.path.exists(p):
            return QIcon(p)
    return QIcon()


def apply_current_theme(name: str) -> None:
    if _app is not None:
        apply_theme(_app, name)


def main() -> int:
    global _app
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    _app = QApplication(sys.argv)
    _app.setApplicationName("PromptForge")
    _app.setWindowIcon(app_icon())
    settings = load_settings()
    apply_theme(_app, settings.theme)
    win = MainWindow()
    win.setWindowIcon(app_icon())
    win.show()
    return _app.exec()


if __name__ == "__main__":
    sys.exit(main())