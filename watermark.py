# Copyright (c) 2026 Mohamed Elfares
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pillow>=10.1",
#     "pymupdf",
# ]
# ///
"""Watermark images and PDFs with tiled, diagonal, semi-transparent text.

PDF pages are rendered to images first, so the watermark is "baked in"
(flattened) and cannot be deleted in a PDF editor. Originals are never
modified; results are saved as ``<name>_watermarked.<ext>``.

Run with uv (dependencies are installed automatically from the block above)::

    uv run watermark.py <files or folders> [options]

Or with pip::

    pip install pymupdf "pillow>=10.1"
    python watermark.py <files or folders> [options]

Examples::

    uv run watermark.py passport.pdf visa.jpg emirates_id.png
    uv run watermark.py scans/
    uv run watermark.py scans/ --text "For XYZ hiring only - 14 Oct 2026"
    uv run watermark.py scans/ --opacity 90 --color 0,0,180 --out-dir ready/
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pymupdf
from PIL import Image, ImageDraw, ImageFont, ImageOps

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"})
PDF_EXTS = frozenset({".pdf"})

# Formats without an alpha channel must be converted to RGB before saving.
NO_ALPHA_EXTS = frozenset({".jpg", ".jpeg", ".bmp"})

# Fonts tried in order; the first one found on the system is used.
# Windows ships Arial, most Linux distros ship DejaVu or Liberation.
FONT_CANDIDATES = (
    "arial.ttf",
    "Arial.ttf",
    "DejaVuSans.ttf",
    "LiberationSans-Regular.ttf",
)

OUTPUT_SUFFIX = "_watermarked"
MAX_CHANNEL = 255  # Upper bound for RGB and alpha values.
JPEG_QUALITY = 92

# Use the local timezone so the default date matches the user's calendar.
TODAY = datetime.now().astimezone().date()
DEFAULT_TEXT = f"For job application only - {TODAY:%d %b %Y}"

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Data types
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class WatermarkStyle:
    """Visual settings for the watermark.

    Attributes:
        text: The text to repeat across the page.
        color: RGB color of the text, each channel 0-255.
        opacity: Alpha value from 0 (invisible) to 255 (solid).
        angle: Counter-clockwise rotation of the text, in degrees.
        rows: Approximate number of text rows per page height.

    """

    text: str = DEFAULT_TEXT
    color: tuple[int, int, int] = (255, 0, 0)
    opacity: int = 70
    angle: float = 30
    rows: int = 6


class EmptyPDFError(ValueError):
    """Raised when a PDF has no pages to watermark."""

    def __init__(self, path: Path) -> None:
        """Build the error message from the offending file path.

        Args:
            path: The PDF file that contained no pages.

        """
        super().__init__(f"PDF has no pages: {path}")


# --------------------------------------------------------------------------- #
# Core watermarking
# --------------------------------------------------------------------------- #


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Return the first available TrueType font at the given size.

    Falls back to Pillow's built-in font (scalable since Pillow 10.1) if
    none of the fonts in ``FONT_CANDIDATES`` is installed.

    Args:
        size: Font size in pixels.

    Returns:
        A font object usable with ``ImageDraw.text``.

    """
    for name in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        # The try/except cost is negligible for four candidates, and Pillow
        # offers no cheaper way to check whether a font is installed.
        except OSError:  # noqa: PERF203
            continue  # Font not installed; try the next one.
    return ImageFont.load_default(size=size)


def watermark_image(img: Image.Image, style: WatermarkStyle) -> Image.Image:
    """Return a copy of ``img`` with the watermark text tiled diagonally.

    The text is drawn on a transparent layer twice the size of the image,
    rotated, and cropped back to the image size. Drawing on the larger
    canvas ensures the rotated text still reaches every corner.

    Args:
        img: The source image. It is not modified.
        style: Text, color, opacity and layout settings.

    Returns:
        A new RGBA image with the watermark blended on top.

    """
    img = img.convert("RGBA")
    width, height = img.size

    layer = Image.new("RGBA", (width * 2, height * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    # Scale the font to the shorter side so it looks similar on
    # portrait pages and landscape ID cards.
    font_size = max(12, min(width, height) // 18)
    font = load_font(font_size)

    # Horizontal step = text width + a gap, so repeats never overlap.
    step_x = int(draw.textlength(style.text, font=font)) + font_size * 2
    step_y = max(font_size * 3, height // style.rows)
    fill = (*style.color, style.opacity)

    for row, y in enumerate(range(0, layer.height, step_y)):
        # Shift every other row by half a step (brickwork pattern) so the
        # watermark can't be removed by cropping out a single column.
        offset = (step_x // 2) * (row % 2)
        for x in range(-offset, layer.width, step_x):
            draw.text((x, y), style.text, font=font, fill=fill)

    # Rotate around the centre, then crop the middle back to the original size.
    layer = layer.rotate(style.angle)
    left, top = width // 2, height // 2
    layer = layer.crop((left, top, left + width, top + height))

    return Image.alpha_composite(img, layer)


def process_image(src: Path, dst: Path, style: WatermarkStyle) -> None:
    """Watermark a single image file and save it to ``dst``.

    Args:
        src: Path of the source image.
        dst: Path to write the watermarked image to.
        style: Watermark settings.

    """
    # Phone photos often store rotation in EXIF instead of the pixels;
    # apply it so the result isn't sideways.
    img = ImageOps.exif_transpose(Image.open(src))
    result = watermark_image(img, style)

    if dst.suffix.lower() in NO_ALPHA_EXTS:
        result.convert("RGB").save(dst, quality=JPEG_QUALITY)
    else:
        result.save(dst)


def process_pdf(src: Path, dst: Path, style: WatermarkStyle, dpi: int = 200) -> None:
    """Watermark every page of a PDF and save a flattened copy to ``dst``.

    Each page is rendered to an image, so the output PDF contains no
    selectable text and the watermark cannot be removed as a layer.

    Args:
        src: Path of the source PDF.
        dst: Path to write the watermarked PDF to.
        style: Watermark settings.
        dpi: Render resolution. Lower values give smaller files.

    Raises:
        EmptyPDFError: If the PDF has no pages.

    """
    pages: list[Image.Image] = []
    with pymupdf.open(src) as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=dpi)  # alpha=False by default, so RGB.
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            pages.append(watermark_image(img, style).convert("RGB"))

    if not pages:
        raise EmptyPDFError(src)

    # Pillow writes a multi-page PDF from the first image plus the rest.
    pages[0].save(dst, save_all=True, append_images=pages[1:], resolution=dpi)


# --------------------------------------------------------------------------- #
# Command-line interface
# --------------------------------------------------------------------------- #


def collect_files(paths: Iterable[str]) -> Iterator[Path]:
    """Expand the given paths into the files to process.

    Folders are scanned (non-recursively) for supported files. Files that
    already carry the ``_watermarked`` suffix are skipped so re-running the
    command doesn't watermark a copy twice.

    Args:
        paths: File and/or folder paths from the command line.

    Yields:
        Paths of files to watermark.

    """
    supported = IMAGE_EXTS | PDF_EXTS
    for path in map(Path, paths):
        if path.is_dir():
            for file in sorted(path.iterdir()):
                if file.suffix.lower() in supported and OUTPUT_SUFFIX not in file.stem:
                    yield file
        elif path.is_file():
            yield path
        else:
            logger.warning("  ! Not found: %s", path)


def parse_color(value: str) -> tuple[int, int, int]:
    """Parse an ``R,G,B`` string into a color tuple for argparse.

    Args:
        value: Comma-separated channel values, e.g. ``"255,0,0"``.

    Returns:
        The color as a tuple of three integers.

    Raises:
        argparse.ArgumentTypeError: If the value is not three numbers 0-255.

    """
    try:
        red, green, blue = (int(part) for part in value.split(","))
    except ValueError as exc:
        msg = f"expected R,G,B (e.g. 255,0,0), got {value!r}"
        raise argparse.ArgumentTypeError(msg) from exc

    color = (red, green, blue)
    if not all(0 <= channel <= MAX_CHANNEL for channel in color):
        msg = f"color channels must be 0-255, got {value!r}"
        raise argparse.ArgumentTypeError(msg)
    return color


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser.

    Returns:
        The configured parser.

    """
    parser = argparse.ArgumentParser(description="Watermark images and PDFs.")
    parser.add_argument("paths", nargs="+", help="files and/or folders to watermark")
    parser.add_argument("--text", default=DEFAULT_TEXT, help="watermark text")
    parser.add_argument(
        "--opacity",
        type=int,
        default=70,
        help="0 (invisible) to 255 (solid); default 70",
    )
    parser.add_argument(
        "--color",
        type=parse_color,
        default=(255, 0, 0),
        help="text color as R,G,B; default 255,0,0 (red)",
    )
    parser.add_argument(
        "--angle",
        type=float,
        default=30,
        help="rotation in degrees; default 30",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=200,
        help="PDF render quality; use 150 for smaller files",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        help="save results here instead of next to the originals",
    )
    return parser


def main() -> None:
    """Run the command-line tool."""
    # Plain messages, no log-level prefix, since this is user-facing output.
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    args = build_parser().parse_args()
    style = WatermarkStyle(
        text=args.text,
        color=args.color,
        opacity=args.opacity,
        angle=args.angle,
    )

    out_dir: Path | None = args.out_dir
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)

    logger.info('Watermark: "%s"', style.text)
    for src in collect_files(args.paths):
        ext = src.suffix.lower()
        dst = (out_dir or src.parent) / f"{src.stem}{OUTPUT_SUFFIX}{src.suffix}"

        try:
            if ext in PDF_EXTS:
                process_pdf(src, dst, style, dpi=args.dpi)
            elif ext in IMAGE_EXTS:
                process_image(src, dst, style)
            else:
                logger.info("  - Skipped (unsupported type): %s", src.name)
                continue
        # OSError covers unreadable or corrupt images (UnidentifiedImageError);
        # RuntimeError covers damaged PDFs (pymupdf.FileDataError).
        except (OSError, ValueError, RuntimeError) as exc:
            # Log the short message only; a full traceback would be noise for
            # end users, and one bad file shouldn't stop the rest of the batch.
            logger.error("  ! Failed on %s: %s", src.name, exc)  # noqa: TRY400
        else:
            logger.info("  + %s -> %s", src.name, dst.name)


if __name__ == "__main__":
    main()
