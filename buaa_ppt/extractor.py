"""Playwright 提取器：登录北航后从回放页面抓取全部 PPT 幻灯片图片。

提取策略（接口优先，页面扫描兜底）：
1. PPT 列表来自 `pptnote/v1/schedule/search-ppt` 接口（含每页原图地址与出现时间），
   需要登录 Cookie：优先捕获页面自己发出的该请求，捕获不到则用页面 URL 里的
   course_id / sub_id 主动调用（resource_guid 可省略）；
2. 下载走浏览器上下文的 request（自动携带 Cookie 与 Referer），绕过跨域限制；
3. 接口不可用时，回退为扫描页面 <img> 并滚动侧边栏触发懒加载。
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import sync_playwright

SSO_HOST_KEYWORD = "sso.buaa.edu.cn"
API_PATH = "/pptnote/v1/schedule/search-ppt"
API_ORIGIN = "https://classroom.msa.buaa.edu.cn"

# 缩略图最小像素尺寸，用于过滤 logo、图标等无关小图（仅兜底扫描模式使用）
MIN_THUMB_WIDTH = 120
MIN_THUMB_HEIGHT = 80
# 保存为幻灯片的最小像素尺寸
MIN_SLIDE_WIDTH = 240


@dataclass
class Slide:
    index: int            # 从 1 开始的页码
    file: str             # 相对于输出目录的文件名
    url: str              # 原始图片地址
    sha256: str           # 图片内容哈希
    width: int
    height: int
    timestamps: list[str] = field(default_factory=list)


@dataclass
class _Entry:
    url: str
    timestamp: str | None = None


# 回放页标题形如“课程名第3周星期2第3,4节”，按此拆出课程名与周次节次
TITLE_SPLIT_RE = re.compile(r"^(.+?)(第\s*\d+\s*周.*)$")


def split_title(title: str) -> tuple[str | None, str | None]:
    m = TITLE_SPLIT_RE.match((title or "").strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return None, None


def safe_name(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", (name or "").strip())
    return cleaned or "未命名"


def resolve_output_dir(working_dir: Path, title: str) -> Path:
    """把时间戳工作目录整理为 output/<课程名>/<周次节次>，返回最终目录。

    标题无法拆分时保留原目录；目标已存在（重复提取同一讲）时追加 _2、_3 序号。
    """
    course, session = split_title(title)
    if not course:
        return working_dir
    target = working_dir.parent / safe_name(course) / safe_name(session)
    candidate, n = target, 1
    while candidate.exists():
        n += 1
        candidate = target.with_name(f"{target.name}_{n}")
    if candidate == working_dir:
        return working_dir
    candidate.parent.mkdir(parents=True, exist_ok=True)
    working_dir.rename(candidate)
    return candidate


def _format_seconds(sec: int) -> str:
    sec = max(0, int(sec))
    if sec >= 3600:
        return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}"
    return f"{sec // 60:02d}:{sec % 60:02d}"


class SlideExtractor:
    def __init__(
        self,
        profile_dir: Path,
        headless: bool = False,
        log: Callable[[str], None] = print,
    ):
        self.profile_dir = profile_dir
        self.headless = headless
        self.log = log

    # ---- 浏览器生命周期 -------------------------------------------------

    def _launch(self, p):
        """优先使用本机已安装的 Chrome / Edge，避免额外下载 Chromium。"""
        errors = []
        for channel in ("chrome", "msedge"):
            try:
                return p.chromium.launch_persistent_context(
                    str(self.profile_dir),
                    channel=channel,
                    headless=self.headless,
                    viewport={"width": 1600, "height": 1000},
                    args=["--disable-blink-features=AutomationControlled"],
                )
            except Exception as exc:  # noqa: BLE001 - 逐个渠道尝试
                errors.append(f"{channel}: {exc}")
        try:
            return p.chromium.launch_persistent_context(
                str(self.profile_dir),
                headless=self.headless,
                viewport={"width": 1600, "height": 1000},
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"chromium: {exc}")
        raise RuntimeError(
            "无法启动浏览器。请先安装运行 `python -m playwright install chromium`，"
            "或确认本机已安装 Chrome / Edge。\n" + "\n".join(errors)
        )

    def _open_with_login(self, page, url: str, timeout_s: int):
        page.goto(url, wait_until="domcontentloaded")
        time.sleep(3)
        if SSO_HOST_KEYWORD not in page.url:
            return
        self.log("检测到需要登录北航账号。请在打开的浏览器窗口中完成登录（支持扫码）……")
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            time.sleep(2)
            if page.is_closed():
                raise RuntimeError("浏览器窗口被关闭，登录中断。")
            if SSO_HOST_KEYWORD not in page.url:
                self.log("登录成功，继续提取。")
                time.sleep(3)
                return
        raise RuntimeError("登录等待超时，请重新运行并在弹出的窗口中及时完成登录。")

    # ---- 接口模式 -------------------------------------------------------

    def _attach_api_listener(self, page) -> dict:
        """在页面跳转前挂上响应监听，捕获页面自己发出的 search-ppt 请求。"""
        captured: dict = {}

        def on_response(resp):
            if API_PATH in resp.url and captured.get("url") is None:
                try:
                    captured["url"] = resp.url
                    captured["body"] = resp.json()
                except Exception:  # noqa: BLE001 - 响应体读取失败时允许下一次捕获
                    captured["url"] = None

        page.on("response", on_response)
        return captured

    def _await_api_capture(self, captured: dict, wait_s: float):
        deadline = time.time() + wait_s
        while time.time() < deadline and captured.get("url") is None:
            time.sleep(1)
        if captured.get("url") is None:
            return None, None
        return captured["url"], captured.get("body")

    def _build_api_url(self, livingroom_url: str) -> str | None:
        """从回放页 URL 提取 course_id / sub_id，构造 search-ppt 接口地址。"""
        query = parse_qs(urlsplit(livingroom_url).query)
        course_id = (query.get("course_id") or [None])[0]
        sub_id = (query.get("sub_id") or [None])[0]
        if not course_id or not sub_id:
            return None
        return (
            f"{API_ORIGIN}{API_PATH}?course_id={course_id}&sub_id={sub_id}"
            "&page=1&per_page=100"
        )

    def _fetch_api_page(self, page, url: str):
        """同源 fetch 调用 PPT 列表接口。"""
        return page.evaluate(
            """async (u) => {
                const r = await fetch(u, { credentials: 'include' });
                return await r.json();
            }""",
            url,
        )

    def _collect_api_entries(self, page, api_url: str, body) -> list[_Entry]:
        """从接口响应收集全部幻灯片，必要时翻页。接口本身按时间顺序返回。"""
        entries: dict[str, _Entry] = {}
        ordered: list[_Entry] = []
        total = int(body.get("total") or len(body.get("list") or []))

        def absorb(items):
            for item in items:
                try:
                    content = json.loads(item.get("content") or "{}")
                except (TypeError, ValueError):
                    continue
                img = content.get("pptimgurl")
                if not img or img in entries:
                    continue
                entry = _Entry(url=img)
                sec = item.get("created_sec")
                try:
                    entry.timestamp = _format_seconds(int(sec))
                except (TypeError, ValueError):
                    pass
                entries[img] = entry
                ordered.append(entry)

        absorb(body.get("list") or [])
        # 接口按 page/per_page 分页；翻页直到取满 total 或某页无新数据
        page_no = 1
        while len(ordered) < total and page_no < 20:
            page_no += 1
            next_url = re.sub(r"([?&])page=\d+", rf"\g<1>page={page_no}", api_url)
            if next_url == api_url:
                next_url = api_url + ("&" if "?" in api_url else "?") + f"page={page_no}"
            try:
                data = self._fetch_api_page(page, next_url)
            except Exception:  # noqa: BLE001
                break
            items = (data or {}).get("list") or []
            before = len(ordered)
            absorb(items)
            if not items or len(ordered) == before:
                break
        return ordered

    # ---- 兜底：页面扫描模式 ---------------------------------------------

    def _scan_dom_thumbs(self, page) -> list[_Entry]:
        """扫描页面上的缩略图 <img>，同时从自身或祖先节点文本里读取时间戳。"""
        raw = page.evaluate(
            """() => {
                const seen = new Set();
                const out = [];
                for (const img of document.images) {
                    const w = img.naturalWidth || img.width || 0;
                    const h = img.naturalHeight || img.height || 0;
                    if (w < %d || h < %d) continue;
                    const src = img.currentSrc || img.src;
                    if (!src || seen.has(src)) continue;
                    seen.add(src);
                    let node = img, ts = null;
                    for (let i = 0; i < 5 && node; i++) {
                        const m = (node.textContent || '').match(/\\b(\\d{1,2}:\\d{2}(?::\\d{2})?)\\b/);
                        if (m) { ts = m[1]; break; }
                        node = node.parentElement;
                    }
                    out.push({ src, ts });
                }
                return out;
            }"""
            % (MIN_THUMB_WIDTH, MIN_THUMB_HEIGHT)
        )
        return [_Entry(url=t["src"], timestamp=t.get("ts")) for t in raw]

    def _find_scroll_container(self, page):
        return page.evaluate(
            """() => {
                const imgs = [...document.images].filter(img => {
                    const w = img.naturalWidth || img.width || 0;
                    const h = img.naturalHeight || img.height || 0;
                    return w >= %d && h >= %d;
                });
                if (!imgs.length) return null;
                const counts = new Map();
                for (const img of imgs) {
                    let node = img.parentElement;
                    for (let i = 0; i < 8 && node; i++) {
                        if (node.scrollHeight - node.clientHeight > 60) {
                            counts.set(node, (counts.get(node) || 0) + 1);
                            break;
                        }
                        node = node.parentElement;
                    }
                }
                let best = null, bestCount = 0;
                for (const [el, c] of counts) {
                    if (c > bestCount) { best = el; bestCount = c; }
                }
                if (!best) return null;
                best.setAttribute('data-buaa-ppt-scroll', '1');
                return '[data-buaa-ppt-scroll="1"]';
            }"""
            % (MIN_THUMB_WIDTH, MIN_THUMB_HEIGHT)
        )

    def _scroll_to_load_all(self, page) -> list[_Entry]:
        """滚动侧边栏触发懒加载，反复扫描直到不再出现新图片。"""
        selector = self._find_scroll_container(page)
        collected: dict[str, _Entry] = {}
        if selector:
            self.log("找到侧边栏滚动容器，开始滚动加载全部幻灯片……")
            stale_rounds = 0
            for _ in range(200):
                for e in self._scan_dom_thumbs(page):
                    collected.setdefault(e.url, e)
                before = len(collected)
                more = page.evaluate(
                    """(sel) => {
                        const el = document.querySelector(sel);
                        if (!el) return false;
                        const before = el.scrollTop;
                        el.scrollBy(0, el.clientHeight * 0.8);
                        return el.scrollTop > before;
                    }""",
                    selector,
                )
                time.sleep(0.6)
                if not more or len(collected) == before:
                    stale_rounds += 1
                    if stale_rounds >= 4:
                        break
                else:
                    stale_rounds = 0
            page.evaluate(
                """(sel) => { const el = document.querySelector(sel); if (el) el.scrollTop = 0; }""",
                selector,
            )
        for e in self._scan_dom_thumbs(page):
            collected.setdefault(e.url, e)
        return list(collected.values())

    # ---- 下载与保存 -----------------------------------------------------

    def _download(self, ctx, page, url: str, referer: str) -> bytes | None:
        """优先走浏览器上下文请求（自动带 Cookie），失败再回退页面内 fetch。"""
        try:
            resp = ctx.request.get(url, headers={"Referer": referer})
            if resp.ok:
                return resp.body()
        except Exception:  # noqa: BLE001
            pass
        try:
            return self._download_in_page(page, url)
        except Exception:  # noqa: BLE001
            return None

    def _download_in_page(self, page, url: str) -> bytes | None:
        result = page.evaluate(
            """async (url) => {
                const resp = await fetch(url, { credentials: 'include' });
                if (!resp.ok) return null;
                const buf = await resp.arrayBuffer();
                const bytes = new Uint8Array(buf);
                let bin = '';
                const chunk = 0x8000;
                for (let i = 0; i < bytes.length; i += chunk) {
                    bin += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
                }
                return btoa(bin);
            }""",
            url,
        )
        if not result:
            return None
        import base64

        return base64.b64decode(result)

    def _save_entries(
        self,
        ctx,
        page,
        entries: list[_Entry],
        out_dir: Path,
        referer: str,
        keep_duplicates: bool,
        on_progress=None,
    ) -> list[Slide]:
        slides_dir = out_dir / "slides"
        slides_dir.mkdir(parents=True, exist_ok=True)
        slides: list[Slide] = []
        total = len(entries)
        for i, entry in enumerate(entries, 1):
            data = self._download(ctx, page, entry.url, referer)
            if not data:
                self.log(f"[{i}/{total}] 下载失败，跳过：{entry.url}")
                continue
            width, height = self._image_size(data)
            if width < MIN_SLIDE_WIDTH:
                self.log(f"[{i}/{total}] 图片过小({width}x{height})，跳过。")
                continue
            digest = hashlib.sha256(data).hexdigest()
            if (
                not keep_duplicates
                and digest == (slides[-1].sha256 if slides else None)
            ):
                # 与上一页完全相同：合并时间戳而不是新增一页
                if entry.timestamp:
                    slides[-1].timestamps.append(entry.timestamp)
                self.log(f"[{i}/{total}] 与上一页重复，已合并时间戳。")
                continue
            ext = self._guess_ext(entry.url, data)
            no = len(slides) + 1
            filename = f"slide_{no:03d}{ext}"
            (slides_dir / filename).write_bytes(data)
            slides.append(
                Slide(
                    index=no,
                    file=f"slides/{filename}",
                    url=entry.url,
                    sha256=digest,
                    width=width,
                    height=height,
                    timestamps=[entry.timestamp] if entry.timestamp else [],
                )
            )
            if on_progress:
                on_progress(i, total)
            if no % 10 == 0:
                self.log(f"已保存 {no} 页……")
        return slides

    # ---- 主流程 ---------------------------------------------------------

    def extract(
        self,
        url: str,
        out_dir: Path,
        login_timeout_s: int = 600,
        keep_duplicates: bool = False,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> tuple[list[Slide], str, Path]:
        """提取全部幻灯片，返回 (页列表, 回放页标题, 最终输出目录)。

        out_dir 是提取过程的工作目录；结束后会整理为 output/<课程名>/<周次节次>。
        """
        out_dir.mkdir(parents=True, exist_ok=True)
        self.profile_dir.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as p:
            ctx = self._launch(p)
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            captured = self._attach_api_listener(page)
            try:
                self._open_with_login(page, url, login_timeout_s)

                entries: list[_Entry] = []
                api_url, body = self._await_api_capture(captured, wait_s=20)
                if body:
                    entries = self._collect_api_entries(page, api_url, body)
                if not entries:
                    # 页面没有发出列表请求时，用回放页 URL 里的参数直接调接口
                    api_url = self._build_api_url(page.url)
                    if api_url:
                        try:
                            body = self._fetch_api_page(page, api_url)
                        except Exception:  # noqa: BLE001
                            body = None
                        if body and body.get("list"):
                            entries = self._collect_api_entries(page, api_url, body)
                if entries:
                    self.log(f"接口返回 {len(entries)} 页幻灯片，开始下载原图……")
                if not entries:
                    self.log("未获取到接口数据，回退为页面扫描模式（可能漏页）。")
                    deadline = time.time() + 60
                    while time.time() < deadline and not entries:
                        entries = self._scroll_to_load_all(page)
                        if not entries:
                            time.sleep(3)
                if not entries:
                    page.screenshot(path=str(out_dir / "debug_no_thumbs.png"))
                    raise RuntimeError(
                        "未能获取任何幻灯片。可能页面结构变化或加载过慢，"
                        f"已保存调试截图：{out_dir / 'debug_no_thumbs.png'}"
                    )

                slides = self._save_entries(
                    ctx, page, entries, out_dir, url, keep_duplicates, on_progress
                )
                title = (page.title() or "").strip()
                final_dir = resolve_output_dir(out_dir, title)
                return slides, title, final_dir
            finally:
                ctx.close()

    @staticmethod
    def _image_size(data: bytes) -> tuple[int, int]:
        from PIL import Image
        import io

        with Image.open(io.BytesIO(data)) as im:
            return im.size

    @staticmethod
    def _guess_ext(url: str, data: bytes) -> str:
        m = re.search(r"\.(jpe?g|png|webp|bmp)(?:[?#]|$)", url, re.IGNORECASE)
        if m:
            return "." + m.group(1).lower().replace("jpeg", "jpg")
        if data.startswith(b"\x89PNG"):
            return ".png"
        if data.startswith(b"\xff\xd8"):
            return ".jpg"
        return ".jpg"
