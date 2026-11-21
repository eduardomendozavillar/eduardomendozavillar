"""Subset the brand fonts to WOFF for embedding in SVG cards.

Pipeline: variable TTF (fonts/src) -> static instance per weight (fontTools
varLib.instancer) -> pyftsubset to the card charset -> WOFF in fonts/.

The card charset is printable ASCII plus Latin-1 accents (Spanish copy),
punctuation used in the copy (· — – ’ “ ” …) and a couple of arrows, so any
text the renderers or the daily data produce stays covered without a rebuild.
"""
from __future__ import annotations

import base64
import io
import sys
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "fonts" / "src"
OUT = ROOT / "fonts"

# family -> (source file, [(weight, out name), ...])
FONTS = {
    "Outfit": ("Outfit.ttf", [(600, "outfit-600"), (700, "outfit-700")]),
    "Source Sans 3": ("SourceSans3.ttf", [(400, "sourcesans-400"), (600, "sourcesans-600")]),
}

# Printable ASCII + Spanish letters (both cases, incl. inverted marks) + the
# punctuation the cards use. Keeps every weight under ~35 KB WOFF.
CHARSET = (
    " !\"#$%&'()*+,-./0123456789:;<=>?@"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`"
    "abcdefghijklmnopqrstuvwxyz{|}~"
    "¡¿ÁÉÍÓÚÜÑáéíóúüñç"
    "·—–’‘“”…→←•°"
)


def subset_font(path: Path, weight: int, out_name: str) -> Path:
    font = TTFont(path)
    if "fvar" in font:  # pin the variable axis to a static instance
        instantiateVariableFont(font, {"wght": weight}, inplace=True)
        font["head"].macStyle |= 0  # keep style flags untouched
    buf = io.BytesIO()
    font.save(buf)

    opts = subset.Options()
    opts.flavor = "woff"
    # default feature set keeps kern/liga/clig; "*" drags in every stylistic table
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    ss = subset.Subsetter(options=opts)
    ss.populate(text=CHARSET)
    font = TTFont(buf)
    ss.subset(font)

    out = OUT / f"{out_name}.woff"
    out.parent.mkdir(parents=True, exist_ok=True)
    font.save(out)
    return out


def main() -> int:
    if not SRC.exists() or not any(SRC.glob("*.ttf")):
        print("No source fonts in fonts/src/ — run scripts/fetch_fonts.py first.", file=sys.stderr)
        return 1
    for family, (filename, weights) in FONTS.items():
        src = SRC / filename
        # Blog gotcha: verify the family from the name table before trusting the file.
        font = TTFont(src)
        actual = font["name"].getDebugName(16) or font["name"].getDebugName(1)
        if actual != family:
            print(f"WARNING: {src.name} says family '{actual}' (expected '{family}')")
        for weight, out_name in weights:
            out = subset_font(src, weight, out_name)
            size = out.stat().st_size
            print(f"{family} {weight} -> {out.relative_to(ROOT)} ({size/1024:.1f} KB)")
    return 0


def data_uri(path: Path) -> str:
    return "data:font/woff;base64," + base64.b64encode(path.read_bytes()).decode()


if __name__ == "__main__":
    raise SystemExit(main())
