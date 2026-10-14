# Document Watermarker

A small command-line tool that stamps a tiled, diagonal, semi-transparent text watermark across images and PDFs.

It's built for the moment an employer, landlord or agency asks for copies of your passport, visa or ID. A watermark like *"For XYZ job application only – 14 Oct 2026"* keeps the document readable for them, but makes the copy much harder to reuse for anything else.

![Example of a watermarked sample ID card](example.jpg)

## Features

- Works on **images** (JPG, PNG, WEBP, BMP, TIFF) and **PDFs** (single or multi-page)
- Text is **tiled across the whole page** in staggered rows, so it can't simply be cropped out
- PDFs are **flattened**: each page is rendered to an image with the watermark baked in, so it can't be deleted in a PDF editor
- Phone photos are auto-rotated using their EXIF orientation
- Process individual files or **whole folders** in one command
- **Originals are never modified**; results are saved as `<name>_watermarked.<ext>`
- Runs fully **offline**, so your documents never leave your computer

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (recommended) **or** pip

Dependencies: [PyMuPDF](https://pymupdf.readthedocs.io/) and [Pillow](https://python-pillow.org/) 10.1+.

## Quick start

### With uv (recommended)

The script declares its own dependencies ([PEP 723](https://peps.python.org/pep-0723/) inline metadata), so uv installs them automatically on the first run. No virtual environment setup needed.

```bash
uv run watermark.py scans/ --text "For XYZ job application only - 14 Oct 2026"
```

### With pip

```bash
pip install pymupdf "pillow>=10.1"
python watermark.py scans/ --text "For XYZ job application only - 14 Oct 2026"
```

## Usage

```bash
uv run watermark.py <files or folders> [options]
```

### Examples

```bash
# Individual files
uv run watermark.py passport.pdf visa.jpg emirates_id.png

# Every image and PDF in a folder
uv run watermark.py scans/

# Custom text, saved to a separate folder
uv run watermark.py scans/ --text "For XYZ hiring only - 14 Oct 2026" --out-dir ready/

# Stronger blue watermark, smaller PDF files
uv run watermark.py scans/ --opacity 100 --color 0,0,180 --dpi 150
```

### Options

| Option | Default | Description |
|---|---|---|
| `--text` | `For job application only - <today>` | The watermark text |
| `--opacity` | `70` | Transparency, from `0` (invisible) to `255` (solid) |
| `--color` | `255,0,0` | Text color as `R,G,B` |
| `--angle` | `30` | Rotation in degrees |
| `--dpi` | `200` | PDF render quality; lower it (e.g. `150`) for smaller files |
| `--out-dir` | next to originals | Folder to save the watermarked files in |

When a folder is passed, files that already contain `_watermarked` in their name are skipped, so re-running the command won't watermark the same copy twice.

## How it works

1. **Images** are opened with Pillow and corrected for EXIF rotation.
2. **PDFs** are rendered page by page to images with PyMuPDF at the chosen DPI.
3. The text is drawn in staggered rows on a transparent layer twice the size of the page, rotated, then cropped back to size, so every corner is covered.
4. The layer is alpha-blended onto the page, and the result is saved as an image or a new multi-page PDF.

Because PDF output is image-based, text in the watermarked PDF is no longer selectable or searchable. This is intentional, since it's what makes the watermark permanent.

## Tips for watermarking ID documents

- **Be specific:** name the recipient, the purpose and the date. A generic "COPY" watermark protects much less.
- **Check readability:** before sending, make sure the name, ID number, photo and expiry date are still clear.
- **Keep the originals:** store the clean scans separately so you can make a fresh copy for each recipient.
- **Large files:** if a PDF is too big to email, re-run it with `--dpi 150`.

## Troubleshooting

| Problem | Fix |
|---|---|
| `load_default() got an unexpected keyword argument 'size'` | Upgrade Pillow to 10.1 or newer (`uv` does this automatically) |
| Watermark text looks small or pixelated | No TrueType font was found. Install Arial or DejaVu Sans, or edit `load_font()` to point at a `.ttf` file on your system |
| Watermark is too faint on a dark document | Increase `--opacity` (e.g. `110`) or switch to a lighter `--color` |

## Development

The code follows [Ruff](https://docs.astral.sh/ruff/) with **all rules enabled** and Google-style docstrings (see `ruff.toml`). To check it:

```bash
uvx ruff check .
uvx ruff format --check .
```
