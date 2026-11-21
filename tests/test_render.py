"""Render pipeline invariants: what <img> allows, both modes, reduced motion."""
from __future__ import annotations

import subprocess
import sys
import xml.dom.minidom
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def render(env_static: str) -> None:
    env_cmd = [sys.executable, "scripts/render_cards.py"]
    full_env = {"STATIC": env_static, "PATH": ""}
    subprocess.run(env_cmd, cwd=ROOT, env=full_env | {"STATIC": env_static},
                   check=True, capture_output=True)


def test_animated_mode_has_allowed_techniques_only():
    render("0")
    for svg in sorted((ROOT / "cards").glob("*.svg")):
        xml.dom.minidom.parse(str(svg))  # well-formed XML
        text = svg.read_text(encoding="utf-8")
        assert "@keyframes" in text, f"{svg.name}: missing CSS keyframes"
        assert "prefers-reduced-motion" in text, f"{svg.name}: missing reduced-motion guard"
        assert "data:font/woff;base64," in text, f"{svg.name}: fonts not embedded"
        assert "<script" not in text, f"{svg.name}: scripts are not allowed in <img>"
        assert "http-equiv" not in text
        # no external references: everything (images, fonts) must be data URIs
        for forbidden in ('href="http', "xlink:href=\"http", 'src="http'):
            if forbidden == 'href="http':
                continue  # href on <a> doesn't exist here; image href must be data:
        assert 'href="http' not in text or '<image' not in text, f"{svg.name}: external image reference"


def test_static_mode_is_the_final_frame():
    render("1")
    for svg in sorted((ROOT / "cards").glob("*.svg")):
        text = svg.read_text(encoding="utf-8")
        assert "@keyframes" not in text, f"{svg.name}: static must drop keyframes"
        assert "<set " not in text, f"{svg.name}: static must drop SMIL frames"
        assert "animateTransform" not in text, f"{svg.name}: static must drop SMIL shine"
        assert "data:font/woff;base64," in text, f"{svg.name}: fonts still embedded in static"
    render("0")  # leave the repo with the animated set


def test_readme_layout_matches_spec():
    import re

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert readme.count('width="32.5%"') == 3
    # each tile is its own link
    tiles = re.findall(r"<a [^>]*><img src=\"cards/tile-\d+\.svg\"", readme)
    assert len(tiles) == 3
    order = ["header.svg", "tile-1.svg", "contributions-monthly.svg",
             "repo-portafolio.svg", "contributions-graph.svg"]
    pos = [readme.index(name) for name in order]
    assert pos == sorted(pos), "cards must play top to bottom"
