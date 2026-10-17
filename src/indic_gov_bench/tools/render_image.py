"""render_image.py — PDF Page to PNG Image Renderer for IndicGovBench-Doc."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pypdfium2 as pdfium


def render_single_page(
    pdf_path: Path,
    out_png_path: Path,
    dpi: int = 300,
    verbose: int = 0,
) -> bool:
    """Renders page 0 of a single PDF to a PNG image at the given DPI."""
    if not pdf_path.is_file():
        print(f"❌ Error: Input PDF '{pdf_path}' not found.", file=sys.stderr)
        return False

    t0 = time.time()
    try:
        pdf = pdfium.PdfDocument(str(pdf_path))
        if len(pdf) == 0:
            print(f"❌ Error: PDF '{pdf_path.name}' has 0 pages.", file=sys.stderr)
            return False

        page = pdf[0]
        # pypdfium2 default point scale is 72 DPI (scale = dpi / 72.0)
        scale = dpi / 72.0
        bitmap = page.render(scale=scale)
        pil_image = bitmap.to_pil()

        out_png_path.parent.mkdir(parents=True, exist_ok=True)
        pil_image.save(out_png_path, format="PNG")
        elapsed = time.time() - t0

        if verbose > 0:
            w, h = pil_image.size
            print(f"🖼️  Rendered {out_png_path.name} ({w}x{h} px) in {elapsed:.2f}s")
        else:
            print(f"🖼️  Rendered {out_png_path.name}")
        return True
    except Exception as e:
        print(f"❌ Error rendering {pdf_path.name}: {e}", file=sys.stderr)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render PDF page 0 to 300 DPI PNG image for IndicGovBench-Doc."
    )
    parser.add_argument("input_pdf", type=str, help="Path to input PDF file")
    parser.add_argument("output_png", type=str, help="Path to output PNG image file")
    parser.add_argument("--dpi", type=int, default=300, help="Output DPI (default: 300)")
    parser.add_argument(
        "--verbose", type=int, default=0, help="Verbosity level (0=compact, 1=detailed)"
    )

    args = parser.parse_args()
    ok = render_single_page(
        pdf_path=Path(args.input_pdf),
        out_png_path=Path(args.output_png),
        dpi=args.dpi,
        verbose=args.verbose,
    )
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
