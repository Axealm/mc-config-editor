"""
propconf.py - server.properties (Java .properties形式) を読み書きする軽量パーサ + スキーマ。

server.properties はファイル内に各項目の説明が無い(Forge configと違う)。
そこで「各設定の意味・型・選択肢・日本語解説」を SCHEMA としてツール側が持つ。
この知識こそが、メモ帳での手編集に対する"価値"になる(差別化ポイント)。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Prop:
    key: str
    raw_value: str
    line_no: int


class PropertiesDoc:
    def __init__(self, path):
        self.path = path
        with open(path, "r", encoding="utf-8") as f:
            self.lines = f.read().split("\n")
        self.props: list[Prop] = []
        self._parse()

    def _parse(self):
        for i, line in enumerate(self.lines):
            s = line.strip()
            if not s or s.startswith("#") or s.startswith("!"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                self.props.append(Prop(key.strip(), value, i))

    def set_value(self, prop, new_value):
        prop.raw_value = new_value
        self.lines[prop.line_no] = f"{prop.key}={new_value}"

    def save(self, path=None):
        with open(path or self.path, "w", encoding="utf-8") as f:
            f.write("\n".join(self.lines))


# t: bool / int / string / enum
SCHEMA = {
    "gamemode": {"t": "enum", "choices": ["survival", "creative", "adventure", "spectator"],
                 "ja": "初期ゲームモード。"},
    "difficulty": {"t": "enum", "choices": ["peaceful", "easy", "normal", "hard"],
                   "ja": "難易度。peacefulだと敵Mobが湧かない。"},
    "hardcore": {"t": "bool", "ja": "ハードコア。死亡で復活不可（スペクテイター固定）になる。"},
    "pvp": {"t": "bool", "ja": "プレイヤー同士の戦闘を許可する。"},
    "online-mode": {"t": "bool",
                    "ja": "正規アカウント認証を行う。falseは誰でもなりすませて危険。基本true。"},
    "white-list": {"t": "bool", "ja": "ホワイトリストを有効化。許可した人だけ参加できる。"},
    "enforce-whitelist": {"t": "bool", "ja": "稼働中もホワイトリストを厳格適用し、外れた人を追い出す。"},
    "enforce-secure-profile": {"t": "bool", "ja": "署名付きチャットを必須にする。"},
    "max-players": {"t": "int", "min": 0, "max": 2147483647, "ja": "同時接続できる最大人数。"},
    "view-distance": {"t": "int", "min": 3, "max": 32, "ja": "描画チャンク距離。大きいほど重い。"},
    "simulation-distance": {"t": "int", "min": 3, "max": 32, "ja": "Mob等が動作する距離。大きいほど重い。"},
    "server-port": {"t": "int", "min": 1, "max": 65535, "ja": "待ち受けポート。通常は25565。"},
    "spawn-protection": {"t": "int", "min": 0, "max": 100000,
                         "ja": "スポーン地点をop以外が触れない保護半径(ブロック)。0で無効。"},
    "op-permission-level": {"t": "int", "min": 0, "max": 4, "ja": "opの権限レベル(0〜4)。4が最強。"},
    "function-permission-level": {"t": "int", "min": 1, "max": 4, "ja": "コマンド関数の既定権限レベル。"},
    "player-idle-timeout": {"t": "int", "min": 0, "max": 525600, "ja": "無操作で自動キックする分数。0で無効。"},
    "enable-command-block": {"t": "bool", "ja": "コマンドブロックを使用可能にする。"},
    "allow-flight": {"t": "bool", "ja": "サバイバルでの飛行を許可（飛行Mod誤検知対策にも）。"},
    "allow-nether": {"t": "bool", "ja": "ネザーへの移動を許可する。"},
    "force-gamemode": {"t": "bool", "ja": "参加時に既定ゲームモードを強制する。"},
    "spawn-monsters": {"t": "bool", "ja": "モンスターの自然湧きを許可。"},
    "spawn-animals": {"t": "bool", "ja": "動物の自然湧きを許可。"},
    "spawn-npcs": {"t": "bool", "ja": "村人NPCの湧きを許可。"},
    "generate-structures": {"t": "bool", "ja": "村・要塞などの構造物を生成する。"},
    "enable-rcon": {"t": "bool", "ja": "RCON（遠隔コンソール）を有効化する。"},
    "motd": {"t": "string", "ja": "サーバー一覧に表示される紹介文（カラーコード可）。"},
    "level-name": {"t": "string", "ja": "ワールドのフォルダ名。"},
    "level-seed": {"t": "string", "ja": "ワールド生成シード（空でランダム）。"},
    "level-type": {"t": "enum",
                   "choices": ["minecraft\\:normal", "minecraft\\:flat",
                               "minecraft\\:large_biomes", "minecraft\\:amplified"],
                   "ja": "ワールドの種類。flatは完全な平地、large_biomesはバイオームが巨大化。"},
    "resource-pack": {"t": "string", "ja": "配布リソースパックのURL。"},
    "server-ip": {"t": "string", "ja": "待ち受けIP（通常は空）。"},
}
