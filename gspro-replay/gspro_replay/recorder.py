"""Record a GSPro round by sitting between your launch-monitor connector and
GSPro's Open Connect API (TCP, default port 921).

    connector  --->  recorder (:9211)  --->  GSPro (:921)

Point your connector at port 9211 (most connectors have a port/IP setting),
start this, play your round. Every shot is appended to the JSONL file along
with the club and distance-to-target that GSPro last reported.
"""
from __future__ import annotations

import json
import socket
import threading
import time
from pathlib import Path


class _Stream:
    def __init__(self):
        self.buf = ""
        self.dec = json.JSONDecoder()

    def feed(self, text):
        self.buf += text
        out = []
        while True:
            s = self.buf.lstrip()
            if not s:
                self.buf = ""
                break
            try:
                obj, i = self.dec.raw_decode(s)
            except json.JSONDecodeError:
                self.buf = s
                break
            out.append(obj)
            self.buf = s[i:]
        return out


def run(listen_port=9211, gspro_host="127.0.0.1", gspro_port=921, out="round.jsonl"):
    out = Path(out)
    state = {"player": {}, "n": 0}
    lock = threading.Lock()
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", listen_port))
    srv.listen(1)
    print(f"Recorder listening on :{listen_port} -> GSPro {gspro_host}:{gspro_port}. Writing {out}")

    def pump(src, dst, from_connector):
        st = _Stream()
        while True:
            try:
                data = src.recv(65536)
            except OSError:
                break
            if not data:
                break
            try:
                dst.sendall(data)
            except OSError:
                break
            for msg in st.feed(data.decode("utf-8", "replace")):
                with lock:
                    if from_connector:
                        opts = msg.get("ShotDataOptions", {})
                        if msg.get("BallData") and opts.get("ContainsBallData", True) and not opts.get("IsHeartBeat"):
                            state["n"] += 1
                            rec = {"time": time.time(), "player": state["player"], "shot": msg}
                            with open(out, "a") as f:
                                f.write(json.dumps(rec) + "\n")
                            bd = msg["BallData"]
                            print(f"  shot {state['n']}: {state['player'].get('Club', '?')} "
                                  f"{bd.get('Speed', 0):.1f} mph  VLA {bd.get('VLA', 0):.1f}  HLA {bd.get('HLA', 0):.1f}")
                    elif isinstance(msg.get("Player"), dict):
                        state["player"] = msg["Player"]
        for s in (src, dst):
            try:
                s.close()
            except OSError:
                pass

    while True:
        c, addr = srv.accept()
        print(f"connector connected from {addr[0]}")
        g = socket.create_connection((gspro_host, gspro_port))
        threading.Thread(target=pump, args=(c, g, True), daemon=True).start()
        threading.Thread(target=pump, args=(g, c, False), daemon=True).start()
