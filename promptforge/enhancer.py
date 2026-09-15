"""增强引擎：策略模板装配 + 输出解析。"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from .config import data_dir
from .llm_client import LLMClient

STRATEGY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "strategies")
USER_STRATEGY_DIR = os.path.join(data_dir(), "strategies")

STRATEGIES: List[Dict[str, str]] = [
    {"key": "general", "label": "通用"},
    {"key": "coding", "label": "编程"},
    {"key": "drawing", "label": "绘画"},
    {"key": "writing", "label": "写作"},
]


@dataclass
class EnhanceResult:
    enhanced: str
    notes: str
    raw: str


def strategy_path(key: str) -> str:
    """用户自定义策略优先，其次内置策略。"""
    user = os.path.join(USER_STRATEGY_DIR, key + ".md")
    if os.path.exists(user):
        return user
    return os.path.join(STRATEGY_DIR, key + ".md")


def load_strategy(key: str) -> str:
    path = strategy_path(key)
    if not os.path.exists(path):
        raise FileNotFoundError(f"策略模板不存在: {key}")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def strategy_label(key: str) -> str:
    for s in STRATEGIES:
        if s["key"] == key:
            return s["label"]
    return key


def build_meta_prompt(strategy_key: str, original: str, extra_options: str = "") -> str:
    tpl = load_strategy(strategy_key)
    extra = ""
    if extra_options.strip():
        extra = "# 用户附加要求\n以下是用户对本次增强的附加要求，必须严格遵守：\n" + extra_options.strip()
    # 防止用户输入中的花括号干扰 format
    return tpl.replace("{extra_instructions}", extra).replace("{original_prompt}", original)


_TAG_RE = re.compile(r"<enhanced>(.*?)</enhanced>", re.S | re.I)
_NOTES_RE = re.compile(r"<notes>(.*?)</notes>", re.S | re.I)


def parse_output(raw: str) -> EnhanceResult:
    """从模型输出中提取 <enhanced> 与 <notes> 区块；缺失时降级处理。"""
    m = _TAG_RE.search(raw)
    enhanced = m.group(1).strip() if m else ""
    n = _NOTES_RE.search(raw)
    notes = n.group(1).strip() if n else ""
    if not enhanced:
        # 降级：去掉 notes 区块后整体作为增强结果
        fallback = _NOTES_RE.sub("", raw)
        fallback = re.sub(r"^[\s`#>]+", "", fallback.strip())
        enhanced = fallback.strip() or raw.strip()
        notes = notes or "（模型未按结构化格式输出，已原样展示）"
    return EnhanceResult(enhanced=enhanced, notes=notes, raw=raw)


class Enhancer:
    """组装元提示词并调用 LLM 完成增强。"""

    def __init__(self, client: LLMClient, use_stream: bool = True) -> None:
        self.client = client
        self.use_stream = use_stream

    def enhance(self, strategy_key: str, original: str, extra_options: str = "") -> EnhanceResult:
        meta = build_meta_prompt(strategy_key, original, extra_options)
        raw = self.client.complete(meta)
        return parse_output(raw)

    def enhance_stream(self, strategy_key: str, original: str, extra_options: str,
                       on_delta) -> EnhanceResult:
        meta = build_meta_prompt(strategy_key, original, extra_options)
        buf: List[str] = []
        for chunk in self.client.stream(meta, on_delta=on_delta):
            buf.append(chunk)
        return parse_output("".join(buf))