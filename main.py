"""智学北航课堂回放 PPT 提取工具（命令行版）。

用法：
    python main.py "https://classroom.msa.buaa.edu.cn/livingroom?course_id=...&sub_id=...&tenant_code=..."

提取全部幻灯片图片并合成为一个 PDF 文件。需要图形操作界面时运行 `python webui.py`。
首次运行会弹出浏览器窗口，登录北航账号（支持扫码）一次即可，登录状态保存在
本地 .browser_profile 目录，之后运行无需再次登录。
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from buaa_ppt.extractor import SlideExtractor
from buaa_ppt.pdfgen import build_pdf

PROJECT_DIR = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description="提取智学北航课堂回放中的 PPT 并合成 PDF")
    parser.add_argument("url", help="回放页面地址（livingroom 链接）")
    parser.add_argument("--out", default=None, help="输出目录（默认 output/<时间戳>）")
    parser.add_argument("--keep-duplicates", action="store_true", help="不去除重复的幻灯片")
    parser.add_argument("--no-hd", action="store_true", help="关闭高清增强（默认开启：裁掉黑边并放大锐化）")
    parser.add_argument("--headless", action="store_true", help="无头模式运行浏览器（首次登录时不要使用）")
    parser.add_argument("--login-timeout", type=int, default=600, help="等待登录的最长时间（秒）")
    args = parser.parse_args()

    out_dir = Path(args.out) if args.out else PROJECT_DIR / "output" / datetime.now().strftime("%Y%m%d_%H%M%S")
    print(f"输出目录：{out_dir}")

    extractor = SlideExtractor(
        profile_dir=PROJECT_DIR / ".browser_profile",
        headless=args.headless,
    )
    try:
        slides, title, out_dir = extractor.extract(
            url=args.url,
            out_dir=out_dir,
            login_timeout_s=args.login_timeout,
            keep_duplicates=args.keep_duplicates,
            on_progress=lambda done, total: print(f"\r下载进度 {done}/{total}", end=""),
        )
    except Exception as exc:  # noqa: BLE001 - CLI 层统一给出可读错误
        print(f"\n提取失败：{exc}")
        return 1
    print(f"\n共提取 {len(slides)} 页幻灯片，正在合成 PDF……")
    try:
        pdf = build_pdf(out_dir, slides, title, hd=not args.no_hd)
    except Exception as exc:  # noqa: BLE001
        print(f"PDF 合成失败：{exc}（图片已保存在 {out_dir / 'slides'}）")
        return 1
    print(f"完成！输出目录：{out_dir}")
    print(f"PDF 文件：{pdf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
