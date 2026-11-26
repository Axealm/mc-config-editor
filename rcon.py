"""
rcon.py - Minecraft / Source RCON プロトコルのクライアント(標準ライブラリのみ)。

起動中のサーバーに TCP で接続し、コンソールコマンド(list, op など)を送って応答を得る。
サーバー側は server.properties で enable-rcon=true と rcon.password の設定が必要。

パケット形式(全て little-endian):
  [int32 length][int32 request-id][int32 type][body(ASCII)\\0][\\0]
  type: 3=認証リクエスト / 2=コマンド実行・認証応答 / 0=コマンド応答
  認証応答の request-id が -1 なら認証失敗。
"""
import socket
import struct

AUTH_REQUEST = 3
AUTH_RESPONSE = 2
EXEC_COMMAND = 2
RESPONSE_VALUE = 0


class RconError(Exception):
    pass


class RconClient:
    def __init__(self, host, port, password, timeout=5.0):
        self._id = 0
        self.sock = socket.create_connection((host, int(port)), timeout=timeout)
        self.sock.settimeout(timeout)
        self._authenticate(password)

    def _send(self, type_, body):
        self._id += 1
        rid = self._id
        payload = struct.pack("<ii", rid, type_) + body.encode("utf-8") + b"\x00\x00"
        self.sock.sendall(struct.pack("<i", len(payload)) + payload)
        return rid

    def _recv_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise RconError("接続が切れました")
            buf += chunk
        return buf

    def _recv(self):
        length = struct.unpack("<i", self._recv_exact(4))[0]
        data = self._recv_exact(length)
        rid, type_ = struct.unpack("<ii", data[:8])
        body = data[8:-2].decode("utf-8", "replace")
        return rid, type_, body

    def _authenticate(self, password):
        self._send(AUTH_REQUEST, password)
        for _ in range(3):                 # 一部実装は空の応答を先に返すので数回読む
            rid, type_, _ = self._recv()
            if type_ == AUTH_RESPONSE:
                if rid == -1:
                    raise RconError("認証失敗（rcon.password が違います）")
                return
        raise RconError("認証応答が返ってきませんでした")

    def command(self, cmd):
        self._send(EXEC_COMMAND, cmd)
        _, _, body = self._recv()
        return body

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass
