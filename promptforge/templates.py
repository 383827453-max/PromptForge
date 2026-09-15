"""模板库：内置模板 + 用户自定义模板（JSON 持久化）。"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, asdict
from typing import List

from .config import data_dir

BUILTIN_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates_builtin", "templates.json")
USER_PATH = os.path.join(data_dir(), "user_templates.json")

_VAR_RE = re.compile(r"\{\{(.+?)\}\}")


@dataclass
class Template:
    name: str
    category: str
    strategy: str
    content: str
    builtin: bool = False

    def variables(self) -> List[str]:
        seen: List[str] = []
        for m in _VAR_RE.finditer(self.content):
            v = m.group(1).strip()
            if v not in seen:
                seen.append(v)
        return seen

    def fill(self, values: dict) -> str:
        out = self.content
        for k, v in values.items():
            out = out.replace("{{" + k + "}}", v)
        return out


def _load(path: str, builtin: bool) -> List[Template]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return [Template(builtin=builtin, **t) for t in raw]
    except Exception:
        return []


def load_builtin() -> List[Template]:
    return _load(BUILTIN_PATH, builtin=True)


def load_user() -> List[Template]:
    return _load(USER_PATH, builtin=False)


def load_all() -> List[Template]:
    return load_builtin() + load_user()


def save_user(templates: List[Template]) -> None:
    data = [asdict(t) for t in templates if not t.builtin]
    with open(USER_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_user_template(t: Template) -> None:
    items = load_user()
    items.append(t)
    save_user(items)


def delete_user_template(name: str) -> None:
    items = [t for t in load_user() if t.name != name]
    save_user(items)