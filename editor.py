#!/usr/bin/env python3
"""
editor.py - Minecraftサーバーの設定を「まるごとGUIで」編集するデモ (PySide6)。

左でファイルを選ぶ -> 右がそのファイル専用のエディタに切り替わる:
  - server.properties  -> 型を理解したフォーム (bool=チェック, enum=ドロップダウン,
                          数値=スピン)。各設定の日本語解説つき (🇯🇵トグル)。
  - ops.json / whitelist.json -> 表で op / ホワイトリストを追加・削除・編集。
  - config/**/*.toml (mod config) -> コメント保持フォーム + 検索。

modの有無に関係なく全サーバーが持つファイルを触れる = Hearth(サーバー管理)の一機能に直結。
パース処理は tomlconf.py / propconf.py / playersjson.py に分離(UI非依存・移植可能)。

起動: py editor.py
"""
import glob
import os
import shutil
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator, QDoubleValidator
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QScrollArea, QGroupBox, QCheckBox, QSpinBox, QDoubleSpinBox, QLineEdit,
    QComboBox, QLabel, QPushButton, QFileDialog, QListWidget, QListWidgetItem,
    QTableWidget, QTableWidgetItem, QHeaderView, QSplitter, QAbstractItemView,
    QPlainTextEdit,
)

import tomlconf
import propconf
import playersjson
import rcon

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SERVER = os.path.join(HERE, "server")
INT32 = 2 ** 31 - 1

# mod config(TOML)の簡易日本語化辞書(デモ用・一部のみ。製品版はLLMで全自動翻訳する想定)
JA_SECTION = {
    "general": "全般", "general.dynamic_tank": "ダイナミックタンク",
    "general.auto_eject": "自動排出", "general.radiation": "放射線",
    "general.digital_miner": "デジタルマイナー", "general.laser": "レーザー",
    "general.pump": "ポンプ", "general.security": "ブロックの保護",
    "general.energy_conversion": "エネルギー変換レート",
}
JA_DESC = {
    "Log Mekanism packet names. Debug setting.": "Mekanismのパケット名をログ出力（デバッグ用）。",
    "Disable to make the anchor upgrade not do anything.": "無効にするとアンカーアップグレードが無効化される。",
    "Enable worldwide radiation effects. Don't be a downer and disable this.":
        "世界全体の放射線効果を有効化する。",
    "How far (in blocks) a laser can travel.": "レーザーが届く距離（ブロック数）。",
    "If enabled, lasers can break blocks and the flamethrower starts fires.":
        "有効にするとレーザーがブロックを壊し、火炎放射器が着火する。",
    "Maximum block distance to pull fluid from for the Electric Pump.":
        "電動ポンプが液体を吸い上げる最大距離（ブロック）。",
}


def backup(path):
    shutil.copyfile(path, path + ".bak")


def help_label(text):
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet("color:#777; font-size:11px")
    return lbl


# =========================================================================
# View 1: server.properties (スキーマ駆動フォーム)
# =========================================================================
class PropsView(QWidget):
    def __init__(self, path):
        super().__init__()
        self.doc = propconf.PropertiesDoc(path)
        self.getters = []
        self.ja = False
        self.query = ""
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.scroll)
        self.rebuild()

    def set_ja(self, on):
        self.ja = on
        self.rebuild()

    def set_filter(self, text):
        self.query = text.strip().lower()
        self.rebuild()

    def _collect(self):
        for prop, getter in self.getters:
            self.doc.set_value(prop, getter())

    def rebuild(self):
        if self.getters:
            self._collect()
        self.getters = []
        box = QGroupBox("server.properties")
        form = QFormLayout(box)
        form.setLabelAlignment(Qt.AlignRight)

        for prop in self.doc.props:
            sch = propconf.SCHEMA.get(prop.key, {})
            ja_txt = sch.get("ja", "")
            if self.query and self.query not in prop.key.lower() and self.query not in ja_txt.lower():
                continue
            widget, getter = self._make_widget(prop, sch)
            self.getters.append((prop, getter))

            hint = ""
            if self.ja and ja_txt:
                hint = "🇯🇵 " + ja_txt
            if sch.get("t") == "int" and "min" in sch:
                hint += f"  ［範囲: {sch['min']}〜{sch['max']}］"
            cell = QWidget()
            cl = QVBoxLayout(cell)
            cl.setContentsMargins(0, 0, 0, 6)
            cl.setSpacing(1)
            cl.addWidget(widget)
            if hint.strip():
                cl.addWidget(help_label(hint))
            form.addRow(prop.key, cell)

        self.scroll.setWidget(box)

    def _make_widget(self, prop, sch):
        v = prop.raw_value
        t = sch.get("t")
        if t == "enum":
            w = QComboBox()
            w.addItems(sch["choices"])
            if v in sch["choices"]:
                w.setCurrentText(v)
            elif v:
                w.addItem(v)
                w.setCurrentText(v)
            return w, lambda: w.currentText()
        if t == "bool" or v in ("true", "false"):
            w = QCheckBox("有効")
            w.setChecked(v == "true")
            return w, lambda: "true" if w.isChecked() else "false"
        if t == "int" and "min" in sch and -INT32 <= sch["min"] and sch["max"] <= INT32:
            w = QSpinBox()
            w.setRange(sch["min"], sch["max"])
            try:
                w.setValue(int(v))
            except ValueError:
                pass
            return w, lambda: str(w.value())
        le = QLineEdit(v)
        if v.lstrip("-").isdigit():
            le.setValidator(QIntValidator())
        return le, lambda: le.text()

    def save(self):
        self._collect()
        backup(self.doc.path)
        self.doc.save()


# =========================================================================
# View 2: ops.json / whitelist.json (表エディタ)
# =========================================================================
class PlayersView(QWidget):
    def __init__(self, path):
        super().__init__()
        self.pl = playersjson.PlayerList(path)
        self.cols = self.pl.columns()

        self.table = QTableWidget(len(self.pl.rows), len(self.cols))
        self.table.setHorizontalHeaderLabels(self.cols)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        for r, row in enumerate(self.pl.rows):
            for c, col in enumerate(self.cols):
                self.table.setItem(r, c, QTableWidgetItem(str(row.get(col, ""))))

        add = QPushButton("＋ 行を追加")
        add.clicked.connect(self._add_row)
        rm = QPushButton("− 選択行を削除")
        rm.clicked.connect(self._del_row)
        bar = QHBoxLayout()
        bar.addWidget(add)
        bar.addWidget(rm)
        bar.addStretch(1)

        lay = QVBoxLayout(self)
        lay.addLayout(bar)
        lay.addWidget(self.table)

    def _add_row(self):
        self.table.insertRow(self.table.rowCount())

    def _del_row(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)

    def set_ja(self, on):
        pass

    def set_filter(self, text):
        q = text.strip().lower()
        for r in range(self.table.rowCount()):
            text_in_row = " ".join(
                (self.table.item(r, c).text() if self.table.item(r, c) else "")
                for c in range(self.table.columnCount())
            ).lower()
            self.table.setRowHidden(r, bool(q) and q not in text_in_row)

    def save(self):
        rows = []
        for r in range(self.table.rowCount()):
            d = {}
            empty = True
            for c, col in enumerate(self.cols):
                item = self.table.item(r, c)
                txt = item.text() if item else ""
                if txt.strip():
                    empty = False
                d[col] = playersjson.coerce(txt)
            if not empty:
                rows.append(d)
        backup(self.pl.path)
        self.pl.save(rows)


# =========================================================================
# View 3: mod config (TOML, コメント保持フォーム)
# =========================================================================
class TomlView(QWidget):
    def __init__(self, path):
        super().__init__()
        self.doc = tomlconf.ConfigDoc(path)
        self.getters = []
        self.ja = False
        self.query = ""
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.scroll)
        self.rebuild()

    def set_ja(self, on):
        self.ja = on
        self.rebuild()

    def set_filter(self, text):
        self.query = text.strip().lower()
        self.rebuild()

    def _collect(self):
        for opt, getter in self.getters:
            kind, value = getter()
            self.doc.set_value(opt, tomlconf.serialize(kind, value))

    def rebuild(self):
        if self.getters:
            self._collect()
        self.getters = []
        container = QWidget()
        vbox = QVBoxLayout(container)
        vbox.setAlignment(Qt.AlignTop)

        for section in self.doc.sections():
            opts = [o for o in self.doc.options if o.section == section
                    and (not self.query or self.query in o.key.lower()
                         or self.query in o.description.lower())]
            if not opts:
                continue
            title = section
            if self.ja and section in JA_SECTION:
                title = f"{JA_SECTION[section]}  ({section})"
            box = QGroupBox(title)
            form = QFormLayout(box)
            form.setLabelAlignment(Qt.AlignRight)
            for opt in opts:
                widget, getter = self._make_widget(opt)
                self.getters.append((opt, getter))
                desc = opt.description
                if self.ja and desc in JA_DESC:
                    desc = "🇯🇵 " + JA_DESC[desc]
                hint = f"  ［範囲: {opt.range_hint}］" if opt.range_hint else ""
                cell = QWidget()
                cl = QVBoxLayout(cell)
                cl.setContentsMargins(0, 0, 0, 6)
                cl.setSpacing(1)
                cl.addWidget(widget)
                if desc or hint:
                    cl.addWidget(help_label(desc + hint))
                form.addRow(opt.key, cell)
            vbox.addWidget(box)
        self.scroll.setWidget(container)

    def _make_widget(self, opt):
        if opt.kind == "bool":
            w = QCheckBox("有効")
            w.setChecked(opt.value)
            return w, lambda: ("bool", w.isChecked())
        if opt.kind == "int" and opt.rmin is not None and opt.rmax is not None \
                and -INT32 <= opt.rmin and opt.rmax <= INT32:
            w = QSpinBox()
            w.setRange(int(opt.rmin), int(opt.rmax))
            w.setValue(opt.value)
            return w, lambda: ("int", w.value())
        if opt.kind == "float" and opt.rmin is not None and opt.rmax is not None \
                and abs(opt.rmax) <= 1000:
            w = QDoubleSpinBox()
            w.setRange(float(opt.rmin), float(opt.rmax))
            w.setDecimals(4)
            w.setSingleStep(0.01)
            w.setValue(opt.value)
            return w, lambda: ("float", w.value())
        le = QLineEdit()
        if opt.kind == "string":
            le.setText(opt.value)
            return le, lambda: ("string", le.text())
        le.setText(opt.raw_value)
        if opt.kind == "int":
            le.setValidator(QIntValidator())
        elif opt.kind == "float":
            le.setValidator(QDoubleValidator())
        return le, lambda: ("raw", le.text())

    def save(self):
        self._collect()
        backup(self.doc.path)
        self.doc.save()


# =========================================================================
# View 4: RCON コンソール (起動中サーバーへコマンドを送る)
# =========================================================================
class RconView(QWidget):
    def __init__(self, props_map):
        super().__init__()
        self.client = None
        enabled = props_map.get("enable-rcon", "false") == "true"

        self.host = QLineEdit("127.0.0.1")
        self.port = QLineEdit(props_map.get("rcon.port", "25575"))
        self.pw = QLineEdit(props_map.get("rcon.password", ""))
        self.pw.setEchoMode(QLineEdit.Password)
        connect_btn = QPushButton("接続")
        connect_btn.clicked.connect(self.on_connect)

        conn_row = QHBoxLayout()
        conn_row.addWidget(QLabel("ホスト"))
        conn_row.addWidget(self.host)
        conn_row.addWidget(QLabel("ポート"))
        conn_row.addWidget(self.port)
        conn_row.addWidget(QLabel("パスワード"))
        conn_row.addWidget(self.pw, 1)
        conn_row.addWidget(connect_btn)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.cmd = QLineEdit()
        self.cmd.setPlaceholderText("コマンド (例: list / op Notch / say こんにちは)")
        self.cmd.returnPressed.connect(self.on_send)
        self.cmd.setEnabled(False)
        self.send_btn = QPushButton("送信")
        self.send_btn.clicked.connect(self.on_send)
        self.send_btn.setEnabled(False)
        cmd_row = QHBoxLayout()
        cmd_row.addWidget(self.cmd, 1)
        cmd_row.addWidget(self.send_btn)

        lay = QVBoxLayout(self)
        if not enabled:
            warn = QLabel("⚠ 接続には server.properties で enable-rcon=true と rcon.password を設定し、"
                          "サーバーを起動しておく必要があります。")
            warn.setWordWrap(True)
            warn.setStyleSheet("color:#b45309")
            lay.addWidget(warn)
        lay.addLayout(conn_row)
        lay.addWidget(self.log, 1)
        lay.addLayout(cmd_row)

    def on_connect(self):
        self.cleanup()
        try:
            self.client = rcon.RconClient(self.host.text().strip(),
                                          self.port.text().strip(), self.pw.text())
            self.log.appendPlainText(f"✅ 接続しました ({self.host.text()}:{self.port.text()})")
            self.cmd.setEnabled(True)
            self.send_btn.setEnabled(True)
        except Exception as e:
            self.log.appendPlainText(f"❌ 接続失敗: {e}")
            self.client = None

    def on_send(self):
        if not self.client:
            return
        cmd = self.cmd.text().strip()
        if not cmd:
            return
        self.log.appendPlainText(f"> {cmd}")
        try:
            self.log.appendPlainText(self.client.command(cmd) or "(応答なし)")
        except Exception as e:
            self.log.appendPlainText(f"❌ {e}")
            self.cmd.setEnabled(False)
            self.send_btn.setEnabled(False)
            self.client = None
        self.cmd.clear()

    def set_ja(self, on):
        pass

    def set_filter(self, text):
        pass

    def cleanup(self):
        if self.client:
            self.client.close()
            self.client = None


# =========================================================================
# メインウィンドウ(シェル)
# =========================================================================
KNOWN_JSON = ("ops.json", "whitelist.json", "banned-players.json", "banned-ips.json")


class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MC サーバー設定エディタ — デモ")
        self.resize(1000, 700)
        self.folder = None
        self.view = None
        self.props_map = {}

        open_btn = QPushButton("📂 サーバーフォルダを開く")
        open_btn.clicked.connect(self.on_open)
        save_btn = QPushButton("💾 保存")
        save_btn.clicked.connect(self.on_save)
        rcon_btn = QPushButton("🎮 RCON")
        rcon_btn.clicked.connect(self.show_rcon)
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔎 絞り込み")
        self.search.textChanged.connect(lambda t: self.view and self.view.set_filter(t))
        self.ja = QCheckBox("🇯🇵 日本語解説")
        self.ja.toggled.connect(lambda on: self.view and self.view.set_ja(on))

        top = QHBoxLayout()
        top.addWidget(open_btn)
        top.addWidget(save_btn)
        top.addWidget(rcon_btn)
        top.addWidget(self.search, 1)
        top.addWidget(self.ja)

        self.filelist = QListWidget()
        self.filelist.setMaximumWidth(240)
        self.filelist.currentItemChanged.connect(self._on_select)

        self.host = QWidget()
        self.host_layout = QVBoxLayout(self.host)
        self.host_layout.setContentsMargins(0, 0, 0, 0)

        split = QSplitter()
        split.addWidget(self.filelist)
        split.addWidget(self.host)
        split.setStretchFactor(1, 1)

        self.status = QLabel("")
        self.status.setStyleSheet("color:#16a34a")

        root = QVBoxLayout()
        root.addLayout(top)
        root.addWidget(split, 1)
        root.addWidget(self.status)
        central = QWidget()
        central.setLayout(root)
        self.setCentralWidget(central)

        self.setAcceptDrops(True)
        if os.path.isdir(DEFAULT_SERVER):
            self.open_folder(DEFAULT_SERVER)

    def on_open(self):
        path = QFileDialog.getExistingDirectory(self, "サーバーフォルダを開く", HERE)
        if path:
            self.open_folder(path)

    # フォルダ(またはその中のファイル)をドラッグ&ドロップして開く
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            p = url.toLocalFile()
            folder = p if os.path.isdir(p) else os.path.dirname(p)
            if folder:
                self.open_folder(folder)
                break

    def open_folder(self, folder):
        self.folder = folder
        self.props_map = {}
        sp = os.path.join(folder, "server.properties")
        if os.path.isfile(sp):
            for p in propconf.PropertiesDoc(sp).props:
                self.props_map[p.key] = p.raw_value
        self.filelist.clear()
        for path in self._scan(folder):
            item = QListWidgetItem(os.path.relpath(path, folder).replace("\\", "/"))
            item.setData(Qt.UserRole, path)
            self.filelist.addItem(item)
        self.status.setText(f"{self.filelist.count()} 個の設定ファイルを検出: {folder}")
        if self.filelist.count():
            self.filelist.setCurrentRow(0)

    @staticmethod
    def _scan(folder):
        found = []
        sp = os.path.join(folder, "server.properties")
        if os.path.isfile(sp):
            found.append(sp)
        for name in KNOWN_JSON:
            p = os.path.join(folder, name)
            if os.path.isfile(p):
                found.append(p)
        found += sorted(glob.glob(os.path.join(folder, "config", "**", "*.toml"), recursive=True))
        return found

    def _on_select(self, item, _prev):
        if item is None:
            return
        self.show_file(item.data(Qt.UserRole))

    def _set_view(self, widget):
        if self.view is not None:
            if hasattr(self.view, "cleanup"):
                self.view.cleanup()
            self.view.setParent(None)
        self.view = widget
        self.view.set_ja(self.ja.isChecked())
        self.view.set_filter(self.search.text())
        self.host_layout.addWidget(self.view)

    def show_file(self, path):
        base = os.path.basename(path)
        if base == "server.properties":
            self._set_view(PropsView(path))
        elif base.endswith(".json"):
            self._set_view(PlayersView(path))
        else:
            self._set_view(TomlView(path))

    def show_rcon(self):
        self.filelist.clearSelection()
        self._set_view(RconView(self.props_map))

    def on_save(self):
        if self.view is None or not hasattr(self.view, "save"):
            self.status.setText("このビューには保存対象がありません（RCONはリアルタイム反映）")
            return
        try:
            self.view.save()
            self.status.setText("保存しました（同フォルダに .bak を作成）")
        except Exception as e:
            self.status.setText(f"保存失敗: {e}")


def main():
    app = QApplication(sys.argv)
    w = Main()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
