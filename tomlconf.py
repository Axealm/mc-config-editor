"""
tomlconf.py - Forge系mod config(コメント付きTOML)を、コメント・書式を保ったまま
読み書きするための軽量パーサ。

ポイント: 標準ライブラリの tomllib は「読み取り専用」かつ「コメントを捨てる」。
でも Forge config はコメント自体が "その項目の説明文・範囲・デフォルト" なので、
それを活かすために行ベースで自前処理する。

このモジュールは UI に一切依存しない。
-> PySide6 のGUI(editor.py)からも、将来 Hearth の Web バックエンドからも同じものを使える。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_RANGE_RE = re.compile(r"Range:\s*(.+)")


def _num(s):
    s = s.strip()
    try:
        return int(s)
    except ValueError:
        try:
            return float(s)
        except ValueError:
            return None


@dataclass
class Option:
    section: str          # 例 "general.radiation"
    key: str              # 例 "radiationEnabled"
    raw_value: str        # ファイル上の生の値文字列 (例 'true', '64', '"10"', '[...]')
    kind: str             # bool / int / float / string / list / unknown
    line_no: int          # 元ファイルの何行目か (差し替え用)
    indent: str           # 行頭のインデント(タブ等)をそのまま保持
    comments: list        # この項目の上にあったコメント行(先頭'#'は除去済み)

    rmin: float | None = None   # コメントの "Range:" から拾った下限
    rmax: float | None = None   # 同 上限

    @property
    def value(self):
        if self.kind == "bool":
            return self.raw_value == "true"
        if self.kind == "int":
            return int(self.raw_value)
        if self.kind == "float":
            return float(self.raw_value)
        if self.kind == "string":
            return self.raw_value[1:-1]      # 両端のクォートを外す
        return self.raw_value                # list / unknown は生のまま

    @property
    def description(self):
        """Range/Allowed Values 行を除いた、人間向けの説明文。"""
        out = []
        for c in self.comments:
            t = c.strip()
            if t.startswith("Range:") or t.startswith("Allowed Values:"):
                continue
            out.append(t)
        return " ".join(out)

    @property
    def range_hint(self):
        if self.rmin is not None and self.rmax is not None:
            return f"{_fmt(self.rmin)} 〜 {_fmt(self.rmax)}"
        if self.rmin is not None:
            return f"{_fmt(self.rmin)} 以上"
        if self.rmax is not None:
            return f"{_fmt(self.rmax)} 以下"
        return ""


def _fmt(n):
    if isinstance(n, float) and n.is_integer():
        return str(int(n))
    return str(n)


class ConfigDoc:
    """1つの config ファイルを表す。options を編集 -> save() で書き戻す。"""

    def __init__(self, path):
        self.path = path
        with open(path, "r", encoding="utf-8") as f:
            self.lines = f.read().split("\n")
        self.options: list[Option] = []
        self.section_comments: dict[str, str] = {}
        self._parse()

    def _parse(self):
        pending: list[str] = []
        current = ""
        for i, line in enumerate(self.lines):
            strip = line.strip()
            if strip.startswith("#"):
                pending.append(strip[1:])
            elif strip.startswith("[") and strip.endswith("]"):
                current = strip[1:-1]
                # セクション直前のコメントは "そのセクションの説明" とみなす
                self.section_comments[current] = " ".join(c.strip() for c in pending)
                pending = []
            elif strip == "":
                pending = []                 # 空行でコメントの紐付けはリセット
            elif "=" in strip:
                key, _, raw = line.partition("=")
                indent = line[:len(line) - len(line.lstrip())]
                opt = Option(current, key.strip(), raw.strip(),
                             self._kind(raw.strip()), i, indent, pending)
                self._apply_range(opt)
                self.options.append(opt)
                pending = []
            else:
                pending = []

    @staticmethod
    def _kind(v):
        if v in ("true", "false"):
            return "bool"
        if v.startswith("["):
            return "list"
        if v.startswith('"'):
            return "string"
        try:
            int(v)
            return "int"
        except ValueError:
            pass
        try:
            float(v)        # 1.6E7 のような指数表記もここで拾える
            return "float"
        except ValueError:
            return "unknown"

    def _apply_range(self, opt):
        for c in opt.comments:
            m = _RANGE_RE.search(c)
            if not m:
                continue
            spec = m.group(1).strip()
            if "~" in spec:
                lo, _, hi = spec.partition("~")
                opt.rmin, opt.rmax = _num(lo), _num(hi)
            elif spec.startswith(">"):
                opt.rmin = _num(spec[1:])
            elif spec.startswith("<"):
                opt.rmax = _num(spec[1:])

    def set_value(self, opt, new_raw):
        """編集後の生文字列を行に反映する(コメントや書式は触らない)。"""
        opt.raw_value = new_raw
        self.lines[opt.line_no] = f"{opt.indent}{opt.key} = {new_raw}"

    def sections(self):
        """登場順のユニークなセクション名。"""
        seen = []
        for o in self.options:
            if o.section not in seen:
                seen.append(o.section)
        return seen

    def save(self, path=None):
        with open(path or self.path, "w", encoding="utf-8") as f:
            f.write("\n".join(self.lines))


def serialize(kind, value):
    """GUIの入力値を、ファイルに書き戻す生文字列へ変換する。"""
    if kind == "bool":
        return "true" if value else "false"
    if kind == "int":
        return str(int(value))
    if kind == "float":
        return repr(float(value))            # float らしさ(小数点)を保つ
    if kind == "string":
        return '"' + str(value) + '"'
    return str(value)                        # list / raw はテキストをそのまま
