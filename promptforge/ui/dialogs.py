"""对话框：模板变量填充、模板编辑。"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
)

from ..enhancer import STRATEGIES
from ..templates import Template


class TemplateFillDialog(QDialog):
    """为模板中的 {{变量}} 逐项填充。"""

    def __init__(self, template: Template, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"填充模板变量 - {template.name}")
        self.resize(520, 300)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"模板「{template.name}」包含以下变量，请逐项填写："))
        form = QFormLayout()
        self._edits: dict = {}
        for v in template.variables():
            e = QLineEdit()
            e.setPlaceholderText(f"请输入{v}")
            self._edits[v] = e
            form.addRow(v, e)
        lay.addLayout(form)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def values(self) -> dict:
        return {k: e.text() for k, e in self._edits.items()}


class TemplateEditDialog(QDialog):
    """新建/编辑用户自定义模板。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("新建模板")
        self.resize(560, 460)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("模板名称")
        self.category_edit = QLineEdit()
        self.category_edit.setPlaceholderText("分类，如：办公 / 编程 / 写作")
        self.strategy_combo = QComboBox()
        for s in STRATEGIES:
            self.strategy_combo.addItem(s["label"], s["key"])
        form.addRow("名称", self.name_edit)
        form.addRow("分类", self.category_edit)
        form.addRow("关联策略", self.strategy_combo)
        lay.addLayout(form)
        lay.addWidget(QLabel("模板内容（使用 {{变量名}} 作为占位符）："))
        self.content_edit = QPlainTextEdit()
        self.content_edit.setPlaceholderText("例如：请帮我写一份关于{{主题}}的{{文体}}……")
        lay.addWidget(self.content_edit, 1)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def template(self) -> Template:
        return Template(
            name=self.name_edit.text().strip() or "未命名模板",
            category=self.category_edit.text().strip() or "自定义",
            strategy=self.strategy_combo.currentData(),
            content=self.content_edit.toPlainText(),
            builtin=False,
        )
