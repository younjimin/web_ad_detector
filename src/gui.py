"""탐지 결과 안내 화면 (Tkinter). URL 입력 -> 탐지 시작 -> 진행 상태 -> 결과 표/상세 -> 리포트·결과 파일 열기."""
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import webbrowser
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Dict, List, Optional

from report import COLORS, TECH_INFO, write_report
from result_writer import TOOL_VERSION
from scan_core import (DEFAULT_MAX_PAGES, DEFAULT_TIMEOUT_SEC, DEFAULT_WORKERS, base_dir, run_scan)

TECH_ORDER = ["HOMOGLYPH", "JAMO", "TRANSPARENT", "OFFSCREEN"]
COLUMNS = (("id", "ID", 60), ("tech", "유형", 120), ("url", "페이지 URL", 330), ("loc", "위치 (CSS 선택자)", 300), ("ev", "근거 원문", 260))


def open_path(path) -> None:
    """파일/폴더를 운영체제 기본 프로그램으로 연다."""
    path = str(path)
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)                      # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        messagebox.showerror("열 수 없음", f"{path}\n\n{e}")


class App:
    def __init__(self, root: tk.Tk, crawl_fn: Optional[Callable] = None, out_dir: Optional[Path] = None,
                 default_url: str = ""):
        self.root, self.crawl_fn = root, crawl_fn
        self.out_dir = Path(out_dir) if out_dir else base_dir()
        self.q: "queue.Queue" = queue.Queue()
        self.stop_flag = threading.Event()
        self.worker: Optional[threading.Thread] = None
        self.running, self.t0 = False, 0.0
        self.n_extra = 0
        self.rows: List[Dict] = []
        self.visible: List[Dict] = []
        self.last_ret: Optional[Dict] = None
        self.sort_col, self.sort_rev = None, False

        root.title(f"공공 웹사이트 불법광고 탐지 도구  v{TOOL_VERSION}")
        root.geometry("1180x800")
        root.minsize(940, 640)
        self._style()
        self._build(default_url)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(100, self.poll)

    def _style(self):
        import tkinter.font as tkfont
        fams = set(tkfont.families())
        self.font = next((f for f in ("Malgun Gothic", "맑은 고딕", "Noto Sans CJK KR", "NanumGothic") if f in fams), "TkDefaultFont")
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
            try:
                tkfont.nametofont(name).configure(family=self.font, size=10)
            except tk.TclError:
                pass
        st = ttk.Style()
        try:
            st.theme_use("vista" if "vista" in st.theme_names() else "clam")
        except tk.TclError:
            pass
        st.configure("Treeview", rowheight=26)
        st.configure("Title.TLabel", font=(self.font, 15, "bold"))
        st.configure("Go.TButton", font=(self.font, 10, "bold"))

    def _build(self, default_url: str):
        pad = {"padx": 12}
        top = ttk.Frame(self.root)
        top.pack(fill="x", pady=(12, 4), **pad)
        ttk.Label(top, text="공공 웹사이트 불법광고 탐지", style="Title.TLabel").pack(side="left")
        ttk.Label(top, text="닮은꼴 글자 · 자모 분해 · 투명 텍스트 · 화면 밖 은닉", foreground="#667").pack(side="left", padx=12)

        row = ttk.Frame(self.root)
        row.pack(fill="x", pady=4, **pad)
        ttk.Label(row, text="점검할 URL").pack(side="left")
        self.url_var = tk.StringVar(value=default_url)
        self.url_entry = ttk.Entry(row, textvariable=self.url_var)
        self.url_entry.pack(side="left", fill="x", expand=True, padx=8)
        self.url_entry.bind("<Return>", lambda e: self.start())
        self.btn_start = ttk.Button(row, text="탐지 시작", style="Go.TButton", command=self.start, width=12)
        self.btn_start.pack(side="left")
        self.btn_stop = ttk.Button(row, text="중지", command=self.stop, width=8, state="disabled")
        self.btn_stop.pack(side="left", padx=(6, 0))

        opt = ttk.LabelFrame(self.root, text="옵션")
        opt.pack(fill="x", pady=6, **pad)
        self.max_pages = tk.IntVar(value=DEFAULT_MAX_PAGES)
        self.workers = tk.IntVar(value=DEFAULT_WORKERS)
        self.minutes = tk.IntVar(value=int(DEFAULT_TIMEOUT_SEC // 60))
        self.opt_widgets = []
        for label, var, lo, hi in (("최대 페이지 수", self.max_pages, 1, 100000), ("동시 탭 수", self.workers, 1, 8),
                                   ("제한 시간(분)", self.minutes, 1, 28)):
            ttk.Label(opt, text=label).pack(side="left", padx=(10, 4), pady=6)
            sp = ttk.Spinbox(opt, from_=lo, to=hi, textvariable=var, width=7)
            sp.pack(side="left", padx=(0, 8))
            self.opt_widgets.append(sp)

        stat = ttk.Frame(self.root)
        stat.pack(fill="x", pady=(2, 4), **pad)
        self.status_var = tk.StringVar(value="URL 을 입력하고 [탐지 시작]을 누르세요.")
        ttk.Label(stat, textvariable=self.status_var).pack(side="left")
        self.elapsed_var = tk.StringVar(value="")
        ttk.Label(stat, textvariable=self.elapsed_var, foreground="#667").pack(side="right")
        self.bar = ttk.Progressbar(self.root, mode="indeterminate")
        self.bar.pack(fill="x", pady=(0, 6), **pad)

        sumf = ttk.Frame(self.root)
        sumf.pack(fill="x", pady=4, **pad)
        self.sum_labels: Dict[str, tk.Label] = {}
        for key, title, color in [("TOTAL", "총 탐지", "#222")] + [(t, TECH_INFO[t][0], COLORS[t]) for t in TECH_ORDER] \
                + [("ETC", "추가 탐지 (result_extra.json)", "#475569")]:
            box = tk.Frame(sumf, highlightbackground="#d5d9e0", highlightthickness=1, bg="white")
            box.pack(side="left", fill="x", expand=True, padx=(0, 8))
            n = tk.Label(box, text="0", font=(self.font, 20, "bold"), fg=color, bg="white")
            n.pack(anchor="w", padx=10, pady=(6, 0))
            tk.Label(box, text=title, font=(self.font, 9), fg="#556", bg="white").pack(anchor="w", padx=10, pady=(0, 6))
            self.sum_labels[key] = n

        bot = ttk.Frame(self.root)
        bot.pack(side="bottom", fill="x", pady=(2, 12), **pad)
        self.btn_report = ttk.Button(bot, text="HTML 리포트 열기", command=self.open_report, state="disabled")
        self.btn_report.pack(side="left")
        self.btn_json = ttk.Button(bot, text="result.json 열기", command=self.open_json, state="disabled")
        self.btn_json.pack(side="left", padx=6)
        ttk.Button(bot, text="결과 폴더 열기", command=lambda: open_path(self.out_dir)).pack(side="left")
        ttk.Button(bot, text="이전 결과 불러오기", command=self.load_result).pack(side="right")

        pan = ttk.PanedWindow(self.root, orient="vertical")
        pan.pack(fill="both", expand=True, pady=6, **pad)
        nb = ttk.Notebook(pan)
        pan.add(nb, weight=3)
        tab_res, tab_log = ttk.Frame(nb), ttk.Frame(nb)
        nb.add(tab_res, text="  탐지 결과  ")
        nb.add(tab_log, text="  진행 로그  ")

        fb = ttk.Frame(tab_res)
        fb.pack(fill="x", pady=6, padx=6)
        ttk.Label(fb, text="유형").pack(side="left")
        self.filter_var = tk.StringVar(value="전체")
        cb = ttk.Combobox(fb, textvariable=self.filter_var, state="readonly", width=22,
                          values=["전체"] + [f"{TECH_INFO[t][0]} ({t})" for t in TECH_ORDER])
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda e: self.refresh_table())
        ttk.Label(fb, text="검색").pack(side="left", padx=(12, 0))
        self.q_var = tk.StringVar()
        self.q_var.trace_add("write", lambda *a: self.refresh_table())
        ttk.Entry(fb, textvariable=self.q_var, width=30).pack(side="left", padx=6)
        self.count_var = tk.StringVar(value="")
        ttk.Label(fb, textvariable=self.count_var, foreground="#667").pack(side="right")

        tf = ttk.Frame(tab_res)
        tf.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.tree = ttk.Treeview(tf, columns=[c[0] for c in COLUMNS], show="headings", selectmode="browse")
        for key, title, w in COLUMNS:
            self.tree.heading(key, text=title, command=lambda k=key: self.sort_by(k))
            self.tree.column(key, width=w, anchor="w", stretch=key in ("url", "loc", "ev"))
        for t in TECH_ORDER:
            self.tree.tag_configure(t, foreground=COLORS[t])
        ys = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=ys.set)
        self.tree.pack(side="left", fill="both", expand=True)
        ys.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.show_detail())
        self.tree.bind("<Double-1>", lambda e: self.open_selected_page())

        self.log = tk.Text(tab_log, height=10, wrap="word", state="disabled", font=("Consolas", 9))
        lys = ttk.Scrollbar(tab_log, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=lys.set)
        self.log.pack(side="left", fill="both", expand=True)
        lys.pack(side="right", fill="y")

        det = ttk.LabelFrame(pan, text="선택한 항목의 상세 (더블클릭하면 해당 페이지를 브라우저로 엽니다)")
        pan.add(det, weight=1)
        self.detail = tk.Text(det, height=7, wrap="word", state="disabled", font=(self.font, 10), bg="#fafbfc")
        self.detail.pack(fill="both", expand=True, padx=6, pady=6)
        for t in TECH_ORDER:
            self.detail.tag_configure(t, foreground=COLORS[t], font=(self.font, 10, "bold"))
        self.detail.tag_configure("k", foreground="#667")
        self.detail.tag_configure("mono", font=("Consolas", 10))

    def start(self):
        if self.running:
            return
        url = self.url_var.get().strip()
        if not url.lower().startswith(("http://", "https://")):
            messagebox.showwarning("URL 확인", "URL 은 http:// 또는 https:// 로 시작해야 합니다.")
            return
        try:
            mp, wk, mins = int(self.max_pages.get()), int(self.workers.get()), int(self.minutes.get())
        except (tk.TclError, ValueError):
            messagebox.showwarning("옵션 확인", "옵션 값은 숫자여야 합니다.")
            return
        self.rows = []
        self.refresh_table()
        self.update_summary([])
        self._set_detail([])
        self.log_clear()
        self.stop_flag.clear()
        self.running, self.t0 = True, time.time()
        self.set_running_ui(True)
        self.status_var.set("탐지 중... 페이지를 찾아 검사하고 있습니다.")

        def work():
            try:
                ret = run_scan(url, max_pages=mp, timeout=float(mins * 60), workers=wk, out_dir=self.out_dir,
                               log=lambda s: self.q.put(("log", s)), should_stop=self.stop_flag.is_set,
                               crawl_fn=self.crawl_fn)
                self.q.put(("done", ret))
            except Exception as e:
                self.q.put(("fail", f"{type(e).__name__}: {e}"))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def stop(self):
        if self.running:
            self.stop_flag.set()
            self.btn_stop.configure(state="disabled")
            self.status_var.set("중지 요청됨 — 진행 중인 페이지를 마치고 지금까지의 결과를 정리합니다...")

    def set_running_ui(self, running: bool):
        self.btn_start.configure(state="disabled" if running else "normal")
        self.btn_stop.configure(state="normal" if running else "disabled")
        self.url_entry.configure(state="disabled" if running else "normal")
        for w in self.opt_widgets:
            w.configure(state="disabled" if running else "normal")
        if running:
            self.bar.start(12)
        else:
            self.bar.stop()

    def poll(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "log":
                    self.log_add(payload)
                    m = re.match(r"\[(\d+)/(\d+)\] 크롤링 중: (.*)", payload)
                    if m:
                        self.status_var.set(f"탐지 중... {m.group(1)}번째 페이지: {m.group(3)[:90]}")
                elif kind == "done":
                    self.finish(payload)
                elif kind == "fail":
                    self.running = False
                    self.set_running_ui(False)
                    self.status_var.set("오류로 중단되었습니다.")
                    messagebox.showerror("오류", payload)
        except queue.Empty:
            pass
        if self.running:
            self.elapsed_var.set(f"경과 {time.time() - self.t0:.0f}초")
        self.root.after(150, self.poll)

    def finish(self, ret: Dict):
        self.running = False
        self.set_running_ui(False)
        self.last_ret = ret
        result = ret["result"]
        self.elapsed_var.set(f"소요 {result['meta']['elapsed_sec']}초")
        self.n_extra = len((ret.get("extra") or {}).get("findings", []))
        self.load_rows(result, ret.get("details", {}))
        for b in (self.btn_report, self.btn_json):
            b.configure(state="normal")
        n = len(result["findings"])
        tail = " (사용자가 중지함)" if ret.get("stopped") else ""
        if ret.get("error"):
            self.status_var.set(f"오류가 있었지만 가능한 결과를 저장했습니다: {ret['error']}")
        else:
            more = f" (+추가 탐지 {self.n_extra}건: result_extra.json)" if self.n_extra else ""
            self.status_var.set(f"완료{tail} — {ret['pages']}개 페이지 검사, {n}건 탐지{more}. 결과 파일: {ret['result_path']}")

    def on_close(self):
        if self.running:
            if not messagebox.askyesno("종료", "탐지가 진행 중입니다. 중지하고 종료할까요?"):
                return
            self.stop_flag.set()
        self.root.destroy()

    def load_rows(self, result: Dict, details: Dict):
        self.rows = []
        for f in result["findings"]:
            self.rows.append({"id": f["id"], "tech": f["technique"], "url": f["url"], "loc": f["location"],
                              "ev": f["evidence_text"], "why": details.get((f["url"], f["location"], f["technique"]), "")})
        self.update_summary(result["findings"])
        self.sum_labels["ETC"].configure(text=str(self.n_extra))
        self.refresh_table()
        kids = self.tree.get_children()
        if kids:
            self.tree.selection_set(kids[0])

    def update_summary(self, findings: List[Dict]):
        self.sum_labels["TOTAL"].configure(text=str(len(findings)))
        for t in TECH_ORDER:
            self.sum_labels[t].configure(text=str(sum(1 for f in findings if f["technique"] == t)))

    def _filter_tech(self) -> Optional[str]:
        v = self.filter_var.get()
        for t in TECH_ORDER:
            if v.endswith(f"({t})"):
                return t
        return None

    def refresh_table(self):
        tech, q = self._filter_tech(), self.q_var.get().strip().lower()
        rows = [r for r in self.rows if (tech is None or r["tech"] == tech)
                and (not q or q in (r["url"] + r["loc"] + r["ev"] + r["id"]).lower())]
        if self.sort_col:
            rows.sort(key=lambda r: r[self.sort_col], reverse=self.sort_rev)
        self.tree.delete(*self.tree.get_children())
        self.visible = rows
        for i, r in enumerate(rows):
            ev = r["ev"].replace("\n", " ")
            self.tree.insert("", "end", iid=str(i), tags=(r["tech"],),
                             values=(r["id"], TECH_INFO.get(r["tech"], (r["tech"],))[0], r["url"], r["loc"],
                                     ev if len(ev) < 80 else ev[:77] + "..."))
        self.count_var.set(f"{len(rows)} / {len(self.rows)}건 표시")

    def sort_by(self, key: str):
        self.sort_rev = (not self.sort_rev) if self.sort_col == key else False
        self.sort_col = key
        self.refresh_table()

    def _selected(self) -> Optional[Dict]:
        sel = self.tree.selection()
        if not sel:
            return None
        try:
            return self.visible[int(sel[0])]
        except (IndexError, ValueError):
            return None

    def _set_detail(self, parts):
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        for text, tag in parts:
            self.detail.insert("end", text, tag)
        self.detail.configure(state="disabled")

    def show_detail(self):
        r = self._selected()
        if not r:
            return
        ko, desc = TECH_INFO.get(r["tech"], (r["tech"], ""))
        parts = [(f"{ko} ({r['tech']})\n", r["tech"]), (f"{desc}\n\n", "k"),
                 ("페이지  ", "k"), (r["url"] + "\n", ""), ("위치    ", "k"), (r["loc"] + "\n", "mono"),
                 ("근거    ", "k"), (r["ev"] + "\n", "")]
        if r["why"]:
            parts += [("판정 이유  ", "k"), (r["why"] + "\n", "")]
        self._set_detail(parts)

    def open_selected_page(self):
        r = self._selected()
        if r:
            webbrowser.open(r["url"])

    def log_add(self, line: str):
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        if int(self.log.index("end-1c").split(".")[0]) > 3000:
            self.log.delete("1.0", "500.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def log_clear(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def open_report(self):
        if self.last_ret and self.last_ret.get("report_path"):
            open_path(self.last_ret["report_path"])

    def open_json(self):
        if self.last_ret:
            open_path(self.last_ret["result_path"])

    def load_result(self):
        if self.running:
            return
        path = filedialog.askopenfilename(title="result.json 선택", initialdir=str(self.out_dir),
                                          filetypes=[("JSON", "*.json"), ("모든 파일", "*.*")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8-sig") as fp:
                result = json.load(fp)
            for f in result["findings"]:
                f["id"], f["url"], f["location"], f["technique"], f["evidence_text"]
        except Exception as e:
            messagebox.showerror("불러오기 실패", f"result.json 형식이 아닙니다.\n\n{e}")
            return
        self.n_extra = 0
        try:
            with open(Path(path).with_name("result_extra.json"), encoding="utf-8-sig") as fp:
                self.n_extra = len(json.load(fp)["findings"])
        except Exception:
            pass
        self.load_rows(result, {})
        rp = write_report(result, self.out_dir / "report.html")
        self.last_ret = {"result": result, "result_path": Path(path), "report_path": rp, "pages": "-", "details": {}}
        for b in (self.btn_report, self.btn_json):
            b.configure(state="normal")
        self.status_var.set(f"불러옴: {path}  ({len(result['findings'])}건, 진입 URL {result.get('meta', {}).get('entry_url', '')})")


def run_gui(crawl_fn=None, out_dir=None, default_url=""):
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    root = tk.Tk()
    App(root, crawl_fn=crawl_fn, out_dir=out_dir, default_url=default_url)
    root.mainloop()


if __name__ == "__main__":
    run_gui()
