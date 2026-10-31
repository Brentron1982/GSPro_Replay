"""Desktop GUI for gspro-replay (tkinter, no extra dependencies).

Launch with:  gspro-replay-gui    or    python -m gspro_replay gui
Jobs run as child processes of the CLI so they can be cancelled and their
output streamed into the log.
"""
from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

SETTINGS = Path.home() / ".gspro-replay-gui.json"
ACCENT = "#e8352c"
STYLES = {"Low-poly": "lowpoly", "Realistic": "realistic", "Satellite facets": "satellite", "Aerial photo": "photo",
          "Cartoon": "toon", "Yardage book": "yardage", "Blueprint": "blueprint", "Night": "night",
          "Golden hour": "sunset", "Autumn": "autumn", "Winter": "winter", "Links (fescue)": "links"}
CAMERAS = {"TV broadcast": "broadcast", "Map (top-down)": "map", "Follow": "follow", "Overhead": "overhead"}
RESOLUTIONS = {"720p": (1280, 720), "1080p": (1920, 1080), "1440p": (2560, 1440), "4K": (3840, 2160)}
ELEVATION = {"USGS 3DEP 1 m (lidar DEM, US)": "3dep", "USGS lidar point clouds (real trees, big download)": "lidar",
             "Global terrain tiles (outside US)": "terrarium"}


def _python():
    if os.environ.get("GSPRO_REPLAY_PYTHON"):
        return os.environ["GSPRO_REPLAY_PYTHON"]
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe" and (exe.parent / "python.exe").exists():
        return str(exe.parent / "python.exe")
    return str(exe)


def _open_path(p):
    p = str(p)
    if sys.platform.startswith("win"):
        os.startfile(p)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", p])
    else:
        subprocess.Popen(["xdg-open", p])


def _slug(s):
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower() or "replay"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("GSPro Replay")
        self.geometry("1280x860")
        self.minsize(1000, 700)
        self.proc = None
        self.q = queue.Queue()
        self.settings = self._load()
        self._style()
        self._vars()
        self._layout()
        self.after(80, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._close)
        if self.v_shots.get() and Path(self.v_shots.get()).exists():
            self._inspect(self.v_shots.get(), quiet=True)

    # ---------------------------------------------------------------- setup
    def _style(self):
        st = ttk.Style(self)
        if "vista" in st.theme_names():
            st.theme_use("vista")
        elif "clam" in st.theme_names():
            st.theme_use("clam")
        st.configure("Title.TLabel", font=("Segoe UI", 18, "bold"))
        st.configure("Sub.TLabel", foreground="#666")
        st.configure("Info.TLabel", foreground="#1a6b2f")
        st.configure("Big.TButton", font=("Segoe UI", 11, "bold"), padding=(14, 5))
        st.configure("TLabelframe.Label", font=("Segoe UI", 10, "bold"))

    def _vars(self):
        s = self.settings
        self.v_shots = tk.StringVar(value=s.get("shots", ""))
        self.v_course = tk.StringVar(value=s.get("course", ""))
        self.v_near = tk.StringVar(value=s.get("near", ""))
        self.v_bbox = tk.StringVar(value="")
        self.v_player = tk.StringVar(value=s.get("player", ""))
        self.v_title = tk.StringVar(value="")
        self.v_out = tk.StringVar(value=s.get("out", ""))
        self.v_elev = tk.StringVar(value=s.get("elev", list(ELEVATION)[0]))
        self.v_imagery = tk.BooleanVar(value=s.get("imagery", True))
        self.v_autoputt = tk.BooleanVar(value=s.get("autoputt", True))
        self.v_detail = tk.DoubleVar(value=s.get("detail", 1.0))
        self.v_trees = tk.DoubleVar(value=s.get("trees", 1.0))
        self.v_pace = tk.DoubleVar(value=s.get("pace", 1.0))
        self.v_holes = tk.StringVar(value="")
        self.v_scorecard = tk.StringVar(value="")
        self.v_pins = tk.StringVar(value="")
        self.v_then_export = tk.BooleanVar(value=s.get("then_export", False))
        self.v_res = tk.StringVar(value=s.get("res", "1080p"))
        self.v_fps = tk.StringVar(value=s.get("fps", "30"))
        self.v_look = tk.StringVar(value=s.get("look", "Low-poly"))
        self.v_cam = tk.StringVar(value=s.get("cam", "TV broadcast"))
        self.v_speed = tk.StringVar(value=s.get("speed", "1"))
        self.v_vholes = tk.StringVar(value="")
        self.v_mp4 = tk.StringVar(value="")
        self.v_info = tk.StringVar(value="Choose the PlayerShots CSV that GSPro exported.")
        self.v_status = tk.StringVar(value="Ready")

    def _row(self, parent, r, label, widget, hint=None, button=None):
        ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", padx=(10, 8), pady=2)
        widget.grid(row=r, column=1, sticky="ew", pady=2)
        if button:
            button.grid(row=r, column=2, sticky="w", padx=(6, 10), pady=2)
        if hint:
            ttk.Label(parent, text=hint, style="Sub.TLabel").grid(row=r, column=3 if button else 2, sticky="w", padx=(6, 10))

    def _layout(self):
        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=3, minsize=600)
        outer.columnconfigure(1, weight=2, minsize=340)
        outer.rowconfigure(0, weight=1)
        root = ttk.Frame(outer)
        root.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        root.columnconfigure(0, weight=1)
        side = ttk.Frame(outer)
        side.grid(row=0, column=1, sticky="nsew")
        side.columnconfigure(0, weight=1)
        side.rowconfigure(2, weight=1)

        head = ttk.Frame(root)
        head.grid(row=0, column=0, sticky="ew")
        cv = tk.Canvas(head, width=44, height=44, highlightthickness=0, bg=self.cget("bg"))
        cv.create_oval(4, 4, 40, 40, fill=ACCENT, outline="")
        cv.create_line(22, 34, 22, 12, fill="white", width=2)
        cv.create_polygon(22, 12, 33, 16, 22, 20, fill="white")
        cv.pack(side="left", padx=(0, 10))
        ttk.Label(head, text="GSPro Replay", style="Title.TLabel").pack(side="left")
        ttk.Button(head, text="Try the demo", command=self.run_demo).pack(side="right")

        # 1. shots
        f1 = ttk.LabelFrame(root, text="1  Your round", padding=(4, 3))
        f1.grid(row=1, column=0, sticky="ew", pady=(8, 3))
        f1.columnconfigure(1, weight=1)
        self._row(f1, 0, "Shots CSV", ttk.Entry(f1, textvariable=self.v_shots),
                  button=ttk.Button(f1, text="Browse…", command=self.pick_shots))
        ttk.Label(f1, textvariable=self.v_info, style="Info.TLabel", wraplength=560).grid(row=1, column=1, columnspan=3, sticky="w", pady=(0, 4))
        self._row(f1, 2, "Player name", ttk.Entry(f1, textvariable=self.v_player, width=28))

        # 2. course
        f2 = ttk.LabelFrame(root, text="2  Course", padding=(4, 3))
        f2.grid(row=2, column=0, sticky="ew", pady=3)
        f2.columnconfigure(1, weight=1)
        self._row(f2, 0, "Course name", ttk.Entry(f2, textvariable=self.v_course), "filled in from the CSV")
        self._row(f2, 1, "Town / state", ttk.Entry(f2, textvariable=self.v_near), "helps find the right course")

        # 3. options
        f3 = ttk.LabelFrame(root, text="3  Options", padding=(4, 3))
        f3.grid(row=3, column=0, sticky="ew", pady=3)
        f3.columnconfigure(1, weight=1)
        self._row(f3, 0, "Elevation", ttk.Combobox(f3, textvariable=self.v_elev, values=list(ELEVATION), state="readonly"))
        chk = ttk.Frame(f3)
        ttk.Checkbutton(chk, text="Aerial imagery", variable=self.v_imagery).pack(side="left")
        ttk.Checkbutton(chk, text="Finish holes with auto putts", variable=self.v_autoputt).pack(side="left", padx=16)
        self._row(f3, 1, "", chk)
        self._scale(f3, 2, "Polygon size", self.v_detail, 0.5, 2.0, "smaller = more detail")
        self._scale(f3, 3, "Tree density", self.v_trees, 0.0, 2.0)
        adv = ttk.Frame(f3)
        adv.grid(row=4, column=0, columnspan=4, sticky="ew")
        adv.columnconfigure(1, weight=1)
        self.adv_open = tk.BooleanVar(value=False)
        self.adv_btn = ttk.Checkbutton(adv, text="Advanced ▸", variable=self.adv_open, command=self._toggle_adv)
        self.adv_btn.grid(row=0, column=0, sticky="w", padx=8, pady=(2, 0))
        self.adv = ttk.Frame(adv)
        self.adv.columnconfigure(1, weight=1)
        self._row(self.adv, 0, "Only holes", ttk.Entry(self.adv, textvariable=self.v_holes, width=16), "e.g. 1-9 or 1,2,18")
        self._row(self.adv, 1, "Scorecard", ttk.Entry(self.adv, textvariable=self.v_scorecard), "strokes per hole: 4,5,3,…")
        self._row(self.adv, 2, "Pins file", ttk.Entry(self.adv, textvariable=self.v_pins),
                  button=ttk.Button(self.adv, text="Browse…", command=lambda: self._pick_into(self.v_pins, [("JSON", "*.json")])))
        self._row(self.adv, 3, "Bounding box", ttk.Entry(self.adv, textvariable=self.v_bbox), "south,west,north,east")
        self._row(self.adv, 4, "Title", ttk.Entry(self.adv, textvariable=self.v_title), "shown in the replay")
        self._scale(self.adv, 5, "Pause length", self.v_pace, 0.4, 1.6, "between shots")

        # 4. build
        f4 = ttk.LabelFrame(root, text="4  Build the replay", padding=(4, 3))
        f4.grid(row=4, column=0, sticky="ew", pady=3)
        f4.columnconfigure(1, weight=1)
        self._row(f4, 0, "Output folder", ttk.Entry(f4, textvariable=self.v_out),
                  button=ttk.Button(f4, text="Browse…", command=self.pick_out))
        b4 = ttk.Frame(f4)
        b4.grid(row=1, column=0, columnspan=4, sticky="ew", padx=10, pady=(6, 2))
        self.btn_build = ttk.Button(b4, text="Build replay", style="Big.TButton", command=self.build)
        self.btn_build.pack(side="left")
        ttk.Checkbutton(b4, text="then make the MP4", variable=self.v_then_export).pack(side="left", padx=12)
        self.btn_folder = ttk.Button(b4, text="Open folder", command=lambda: self._open_out(None))
        self.btn_folder.pack(side="right")
        self.btn_open = ttk.Button(b4, text="Watch replay", command=self.open_replay)
        self.btn_open.pack(side="right", padx=6)

        # 5. video
        f5 = ttk.LabelFrame(root, text="5  Make the video", padding=(4, 3))
        f5.grid(row=5, column=0, sticky="ew", pady=3)
        f5.columnconfigure(1, weight=1)
        opts = ttk.Frame(f5)
        for lab, var, vals, w in (("Resolution", self.v_res, list(RESOLUTIONS), 7), ("FPS", self.v_fps, ["24", "30", "60"], 4),
                                  ("Look", self.v_look, list(STYLES), 16), ("Speed", self.v_speed, ["0.75", "1", "1.5", "2", "3"], 5)):
            ttk.Label(opts, text=lab).pack(side="left", padx=(0, 4))
            ttk.Combobox(opts, textvariable=var, values=vals, width=w, state="readonly").pack(side="left", padx=(0, 12))
        self._row(f5, 0, "Settings", opts)
        opts2 = ttk.Frame(f5)
        ttk.Label(opts2, text="Camera").pack(side="left", padx=(0, 4))
        ttk.Combobox(opts2, textvariable=self.v_cam, values=list(CAMERAS), width=16, state="readonly").pack(side="left", padx=(0, 12))
        ttk.Label(opts2, text="Holes").pack(side="left", padx=(0, 4))
        ttk.Entry(opts2, textvariable=self.v_vholes, width=10).pack(side="left")
        ttk.Label(opts2, text="blank = all, or 1-9", style="Sub.TLabel").pack(side="left", padx=6)
        self._row(f5, 1, "", opts2)
        self._row(f5, 2, "Save as", ttk.Entry(f5, textvariable=self.v_mp4),
                  button=ttk.Button(f5, text="Browse…", command=self.pick_mp4))
        b5 = ttk.Frame(f5)
        b5.grid(row=3, column=0, columnspan=4, sticky="ew", padx=10, pady=(6, 2))
        self.btn_export = ttk.Button(b5, text="Export MP4", style="Big.TButton", command=self.export)
        self.btn_export.pack(side="left")
        self.btn_play = ttk.Button(b5, text="Play video", command=lambda: self._open_file(self.v_mp4.get()))
        self.btn_play.pack(side="right")

        # progress + log (right column)
        ttk.Label(side, text="Progress", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(10, 4))
        pf = ttk.Frame(side)
        pf.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        pf.columnconfigure(0, weight=1)
        self.pbar = ttk.Progressbar(pf, mode="determinate", maximum=1000)
        self.pbar.grid(row=0, column=0, sticky="ew")
        self.btn_cancel = ttk.Button(pf, text="Cancel", command=self.cancel, state="disabled")
        self.btn_cancel.grid(row=0, column=1, padx=(8, 0))
        ttk.Label(pf, textvariable=self.v_status, style="Sub.TLabel", wraplength=320).grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 0))
        self.log = ScrolledText(side, height=10, width=40, font=("Consolas", 9), bg="#0f1419", fg="#cfd8dc",
                                insertbackground="white", relief="flat", wrap="word")
        self.log.grid(row=2, column=0, sticky="nsew")
        self.log.tag_configure("err", foreground="#ff8a80")
        self.log.tag_configure("ok", foreground="#9ccc65")
        self.log.tag_configure("step", foreground="#81d4fa")
        self._log("Welcome!\n1) Pick the PlayerShots CSV GSPro exported\n2) Check the course name and town\n3) Build replay, then Export MP4\n", "ok")

    def _scale(self, parent, r, label, var, lo, hi, hint=None):
        fr = ttk.Frame(parent)
        val = ttk.Label(fr, width=5)
        sc = ttk.Scale(fr, from_=lo, to=hi, variable=var, command=lambda _=None: val.configure(text=f"{var.get():.2f}"))
        sc.pack(side="left", fill="x", expand=True)
        val.pack(side="left", padx=6)
        val.configure(text=f"{var.get():.2f}")
        self._row(parent, r, label, fr, hint)

    def _toggle_adv(self):
        if self.adv_open.get():
            self.adv.grid(row=1, column=0, columnspan=4, sticky="ew")
            self.adv_btn.configure(text="Advanced ▾")
        else:
            self.adv.grid_remove()
            self.adv_btn.configure(text="Advanced ▸")

    # ---------------------------------------------------------------- pickers
    def _pick_into(self, var, types):
        p = filedialog.askopenfilename(filetypes=types + [("All files", "*.*")])
        if p:
            var.set(p)

    def pick_shots(self):
        start = Path(self.v_shots.get()).parent if self.v_shots.get() else Path.home()
        p = filedialog.askopenfilename(initialdir=start, title="GSPro shots file",
                                       filetypes=[("Shot files", "*.csv *.jsonl *.json"), ("All files", "*.*")])
        if p:
            self.v_shots.set(p)
            self._inspect(p)

    def pick_out(self):
        p = filedialog.askdirectory(initialdir=self.v_out.get() or Path.home())
        if p:
            self.v_out.set(p)
            self._default_mp4(force=True)

    def pick_mp4(self):
        p = filedialog.asksaveasfilename(defaultextension=".mp4", filetypes=[("MP4 video", "*.mp4")],
                                         initialfile=Path(self.v_mp4.get()).name or "round.mp4")
        if p:
            self.v_mp4.set(p)

    def _inspect(self, path, quiet=False):
        """Read the shots file in-process to show a summary and prefill fields."""
        try:
            import io
            from contextlib import redirect_stdout
            from . import shots
            shots.META.clear()
            with redirect_stdout(io.StringIO()):
                holes = shots.load(path)
            n = sum(len(v) for v in holes.values())
            meta = dict(shots.META)
            course = meta.get("course_name", "")
            date = meta.get("round_date", "").split("(")[0].strip()
            hs = sorted(holes)
            span = f"hole {hs[0]}" if len(hs) == 1 else f"holes {hs[0]}–{hs[-1]} ({len(hs)})"
            putts = sum(1 for v in holes.values() for s in v if s.is_putt)
            untracked = sum(1 for v in holes.values() for s in v if s.auto)
            n = sum(1 for v in holes.values() for s in v if not s.auto)
            self.v_info.set(f"✓ {n} shots on {span}" + (f" · {course}" if course else "") + (f" · {date}" if date else "")
                            + (f" · {untracked} strokes GSPro counted but didn't export (mostly putts) will be filled in" if untracked
                               else "" if putts else " · no putts recorded (auto putts will finish holes)"))
            if course and (not self.v_course.get() or not quiet):
                self.v_course.set(course)
            if not self.v_out.get() or not quiet:
                self.v_out.set(str(Path(path).parent / _slug(course or Path(path).stem)))
            self._default_mp4(force=not quiet)
        except BaseException as e:  # noqa: BLE001 - SystemExit from the loader too
            self.v_info.set(f"⚠ Couldn't read that file: {e}")

    def _default_mp4(self, force=False):
        if self.v_out.get() and (force or not self.v_mp4.get()):
            out = Path(self.v_out.get())
            self.v_mp4.set(str(out.parent / f"{out.name}.mp4"))

    # ---------------------------------------------------------------- jobs
    def _common_build_args(self):
        a = ["build", "--shots", self.v_shots.get(), "--out", self.v_out.get(),
             "--detail", f"{self.v_detail.get():.2f}", "--tree-density", f"{self.v_trees.get():.2f}",
             "--pace", f"{self.v_pace.get():.2f}"]
        if self.v_bbox.get().strip():
            a += ["--bbox", self.v_bbox.get().strip()]
        if self.v_course.get().strip():
            a += ["--course", self.v_course.get().strip()]
        if self.v_near.get().strip():
            a += ["--near", self.v_near.get().strip()]
        for flag, var in (("--player", self.v_player), ("--title", self.v_title), ("--holes", self.v_holes),
                          ("--scorecard", self.v_scorecard), ("--pins", self.v_pins)):
            if var.get().strip():
                a += [flag, var.get().strip()]
        elev = ELEVATION.get(self.v_elev.get(), "3dep")
        if elev == "lidar":
            a += ["--lidar", "auto"]
        else:
            a += ["--dem", elev]
        if not self.v_imagery.get():
            a.append("--no-imagery")
        if not self.v_autoputt.get():
            a.append("--no-auto-putt")
        return a

    def _export_args(self, replay):
        w, h = RESOLUTIONS[self.v_res.get()]
        a = ["export", str(replay), "-o", self.v_mp4.get(), "--width", str(w), "--height", str(h),
             "--fps", self.v_fps.get(), "--style", STYLES[self.v_look.get()], "--speed", self.v_speed.get(),
             "--camera", CAMERAS.get(self.v_cam.get(), "broadcast")]
        if self.v_vholes.get().strip():
            a += ["--holes", self.v_vholes.get().strip()]
        return a

    def build(self):
        if not self.v_shots.get() or not Path(self.v_shots.get()).exists():
            return messagebox.showwarning("GSPro Replay", "Choose your shots CSV first.")
        if not self.v_out.get():
            return messagebox.showwarning("GSPro Replay", "Choose an output folder.")
        if not (self.v_course.get().strip() or self.v_bbox.get().strip()):
            return messagebox.showwarning("GSPro Replay", "Enter the course name (or a bounding box under Advanced).")
        self._save()
        jobs = [self._common_build_args()]
        if self.v_then_export.get():
            jobs.append(self._export_args(Path(self.v_out.get()) / "replay.html"))
        self._run(jobs, done=self._after_build)

    def export(self):
        replay = Path(self.v_out.get() or ".") / "replay.html"
        if not replay.exists():
            p = filedialog.askopenfilename(title="Choose a replay.html", filetypes=[("Replay", "replay.html *.html")])
            if not p:
                return
            replay = Path(p)
            self.v_out.set(str(replay.parent))
        self._default_mp4()
        self._save()
        self._run([self._export_args(replay)], done=self._after_export)

    def run_demo(self):
        out = Path.home() / "gspro-replay-demo"
        self.v_out.set(str(out))
        self.v_mp4.set(str(out.parent / "gspro-replay-demo.mp4"))
        self._run([["demo", "--out", str(out)]], done=lambda ok: ok and self.open_replay())

    def _run(self, jobs, done=None):
        if self.proc:
            return
        self._busy(True)
        self.pbar.configure(mode="indeterminate")
        self.pbar.start(12)

        def worker():
            ok = True
            for args in jobs:
                cmd = [_python(), "-u", "-m", "gspro_replay", *args]
                self.q.put(("log", "\n$ gspro-replay " + " ".join(f'"{x}"' if " " in x else x for x in args) + "\n", "step"))
                flags = 0x08000000 if sys.platform.startswith("win") else 0  # CREATE_NO_WINDOW
                pkg_root = str(Path(__file__).resolve().parent.parent)
                env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8",
                           PYTHONPATH=pkg_root + os.pathsep + os.environ.get("PYTHONPATH", ""))
                try:
                    self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env,
                                                 creationflags=flags, bufsize=0, cwd=pkg_root)
                except OSError as e:
                    self.q.put(("log", f"Could not start: {e}\n", "err"))
                    ok = False
                    break
                buf = b""
                pending_cr = False
                while True:
                    ch = self.proc.stdout.read(1)
                    if not ch:
                        break
                    if pending_cr:
                        pending_cr = False
                        line = buf.decode("utf-8", "replace")
                        buf = b""
                        # "\r\n" is an ordinary Windows line end; a bare "\r" is a progress update
                        if line.strip():
                            self.q.put(("line", line, ch != b"\n"))
                        if ch == b"\n":
                            continue
                    if ch == b"\r":
                        pending_cr = True
                    elif ch == b"\n":
                        line = buf.decode("utf-8", "replace")
                        buf = b""
                        if line.strip():
                            self.q.put(("line", line, False))
                    else:
                        buf += ch
                if buf.strip():
                    self.q.put(("line", buf.decode("utf-8", "replace"), False))
                rc = self.proc.wait()
                cancelled = getattr(self.proc, "_cancelled", False)
                self.proc = None
                if rc != 0:
                    self.q.put(("log", "Cancelled.\n" if cancelled else f"Stopped with an error (code {rc}). See the messages above.\n", "err"))
                    if not cancelled:
                        self.q.put(("fail", None))
                    ok = False
                    break
            self.q.put(("done", ok, done))

        threading.Thread(target=worker, daemon=True).start()

    def cancel(self):
        if self.proc:
            self.proc._cancelled = True
            self.proc.terminate()

    # ---------------------------------------------------------------- results
    def _after_build(self, ok):
        if ok:
            self._log(f"✓ Replay ready: {Path(self.v_out.get()) / 'replay.html'}\n", "ok")
            if not self.v_then_export.get():
                self.open_replay()
            else:
                self._after_export(ok)

    def _after_export(self, ok):
        if ok and Path(self.v_mp4.get()).exists():
            self._log(f"✓ Video saved: {self.v_mp4.get()}\n", "ok")
            if messagebox.askyesno("GSPro Replay", "Video finished. Play it now?"):
                self._open_file(self.v_mp4.get())

    def open_replay(self):
        p = Path(self.v_out.get() or ".") / "replay.html"
        if p.exists():
            webbrowser.open(p.resolve().as_uri())
        else:
            messagebox.showinfo("GSPro Replay", "No replay built yet in that folder.")

    def _open_out(self, _):
        p = Path(self.v_out.get() or ".")
        if p.exists():
            _open_path(p)

    def _open_file(self, p):
        if p and Path(p).exists():
            _open_path(p)
        else:
            messagebox.showinfo("GSPro Replay", "That file doesn't exist yet.")

    # ---------------------------------------------------------------- plumbing
    def _busy(self, busy):
        for b in (self.btn_build, self.btn_export):
            b.configure(state="disabled" if busy else "normal")
        self.btn_cancel.configure(state="normal" if busy else "disabled")

    def _log(self, text, tag=None):
        self.log.insert("end", text, tag)
        self.log.see("end")

    def _poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                kind = msg[0]
                if kind == "log":
                    self._log(msg[1], msg[2])
                elif kind == "line":
                    self._line(msg[1], msg[2])
                elif kind == "fail":
                    lines = self.log.get("1.0", "end").strip().splitlines()
                    starts = [i for i, l in enumerate(lines) if l.startswith("$ gspro-replay")]
                    tail = [l for l in lines[(starts[-1] + 1 if starts else 0):] if not l.startswith("Stopped with")][-12:]
                    messagebox.showerror("GSPro Replay", "The job stopped with an error:\n\n" + "\n".join(tail))
                elif kind == "done":
                    _, ok, cb = msg
                    self.pbar.stop()
                    self.pbar.configure(mode="determinate", value=1000 if ok else 0)
                    self.v_status.set("Done" if ok else "Stopped")
                    self._busy(False)
                    if cb:
                        cb(ok)
        except queue.Empty:
            pass
        self.after(80, self._poll)

    def _line(self, line, is_progress):
        m = re.search(r"(\d+)/(\d+) frames\s+([\d.]+) fps\s+ETA (\S+)", line)
        if m:
            i, n = int(m.group(1)), int(m.group(2))
            if str(self.pbar.cget("mode")) != "determinate":
                self.pbar.stop()
                self.pbar.configure(mode="determinate")
            self.pbar.configure(value=1000 * i / max(1, n))
            self.v_status.set(f"Rendering video: {i:,} / {n:,} frames ({100 * i // max(1, n)}%) · {m.group(3)} fps · {m.group(4)} remaining")
            return
        if is_progress:  # other carriage-return progress (downloads)
            self.v_status.set(line.strip())
            return
        s = line.rstrip()
        if s.startswith("•"):
            self.v_status.set(s.lstrip("• ").strip())
            self._log(s + "\n", "step")
        elif "Traceback" in s or "Error" in s or s.startswith(("!", "  !")) or "failed" in s.lower():
            self._log(s + "\n", "err")
        else:
            self._log(s + "\n")

    def _load(self):
        try:
            return json.loads(SETTINGS.read_text())
        except Exception:  # noqa: BLE001
            return {}

    def _save(self):
        d = dict(shots=self.v_shots.get(), course=self.v_course.get(), near=self.v_near.get(), player=self.v_player.get(),
                 out=self.v_out.get(), elev=self.v_elev.get(), imagery=self.v_imagery.get(), autoputt=self.v_autoputt.get(),
                 detail=self.v_detail.get(), trees=self.v_trees.get(), pace=self.v_pace.get(),
                 then_export=self.v_then_export.get(), res=self.v_res.get(), fps=self.v_fps.get(), look=self.v_look.get(), cam=self.v_cam.get(),
                 speed=self.v_speed.get())
        try:
            SETTINGS.write_text(json.dumps(d, indent=1))
        except OSError:
            pass

    def _close(self):
        if self.proc and not messagebox.askyesno("GSPro Replay", "A job is still running. Stop it and quit?"):
            return
        self.cancel()
        self._save()
        self.destroy()


def main():
    try:
        App().mainloop()
    except Exception:  # noqa: BLE001 - pythonw has no console, so show the error
        import traceback
        err = traceback.format_exc()
        log = Path.home() / "gspro-replay-error.log"
        try:
            log.write_text(err)
        except OSError:
            pass
        msg = f"GSPro Replay could not start:\n\n{err[-1500:]}\n\n(saved to {log})"
        try:
            messagebox.showerror("GSPro Replay", msg)
        except Exception:  # noqa: BLE001
            if sys.platform.startswith("win"):
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, msg, "GSPro Replay", 0x10)
            else:
                print(msg, file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
