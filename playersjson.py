"""
playersjson.py - ops.json / whitelist.json / banned-*.json のような
「オブジェクトの配列」JSON を読み書きする。

modが入っていないバニラ環境でも必ず存在するファイル群。
opやホワイトリストを、JSONを手打ちせず表形式で編集するためのバックエンド。
"""
import json

# 列の表示順の優先(存在するものだけ使う)
PREFERRED = ["name", "uuid", "level", "bypassesPlayerLimit",
             "reason", "source", "created", "expires", "ip"]


class PlayerList:
    def __init__(self, path):
        self.path = path
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.rows = data if isinstance(data, list) else []

    def columns(self):
        keys = []
        for row in self.rows:
            for k in row:
                if k not in keys:
                    keys.append(k)
        ordered = [c for c in PREFERRED if c in keys]
        ordered += [c for c in keys if c not in ordered]
        return ordered or ["name", "uuid"]

    def save(self, rows, path=None):
        with open(path or self.path, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, ensure_ascii=False)
            f.write("\n")


def coerce(text):
    """表のセル文字列を、JSONらしい型に戻す。"""
    t = text.strip()
    if t == "true":
        return True
    if t == "false":
        return False
    try:
        return int(t)
    except ValueError:
        return text
