"""Download the brand fonts (SIL OFL) once so the subsetter can run offline."""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "fonts" / "src"

SOURCES = {
    "Anton.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/anton/Anton-Regular.ttf",
    "Manrope.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/manrope/Manrope%5Bwght%5D.ttf",
    "JetBrainsMono.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf",
}


def main() -> int:
    SRC.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        dest = SRC / name
        if dest.exists() and dest.stat().st_size > 10_000:
            print(f"{name}: already present")
            continue
        urllib.request.urlretrieve(url, dest)  # noqa: S310 - fixed URL
        print(f"{name}: downloaded {dest.stat().st_size/1024:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
