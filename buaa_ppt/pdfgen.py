"""把幻灯片图片处理并合成为一个 PDF 文件。

处理流程：
1. 自动裁剪：去掉教室画面两侧的黑边和右侧课堂工具栏，让 PPT 内容铺满页面
   （按列/行亮度检测白色幻灯片区域，检测不可靠时保留原图）；
2. 高清增强（可选）：内容区 2× Lanczos 放大加锐化，缩放阅读时边缘更锐利；
3. 用 img2pdf 合成 PDF，成功后清理图片，最终只保留 PDF。
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .extractor import Slide, safe_name

# 检测白色幻灯片区域的亮度阈值（0-255）：黑边约 10~20，工具栏约 40~60，白底页 200+
_BRIGHT = 85


def build_pdf(out_dir: Path, slides: list[Slide], title: str, hd: bool = True) -> Path:
    if not slides:
        raise RuntimeError("没有可用的幻灯片图片，无法合成 PDF。")
    from PIL import Image, ImageFilter

    work_dir = out_dir / "_pdf_src"
    work_dir.mkdir(exist_ok=True)
    images: list[str] = []
    try:
        for i, slide in enumerate(slides, 1):
            src = out_dir / slide.file
            with Image.open(src) as im:
                im = im.convert("RGB")
                im, cropped = _crop_content(im)
                untouched = (not cropped) and (not hd)
                if untouched:
                    # 没有任何处理：直接复用原始字节，无重编码损失
                    images.append(str(src))
                    continue
                if hd:
                    im = im.resize((im.width * 2, im.height * 2), Image.LANCZOS)
                    im = im.filter(ImageFilter.UnsharpMask(radius=2, percent=110, threshold=2))
                dst = work_dir / f"p_{i:03d}.jpg"
                im.save(dst, quality=88 if hd else 92)
                images.append(str(dst))
        pdf_path = out_dir / f"{safe_name(title)}.pdf"
        try:
            import img2pdf

            # img2pdf 直接嵌入 JPEG 数据，不重编码、无画质损失
            pdf_path.write_bytes(img2pdf.convert(images))
        except Exception:  # noqa: BLE001 - 个别图片 img2pdf 不接受时兜底
            _build_with_pillow(pdf_path, images)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
    shutil.rmtree(out_dir / "slides", ignore_errors=True)
    return pdf_path


def _crop_content(im):
    """检测并裁掉黑边与工具栏，返回 (图, 是否发生裁剪)。"""
    from PIL import Image

    w, h = im.size
    if w < 500 or h < 300:
        return im, False
    g = im.convert("L")
    cols = list(g.resize((w, 1), Image.BOX).getdata())
    rows = list(g.resize((1, h), Image.BOX).getdata())

    cw, cstart = _largest_bright_run(cols)
    rh, rstart = _largest_bright_run(rows)
    if cw < w * 0.45 or rh < h * 0.45:
        # 区域检测不可靠（如深色背景的页面），保留原图
        return im, False
    box = (cstart, rstart, cstart + cw, rstart + rh)
    if box == (0, 0, w, h):
        return im, False
    return im.crop(box), True


def _largest_bright_run(vals: list[int]):
    """返回最大的连续高亮区段 (长度, 起点)。"""
    best_len, best_start = 0, 0
    cur_start = None
    for i, v in enumerate([*vals, 0]):
        if v > _BRIGHT:
            if cur_start is None:
                cur_start = i
        else:
            if cur_start is not None and i - cur_start > best_len:
                best_len, best_start = i - cur_start, cur_start
            cur_start = None
    return best_len, best_start


def _build_with_pillow(pdf_path: Path, images: list[str]):
    from PIL import Image

    pages = []
    for path in images:
        with Image.open(path) as im:
            pages.append(im.convert("RGB").copy())
    if pages:
        pages[0].save(pdf_path, save_all=True, append_images=pages[1:], quality=90)
