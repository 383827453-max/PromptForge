"""历史记录：SQLite 本地存储。"""
from __future__ import annotations

import os
import sqlite3
import time
from dataclasses import dataclass
from typing import List, Optional

from .config import data_dir

_SCHEMA = """
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    strategy TEXT NOT NULL,
    original TEXT NOT NULL,
    enhanced TEXT NOT NULL,
    notes TEXT DEFAULT '',
    favorite INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_history_ts ON history(ts DESC);
"""


@dataclass
class HistoryItem:
    id: int
    ts: int
    strategy: str
    original: str
    enhanced: str
    notes: str
    favorite: int

    @property
    def time_str(self) -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.ts))


class Database:
    def __init__(self) -> None:
        self.path = os.path.join(data_dir(), "history.db")
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def add(self, strategy: str, original: str, enhanced: str, notes: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO history (ts, strategy, original, enhanced, notes) VALUES (?, ?, ?, ?, ?)",
            (int(time.time()), strategy, original, enhanced, notes),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def list(self, keyword: str = "", strategy: str = "", only_favorite: bool = False,
             limit: int = 200) -> List[HistoryItem]:
        sql = "SELECT id, ts, strategy, original, enhanced, notes, favorite FROM history WHERE 1=1"
        args: list = []
        if keyword:
            # LIKE 的 % 与 _ 是通配符，必须转义后再当字面量匹配，
            # 否则搜 "100%" 会命中所有记录。配合 ESCAPE '\' 指定转义符。
            esc = (keyword.replace("\\", "\\\\")
                          .replace("%", "\\%")
                          .replace("_", "\\_"))
            sql += " AND (original LIKE ? ESCAPE '\\' OR enhanced LIKE ? ESCAPE '\\')"
            args += [f"%{esc}%", f"%{esc}%"]
        if strategy:
            sql += " AND strategy = ?"
            args.append(strategy)
        if only_favorite:
            sql += " AND favorite = 1"
        # ts 精度是秒，同秒内多条记录只按 ts 排序顺序不稳定（每次查询可能不同）。
        # 追加 id 作为次级排序键，保证顺序确定：后插入的排前面。
        sql += " ORDER BY ts DESC, id DESC LIMIT ?"
        args.append(limit)
        rows = self._conn.execute(sql, args).fetchall()
        return [HistoryItem(*r) for r in rows]

    def get(self, item_id: int) -> Optional[HistoryItem]:
        row = self._conn.execute(
            "SELECT id, ts, strategy, original, enhanced, notes, favorite FROM history WHERE id = ?",
            (item_id,),
        ).fetchone()
        return HistoryItem(*row) if row else None

    def set_favorite(self, item_id: int, fav: bool) -> None:
        self._conn.execute("UPDATE history SET favorite = ? WHERE id = ?", (1 if fav else 0, item_id))
        self._conn.commit()

    def delete(self, item_id: int) -> None:
        self._conn.execute("DELETE FROM history WHERE id = ?", (item_id,))
        self._conn.commit()

    def clear(self) -> None:
        self._conn.execute("DELETE FROM history")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()
