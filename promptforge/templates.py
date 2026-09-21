"""模板库：内置模板 + 用户自定义模板（JSON 持久化）。"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from typing import List

from .config import data_dir

BUILTIN_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates_builtin", "templates.json")


def user_path() -> str:
    """用户模板文件路径，运行时解析。

    早期实现在 import 时就把 data_dir() 固化成模块常量，
    PROMPTFORGE_DATA_DIR 在导入之后生效时用户模板会全部读不到。
    """
    return os.path.join(data_dir(), "user_templates.json")

_VAR_RE = re.compile(r"\{\{\s*(.+?)\s*\}\}")


def normalize_var_name(name: str) -> str:
    """变量名比较用的归一化形式：去掉首尾空白并折叠内部空白。"""
    return re.sub(r"\s+", " ", name.strip())


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
            v = normalize_var_name(m.group(1))
            if v and v not in seen:
                seen.append(v)
        return seen

    def fill(self, values: dict) -> str:
        """替换模板中的 {{变量}}。

        按正则整段匹配「含空白的占位符」再替换：早期实现是把
        `"{{" + k + "}}"` 当作字面量去 replace，模板里写成 `{{ 主题 }}`
        （带空格，书写时很自然）就替换不掉，占位符会原样出现在最终
        提示词里被发给模型。键做归一化，键与占位符的空格差异不再影响匹配。
        """
        lookup = {normalize_var_name(k): v for k, v in values.items()}
        if not lookup:
            return self.content

        def _sub(m: "re.Match[str]") -> str:
            key = normalize_var_name(m.group(1))
            if key in lookup:
                val = lookup[key]
                return val if isinstance(val, str) else str(val)
            return m.group(0)  # 未提供的变量保持原样

        return _VAR_RE.sub(_sub, self.content)


def _load(path: str, builtin: bool) -> List[Template]:
    """读取模板文件。

    必须是「逐字段挑选」而不是 `Template(builtin=builtin, **t)`：
    save_user 用 asdict() 落盘，写出来的 JSON 里本来就带 "builtin" 键，
    再显式传一次 builtin 会抛 "got multiple values for keyword argument"，
    被外层 except 吞掉后返回空列表——用户新建的模板保存成功却永远
    显示不出来。未知键同理忽略，不因一个多余字段丢弃整个模板库。
    """
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    out: List[Template] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        out.append(Template(
            name=str(item.get("name", "")),
            category=str(item.get("category", "")),
            strategy=str(item.get("strategy", "general")),
            content=str(item.get("content", "")),
            builtin=builtin,
        ))
    return out


def load_builtin() -> List[Template]:
    return _load(BUILTIN_PATH, builtin=True)


def load_user() -> List[Template]:
    return _load(user_path(), builtin=False)


def load_all() -> List[Template]:
    return load_builtin() + load_user()


def save_user(templates: List[Template]) -> None:
    data = [asdict(t) for t in templates if not t.builtin]
    p = user_path()
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, p)


def add_user_template(t: Template) -> None:
    items = load_user()
    items.append(t)
    save_user(items)


def delete_user_template(name: str) -> None:
    items = [t for t in load_user() if t.name != name]
    save_user(items)
