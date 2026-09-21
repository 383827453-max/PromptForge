"""异常定义。"""
from __future__ import annotations


class LLMError(Exception):
    """所有面向用户的失败都收敛成这一个异常类型。

    消息文本是给最终用户看的（含实际请求地址与针对性排查建议），
    不是给开发者看的栈信息。
    """
