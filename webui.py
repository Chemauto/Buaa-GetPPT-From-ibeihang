"""智学北航回放 PPT 提取工具——网页操作界面。

运行 `python webui.py` 会自动打开浏览器页面（http://127.0.0.1:8765），
在页面中粘贴回放链接即可开始提取，实时显示进度与日志，完成后可直接
查看 PDF / 打开输出文件夹。需要登录时工具会弹出浏览器窗口，完成一次
登录后长期有效。
"""

from __future__ import annotations

import os
import threading
import webbrowser
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request, send_file, send_from_directory

from buaa_ppt.extractor import SlideExtractor
from buaa_ppt.pdfgen import build_pdf

PROJECT_DIR = Path(__file__).resolve().parent
HTML_PATH = PROJECT_DIR / "buaa_ppt" / "webapp.html"
OUTPUT_ROOT = PROJECT_DIR / "output"
HOST, PORT = "127.0.0.1", 8765

app = Flask(__name__)


class JobState:
    """单个提取任务的实时状态（同一时刻只允许一个任务）。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._busy = False
        self._data = self._fresh()
        self.out_dir: Path | None = None

    @staticmethod
    def _fresh():
        return {
            "running": False,
            "stage": "准备中……",
            "done": 0,
            "total": 0,
            "log": [],
            "error": None,
            "result": None,
        }

    def start(self) -> bool:
        with self._lock:
            if self._busy:
                return False
            self._busy = True
            self._data = self._fresh()
            self._data["running"] = True
            return True

    def stage(self, text: str):
        with self._lock:
            self._data["stage"] = text

    def log(self, msg: str):
        with self._lock:
            log = self._data["log"]
            log.append(msg)
            if len(log) > 400:
                del log[: len(log) - 400]

    def progress(self, done: int, total: int):
        with self._lock:
            self._data["done"] = done
            self._data["total"] = total
            if total:
                self._data["stage"] = "正在下载原图……"

    def finish(self, out_dir: Path, pdf: Path, title: str):
        with self._lock:
            self._busy = False
            self._data["running"] = False
            self._data["stage"] = "完成"
            self._data["result"] = {
                "title": title,
                "pdf_name": pdf.name,
                "pdf_size": pdf.stat().st_size,
                "dir_name": out_dir.relative_to(OUTPUT_ROOT).as_posix(),
            }
        self.out_dir = out_dir

    def fail(self, msg: str):
        with self._lock:
            self._busy = False
            self._data["running"] = False
            self._data["error"] = msg

    def snapshot(self) -> dict:
        with self._lock:
            data = dict(self._data)
            data["log"] = list(self._data["log"])
            data["result"] = dict(self._data["result"]) if self._data["result"] else None
            return data

    def result(self) -> dict | None:
        with self._lock:
            return dict(self._data["result"]) if self._data["result"] else None


state = JobState()


def run_job(url: str, keep_duplicates: bool):
    try:
        out_dir = OUTPUT_ROOT / datetime.now().strftime("web_%Y%m%d_%H%M%S")
        state.stage("正在打开浏览器并加载回放页……")
        extractor = SlideExtractor(
            profile_dir=PROJECT_DIR / ".browser_profile",
            headless=False,
            log=lambda m: (print(m), state.log(m)),
        )
        slides, title, out_dir = extractor.extract(
            url=url,
            out_dir=out_dir,
            login_timeout_s=900,
            keep_duplicates=keep_duplicates,
            on_progress=state.progress,
        )
        if not slides:
            raise RuntimeError("未提取到任何幻灯片，请检查链接与登录状态。")
        state.stage(f"正在合成 PDF（共 {len(slides)} 页）……")
        pdf = build_pdf(out_dir, slides, title)
        state.finish(out_dir=out_dir, pdf=pdf, title=title)
        print(f"任务完成：{pdf}")
    except Exception as exc:  # noqa: BLE001 - 后台线程内统一收集错误
        state.fail(str(exc))
        print(f"任务失败：{exc}")


@app.get("/")
def index():
    return send_file(HTML_PATH)


@app.post("/api/extract")
def api_extract():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return jsonify({"error": "请输入有效的回放页链接（以 http/https 开头）"}), 400
    if not state.start():
        return jsonify({"error": "已有提取任务正在进行，请等待完成"}), 409
    threading.Thread(
        target=run_job,
        args=(url, bool(data.get("keep_duplicates", False))),
        daemon=True,
    ).start()
    return jsonify({"ok": True})


@app.get("/api/status")
def api_status():
    return jsonify(state.snapshot())


@app.get("/api/pdf")
def api_pdf():
    result = state.result()
    if not result:
        return jsonify({"error": "还没有已完成的任务"}), 404
    return send_from_directory(state.out_dir, result["pdf_name"])


@app.post("/api/open-folder")
def api_open_folder():
    if state.out_dir is None or not state.out_dir.exists():
        return jsonify({"error": "还没有输出目录"}), 404
    if os.name != "nt":
        return jsonify({"error": "当前系统不支持自动打开文件夹"}), 400
    os.startfile(state.out_dir)  # noqa: S606 - 仅打开本地输出目录
    return jsonify({"ok": True})


def main():
    OUTPUT_ROOT.mkdir(exist_ok=True)
    url = f"http://{HOST}:{PORT}"
    print(f"网页界面：{url}（Ctrl+C 退出）")
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    app.run(host=HOST, port=PORT, debug=False, threaded=True)


if __name__ == "__main__":
    main()
