"""Download the brand fonts (SIL OFL) once so the subsetter can run offline."""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "fonts" / "src"

SOURCES = {
    "Outfit.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/outfit/Outfit%5Bwght%5D.ttf",
    "SourceSans3.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/sourcesans3/SourceSans3%5Bwght%5D.ttf",
    "InstrumentSerif.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/instrumentserif/InstrumentSerif-Regular.ttf",
    "InstrumentSerif-Italic.ttf": "https://raw.githubusercontent.com/google/fonts/main/ofl/instrumentserif/InstrumentSerif-Italic.ttf",
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
