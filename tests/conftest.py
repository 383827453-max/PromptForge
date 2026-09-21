"""pytest 公共夹具。

每个测试用例都在独立的临时数据目录里跑，避免污染真实的
%APPDATA%\\PromptForge 配置与历史库。
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """把 data_dir() 重定向到临时目录。"""
    d = tmp_path / "pfdata"
    d.mkdir()
    monkeypatch.setenv("PROMPTFORGE_DATA_DIR", str(d))
    yield d


@pytest.fixture
def qapp():
    """无头 QApplication（GUI 相关用例用）。"""
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app
