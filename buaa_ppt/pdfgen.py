"""把提取到的幻灯片图片按页序合成为一个 PDF 文件。"""

from __future__ import annotations

import re
from pathlib import Path

from .extractor import Slide


def build_pdf(out_dir: Path, slides: list[Slide], title: str) -> Path:
    if not slides:
        raise RuntimeError("没有可用的幻灯片图片，无法合成 PDF。")
    images = [str(out_dir / s.file) for s in slides]
    pdf_path = out_dir / f"{safe_name(title)}.pdf"
    try:
        import img2pdf

        # img2pdf 直接嵌入原始 JPEG 数据，不重编码、无画质损失
        pdf_path.write_bytes(img2pdf.convert(images))
    except Exception:  # noqa: BLE001 - 少数带透明通道的图片 img2pdf 不接受
        _build_with_pillow(pdf_path, images)
    return pdf_path


def _build_with_pillow(pdf_path: Path, images: list[str]):
    from PIL import Image

    pages = []
    for path in images:
        with Image.open(path) as im:
            pages.append(im.convert("RGB").copy())
    if pages:
        pages[0].save(pdf_path, save_all=True, append_images=pages[1:], quality=90)


def safe_name(title: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", (title or "").strip())
    return name or "课件"
