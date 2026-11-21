#!/usr/bin/env python3
"""Render the GitHub profile README cards as animated SVGs.

Reads data/profile.json (identity, tiles, featured repos, theme) and
data/contributions.json (refreshed daily by .github/workflows/update.yml),
and writes one SVG per card into cards/:

    header.svg                     name, tagline, portrait
    tile-1.svg tile-2.svg tile-3.svg   linked tiles (shown at width 32.5%)
    contributions-monthly.svg      monthly bars + streak/active/busiest stats
    repo-<name>.svg                one card per featured repo
    contributions-graph.svg        the year calendar in the brand colour

The cards are shown through <img> tags, so they only use what works there:
an inline <style> block with CSS keyframes, SMIL <animate>/<set> elements,
and fonts subset with pyftsubset embedded as base64 WOFF data URIs. Every
element rests at its final state; animations move FROM a hidden state, so
turning animations off (prefers-reduced-motion) leaves the finished frame.

STATIC=1 renders the final frame directly: keyframes and SMIL are not
emitted, for screenshotting before pushing.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import sys
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape as xesc

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stats import active_days, current_streak, monthly_totals, most_active_day  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CARDS = ROOT / "cards"
ASSETS = ROOT / "assets"

STATIC = os.environ.get("STATIC") == "1"

MONTHS_ES = ["ene", "feb", "mar", "abr", "may", "jun",
             "jul", "ago", "sep", "oct", "nov", "dic"]

# ---------------------------------------------------------------- data ----

def load_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def fmt_date(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{int(d)} {MONTHS_ES[int(m) - 1]}"


# ------------------------------------------------------------- helpers ----

def wrap(text: str, width: int) -> list[str]:
    """Greedy word wrap assuming ~0.55em average glyph width."""
    limit = max(10, int(width / 0.55))
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if len(trial) > limit and cur:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def countup(x: float, y: float, value: int, begin: float = 0.0, dur: float = 0.8,
            steps: int = 14, attrs: str = "", cls: str = "", suffix: str = "") -> str:
    """Number that counts up with SMIL <set> frames.

    A base <text> always shows the final value; intermediate frames are
    hidden by default and flashed in sequence by SMIL. CSS hides .cf frames
    under prefers-reduced-motion, and STATIC mode never emits them.
    """
    out = [f'<text x="{x:g}" y="{y:g}" {attrs}>{value}{suffix}</text>']
    if not STATIC and value > 0:
        # frames carry the base classes plus .cf (hidden unless SMIL runs)
        base_cls = " ".join(re.findall(r'class="([^"]*)"', attrs))
        frame_attrs = re.sub(r'\s*class="[^"]*"', "", attrs)
        step = dur / steps
        for i in range(1, steps):
            v = round(value * i / steps)
            if v == value:
                continue
            t = begin + dur * i / steps
            out.append(
                f'<text class="cf {base_cls}" style="display:none" x="{x:g}" y="{y:g}" {frame_attrs}>'
                f"{v}{suffix}"
                f'<set attributeName="display" to="inline" begin="{t:.2f}s" dur="{step:.2f}s" fill="remove"/>'
                f"</text>"
            )
    return "\n".join(out)


# ------------------------------------------------------------- styling ----

BASE_CSS = """
text{{font-family:'Source Sans 3',ui-sans-serif,system-ui,sans-serif;fill:{ink}}}
.hd{{font-family:'Outfit',ui-sans-serif,system-ui,sans-serif;font-weight:600}}
.hb{{font-family:'Outfit',ui-sans-serif,system-ui,sans-serif;font-weight:700}}
.mu{{fill:{muted}}}
.ac{{fill:{accent}}}
.wn{{fill:{warn}}}
.an-rise{{animation:rise .55s cubic-bezier(.2,.7,.3,1) both}}
.an-riseBig{{animation:riseBig .6s cubic-bezier(.2,.7,.3,1) both}}
.an-tilt{{animation:tilt .65s cubic-bezier(.2,.7,.3,1) both}}
.an-grow{{animation:grow .6s cubic-bezier(.2,.7,.3,1) both;transform-box:fill-box;transform-origin:bottom}}
.an-pop{{animation:pop .35s cubic-bezier(.2,.7,.3,1) both;transform-box:fill-box;transform-origin:center}}
.an-slide{{animation:slide .55s cubic-bezier(.2,.7,.3,1) both}}
.an-sweep{{animation:sweep 3s ease-in-out infinite}}
.an-pulse{{animation:pulse 2.4s ease-in-out infinite;transform-box:fill-box;transform-origin:center}}
.an-nudge{{animation:nudge 1.6s ease-in-out infinite}}
"""

KEYFRAMES = """
@keyframes rise{from{opacity:0;transform:translateY(14px)}}
@keyframes riseBig{from{opacity:0;transform:translateY(30px) scale(.97)}}
@keyframes tilt{0%{opacity:0;transform:translateY(38px) rotate(-4deg) scale(.94)}70%{opacity:1;transform:translateY(-7px) rotate(1.6deg)}100%{opacity:1;transform:none}}
@keyframes grow{from{transform:scaleY(0)}}
@keyframes pop{from{opacity:0;transform:scale(.5)}}
@keyframes slide{from{opacity:0;transform:translateX(20px)}}
@keyframes sweep{from{transform:translateX(-160%)}to{transform:translateX(560%)}}
@keyframes pulse{50%{opacity:.25;transform:scale(1.5)}}
@keyframes nudge{50%{transform:translateX(4px)}}
"""

REDUCED_MOTION = """
@media (prefers-reduced-motion: reduce){
  *{animation:none!important}
  .cf{display:none!important}
  .smil{display:none!important}
}
"""


def build_style(faces: list[tuple[str, str, int]], th: dict, kf: bool = True) -> str:
    css = ""
    for fam, woff, weight in faces:
        b64 = base64.b64encode(woff.read_bytes()).decode()
        css += (f"@font-face{{font-family:'{fam}';font-weight:{weight};"
                f"src:url(data:font/woff;base64,{b64}) format('woff')}}\n")
    css += BASE_CSS.format(**th)
    if kf and not STATIC:
        css += KEYFRAMES
    css += REDUCED_MOTION
    return css


def svg_doc(w: int, h: int, style: str, body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img">\n'
        f"<style>{style}</style>\n{body}\n</svg>"
    )


def card_frame(w: int, h: int, th: dict, rx: int = 18) -> str:
    return (f'<rect x="1.5" y="1.5" width="{w - 3}" height="{h - 3}" rx="{rx}" '
            f'fill="{th["paper"]}" stroke="{th["line"]}" stroke-width="1"/>')


def shine_defs(th: dict) -> str:
    """Gradient for the SMIL shine: a moving highlight over dark ink."""
    return (
        f'<linearGradient id="shine" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="{th["ink"]}"/>'
        f'<stop offset="0.45" stop-color="{th["ink"]}"/>'
        f'<stop offset="0.5" stop-color="{th["accent"]}"/>'
        f'<stop offset="0.55" stop-color="{th["ink"]}"/>'
        f'<stop offset="1" stop-color="{th["ink"]}"/>'
        f'<animateTransform attributeName="gradientTransform" type="translate" '
        f'values="-0.6 0; 1.2 0" keyTimes="0;1" dur="4.5s" begin="2s" repeatCount="indefinite"/>'
        f"</linearGradient>"
    )


# ------------------------------------------------------------- cards ----

def card_header(prof: dict, th: dict, fonts: dict) -> str:
    w, h = 880, 230
    faces = [("Outfit", fonts["outfit-700"], 700),
             ("Source Sans 3", fonts["sourcesans-400"], 400),
             ("Source Sans 3", fonts["sourcesans-600"], 600)]
    body = [card_frame(w, h, th)]
    if not STATIC:  # SMIL shine: plain ink text below carries the final frame
        body.append(shine_defs(th))

    # top hairline in the accent colour
    body.append(
        f'<path d="M24 2 H{w - 24}" stroke="{th["accent"]}" stroke-width="2" '
        f'opacity=".85" class="an-rise" style="animation-delay:0ms"/>'
    )

    # portrait (optional): embedded data URI, cached in assets/
    portrait = get_portrait(prof)
    if portrait:
        px, py, ps = w - 60 - 150, 40, 150
        body.append(
            f'<clipPath id="pc"><rect x="{px}" y="{py}" width="{ps}" height="{ps}" rx="22"/></clipPath>'
            f'<g class="an-pop" style="animation-delay:120ms">'
            f'<rect x="{px - 4}" y="{py - 4}" width="{ps + 8}" height="{ps + 8}" rx="25" '
            f'fill="none" stroke="{th["accentSoft"]}" stroke-width="1"/>'
            f'<image href="{portrait}" x="{px}" y="{py}" width="{ps}" height="{ps}" '
            f'preserveAspectRatio="xMidYMid slice" clip-path="url(#pc)"/>'
            f"</g>"
        )
        text_w = px - 48 - 48
    else:
        text_w = w - 96

    x = 48
    name = prof["name"]
    # plain name always visible; gradient twin carries the SMIL shine
    body.append(
        f'<text class="hb an-rise" style="animation-delay:60ms" x="{x}" y="98" '
        f'font-size="42" fill="{th["ink"]}">{xesc(name)}</text>'
    )
    if not STATIC:
        body.append(
            f'<text class="hb smil" x="{x}" y="98" font-size="42" '
            f'fill="url(#shine)">{xesc(name)}</text>'
        )
    body.append(
        f'<text class="hd an-rise" style="animation-delay:150ms" x="{x}" y="136" '
        f'font-size="17" fill="{th["accent"]}">{xesc(prof["tagline"])}</text>'
    )
    about_line = wrap(prof["about"], text_w)[0]
    body.append(
        f'<text class="an-rise mu" style="animation-delay:230ms" x="{x}" y="166" '
        f'font-size="14.5" fill="{th["muted"]}">{xesc(about_line)}</text>'
    )

    # bottom chips
    chip_y = 192
    loc = f"· {prof['location']}"
    body.append(
        f'<g class="an-rise" style="animation-delay:310ms">'
        f'<circle cx="{x + 5}" cy="{chip_y - 4}" r="4" fill="{th["muted"]}"/>'
        f'<text x="{x + 16}" y="{chip_y}" font-size="13" fill="{th["muted"]}">'
        f"{xesc(loc.lstrip('· '))}</text></g>"
    )
    if prof.get("available"):
        cx = x + 16 + 7.2 * len(prof["location"]) + 30
        avail = "Disponible para nuevas oportunidades"
        body.append(
            f'<g class="an-rise" style="animation-delay:380ms">'
            f'<circle cx="{cx + 5}" cy="{chip_y - 4}" r="4" fill="{th["ok"]}" '
            f'class="an-pulse"/>'
            f'<text x="{cx + 16}" y="{chip_y}" font-size="13" fill="{th["ink"]}">{avail}</text></g>'
        )
    return svg_doc(w, h, build_style(faces, th), "\n".join(body))


def get_portrait(prof: dict) -> str | None:
    """Download the portrait once into assets/ and embed it as a data URI."""
    url = prof.get("portrait")
    if not url:
        return None
    ASSETS.mkdir(exist_ok=True)
    dest = ASSETS / "portrait.img"
    if not dest.exists():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "profile-cards"})  # noqa: S310
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                dest.write_bytes(resp.read())
        except Exception as exc:  # portrait is optional
            print(f"portrait unavailable ({exc}); header renders without it", file=sys.stderr)
            return None
    mime = "image/webp" if b"WEBP" in dest.read_bytes()[:16] else "image/png"
    return f"data:{mime};base64," + base64.b64encode(dest.read_bytes()).decode()


def card_tile(prof: dict, th: dict, fonts: dict, tile: dict, idx: int) -> str:
    w, h = 286, 160
    faces = [("Outfit", fonts["outfit-700"], 700),
             ("Source Sans 3", fonts["sourcesans-400"], 400),
             ("Source Sans 3", fonts["sourcesans-600"], 600)]
    delay = idx * 90
    body = [
        f'<defs><clipPath id="tc"><rect x="1.5" y="1.5" width="{w - 3}" height="{h - 3}" rx="16"/></clipPath></defs>',
        card_frame(w, h, th, rx=16),
    ]
    # accent corner tick
    body.append(
        f'<path d="M0 0 H46 V4 H4 V46 H0 Z" fill="{th["accentSoft"]}" '
        f'class="an-pop" style="animation-delay:{delay + 260}ms"/>'
    )
    # shine band, clipped to the card, sweeping every few seconds
    if not STATIC:
        body.append(
            f'<g clip-path="url(#tc)" class="smil">'
            f'<rect class="an-sweep" style="animation-delay:{2.2 + idx * 0.4:.1f}s" '
            f'x="-80" y="-20" width="60" height="{h + 40}" fill="{th["ink"]}" opacity=".05" '
            f'transform="skewX(-18)"/></g>'
        )
    body.append(
        f'<text class="hb an-tilt" style="animation-delay:{delay}ms" x="26" y="64" '
        f'font-size="20" fill="{th["ink"]}">{xesc(tile["label"])}</text>'
    )
    body.append(
        f'<text class="an-rise mu" style="animation-delay:{delay + 140}ms" x="26" y="90" '
        f'font-size="12.5" fill="{th["muted"]}">{xesc(tile["caption"])}</text>'
    )
    body.append(
        f'<g class="an-rise" style="animation-delay:{delay + 220}ms">'
        f'<rect x="26" y="108" width="{int(6.4 * len(tile["stat"])) + 20}" height="24" rx="12" '
        f'fill="{th["accentSoft"]}" opacity=".7"/>'
        f'<text x="36" y="124" font-size="11.5" fill="{th["accent"]}">{xesc(tile["stat"])}</text></g>'
    )
    body.append(
        f'<text class="an-nudge" x="{w - 40}" y="{h - 22}" font-size="18" '
        f'fill="{th["accent"]}">&#8594;</text>'
    )
    return svg_doc(w, h, build_style(faces, th), "\n".join(body))


LEVEL_COLORS = ["#101d2b", "#083344", "#0e7490", "#22d3ee", "#a5f3fc"]


def level_for(count: int) -> int:
    if count <= 0:
        return 0
    if count <= 2:
        return 1
    if count <= 5:
        return 2
    if count <= 10:
        return 3
    return 4


def card_monthly(prof: dict, th: dict, data: dict, fonts: dict) -> str:
    w, h = 880, 300
    faces = [("Outfit", fonts["outfit-600"], 600),
             ("Source Sans 3", fonts["sourcesans-400"], 400),
             ("Source Sans 3", fonts["sourcesans-600"], 600)]
    base = 260  # base delay on the page

    days = data["days"]
    months = [m for m in monthly_totals(days)][-12:]
    peak = most_active_day(days)
    streak = current_streak(days)
    actives = active_days(days)
    best = max(months, key=lambda m: m["total"]) if months else None

    body = [card_frame(w, h, th)]
    body.append(
        f'<text class="hd an-rise" x="48" y="46" font-size="20" fill="{th["ink"]}">'
        f'Contribuciones · &#250;ltimos 12 meses</text>'
    )
    body.append(
        f'<text class="an-rise mu" style="animation-delay:70ms" x="48" y="68" '
        f'font-size="12.5" fill="{th["muted"]}">{data["totalContributions"]} contribuciones en el &#250;ltimo a&#241;o</text>'
    )

    # bars
    gx, gy, gh = 48, 96, 96
    pitch = (w - 2 * gx) / max(len(months), 1)
    bw = min(30, pitch * 0.52)
    max_total = max((m["total"] for m in months), default=1) or 1
    for i, m in enumerate(months):
        bh = max(3, (m["total"] / max_total) * gh)
        bx = gx + i * pitch + (pitch - bw) / 2
        is_best = best and m["ym"] == best["ym"]
        color = th["accent"] if is_best else "#0e7490"
        d = base + 60 + i * 45
        body.append(
            f'<rect class="an-grow" style="animation-delay:{d}ms" x="{bx:g}" y="{gy + gh - bh:g}" '
            f'width="{bw:g}" height="{bh:g}" rx="4" fill="{color}" opacity="{1 if is_best else .8}"/>'
        )
        lbl = MONTHS_ES[int(m["ym"][5:]) - 1]
        body.append(
            f'<text class="an-pop mu" style="animation-delay:{d + 200}ms" '
            f'x="{bx + bw / 2:g}" y="{gy + gh + 16}" font-size="10.5" text-anchor="middle" '
            f'fill="{th["muted"]}">{lbl}</text>'
        )
        if is_best:
            body.append(
                f'<g class="an-pop" style="animation-delay:{d + 380}ms">'
                f'<text x="{bx + bw / 2:g}" y="{gy + gh - bh - 8:g}" font-size="13" text-anchor="middle" '
                f'fill="{th["accent"]}">{m["total"]}</text></g>'
            )
    body.append(f'<line x1="{gx}" y1="{gy + gh}" x2="{w - gx}" y2="{gy + gh}" '
                f'stroke="{th["line"]}" stroke-width="1"/>')

    # stat chips: streak / active days / busiest day; the first two count up with SMIL
    chips = [("Racha actual", "streak", 48),
             ("D&#237;as activos", "actives", 48 + 258),
             ("D&#237;a m&#225;s activo", "peak", 48 + 2 * 258)]
    for i, (label, kind, cx) in enumerate(chips):
        d = base + 520 + i * 130
        vx, vy = cx + 14, 272
        attrs = f'font-size="14" font-weight="600" fill="{th["ink"]}"'
        if kind == "streak":
            value = countup(vx, vy, streak, begin=0.8, dur=0.7, attrs=attrs, suffix=" d&#237;as")
        elif kind == "actives":
            value = countup(vx, vy, actives, begin=0.9, dur=0.7, attrs=attrs, suffix=" d&#237;as")
        else:
            peak_txt = f'{fmt_date(peak["date"])} · {peak["count"]}' if peak else "&#8212;"
            value = f'<text x="{vx}" y="{vy}" {attrs}>{peak_txt}</text>'
        body.append(
            f'<g class="an-rise" style="animation-delay:{d}ms">'
            f'<rect x="{cx}" y="238" width="242" height="42" rx="10" fill="{th["paperRaised"]}" '
            f'stroke="{th["line"]}" stroke-width="1"/>'
            f'<text x="{cx + 14}" y="256" font-size="11" fill="{th["muted"]}">{label}</text>'
            f"{value}"
            f"</g>"
        )
    return svg_doc(w, h, build_style(faces, th), "\n".join(body))


def card_repo(prof: dict, th: dict, fonts: dict, repo: dict, idx: int) -> str:
    w, h = 880, 150
    faces = [("Outfit", fonts["outfit-600"], 600),
             ("Source Sans 3", fonts["sourcesans-400"], 400),
             ("Source Sans 3", fonts["sourcesans-600"], 600)]
    delay = 420 + idx * 140

    body = [card_frame(w, h, th)]
    body.append(
        f'<rect x="1.5" y="1.5" width="4" height="{h - 3}" rx="2" fill="{th["accent"]}" '
        f'class="an-pop" style="animation-delay:{delay + 300}ms"/>'
    )
    x = 40
    body.append(
        f'<text class="hd an-slide" style="animation-delay:{delay}ms" x="{x}" y="44" '
        f'font-size="20" fill="{th["ink"]}">{xesc(repo["title"])}</text>'
    )
    # status chip, top right
    label = repo["status"]
    color = th["accent"] if label == "En producci&#243;n" else th["warn"]
    chip_w = int(6.6 * len(label)) + 24
    body.append(
        f'<g class="an-rise" style="animation-delay:{delay + 160}ms">'
        f'<rect x="{w - 48 - chip_w}" y="26" width="{chip_w}" height="24" rx="12" '
        f'fill="{th["paperRaised"]}" stroke="{th["line"]}" stroke-width="1"/>'
        f'<text x="{w - 48 - chip_w + 12}" y="42" font-size="11.5" fill="{color}">{xesc(label)}</text></g>'
    )
    for j, line in enumerate(wrap(repo["description"], w - 2 * x - 150)[:2]):
        body.append(
            f'<text class="an-rise mu" style="animation-delay:{delay + 220 + j * 60}ms" '
            f'x="{x}" y="{70 + j * 19}" font-size="13.5" fill="{th["muted"]}">{xesc(line)}</text>'
        )
    y = h - 28
    body.append(
        f'<g class="an-rise" style="animation-delay:{delay + 340}ms">'
        f'<circle cx="{x + 5}" cy="{y - 4}" r="5" fill="{repo["langColor"]}"/>'
        f'<text x="{x + 16}" y="{y}" font-size="12" fill="{th["muted"]}">{xesc(repo["language"])}</text>'
    )
    tx = x + 30 + 6.2 * len(repo["language"])
    for topic in repo["topics"][:4]:
        tw = int(6.1 * len(topic)) + 18
        body.append(
            f'<rect x="{tx}" y="{y - 15}" width="{tw}" height="20" rx="10" fill="{th["paperRaised"]}" '
            f'stroke="{th["line"]}" stroke-width="1"/>'
            f'<text x="{tx + 9}" y="{y}" font-size="10.5" fill="{th["muted"]}">{xesc(topic)}</text>'
        )
        tx += tw + 8
    if repo.get("demo"):
        body.append(
            f'<text class="an-rise ac" style="animation-delay:{delay + 420}ms" '
            f'x="{w - 48}" y="{y}" font-size="12.5" text-anchor="end" fill="{th["accent"]}">'
            f'Demo &#8594;</text>'
        )
    body.append("</g>")
    return svg_doc(w, h, build_style(faces, th), "\n".join(body))


def card_graph(prof: dict, th: dict, data: dict, fonts: dict) -> str:
    w, h = 880, 212
    faces = [("Outfit", fonts["outfit-600"], 600),
             ("Source Sans 3", fonts["sourcesans-400"], 400)]
    base = 780

    days = data["days"]
    weeks: list[list[dict]] = []
    for d in days:
        if not weeks or (len(weeks[-1]) == 7):
            weeks.append([])
        weeks[-1].append(d)
    peak = most_active_day(days)
    peak_date = peak["date"] if peak else None

    body = [card_frame(w, h, th)]
    total = data["totalContributions"]
    # the headline total counts up (SMIL frames); base text is the final value
    body.append(
        countup(48, 42, total, begin=1.2, dur=1.0,
                attrs=f'class="hd" font-size="19" fill="{th["ink"]}"',
                suffix=" contribuciones en el &#250;ltimo a&#241;o")
    )
    peak_line = f'pico {peak["count"]} el {fmt_date(peak["date"])}' if peak else "a\u00fan sin picos"
    body.append(
        f'<text class="an-rise" style="animation-delay:80ms" x="48" y="64" font-size="12.5" '
        f'fill="{th["muted"]}">{active_days(days)} d&#237;as activos · {peak_line}</text>'
    )

    # grid: pop in left to right
    gx, gy, pitch, size = 48, 78, 14, 11
    cols = len(weeks)
    for ci, week in enumerate(weeks):
        for ri, d in enumerate(week):
            lvl = level_for(d["count"])
            is_peak = d["date"] == peak_date and lvl > 0
            cx = gx + ci * pitch
            cy = gy + ri * pitch
            delay = base + ci * 14 + ri * 7
            if ci == cols - 1:
                # today: outline square
                body.append(
                    f'<rect class="an-pop" style="animation-delay:{delay}ms" '
                    f'x="{cx}" y="{cy}" width="{size}" height="{size}" rx="2.5" '
                    f'fill="none" stroke="{th["line"]}" stroke-width="1"/>'
                )
                continue
            body.append(
                f'<rect class="an-pop" style="animation-delay:{delay}ms" x="{cx}" y="{cy}" '
                f'width="{size}" height="{size}" rx="2.5" fill="{LEVEL_COLORS[lvl]}"'
                + (f' stroke="{th["accent"]}" stroke-width="1.2"' if is_peak else "")
                + "/>"
            )
    # legend below the grid, bottom-left
    ly = h - 14
    body.append(f'<text class="an-rise mu" style="animation-delay:{base + 600}ms" '
                f'x="48" y="{ly}" font-size="10.5" fill="{th["muted"]}">Menos</text>')
    for i, c in enumerate(LEVEL_COLORS):
        body.append(f'<rect class="an-pop" style="animation-delay:{base + 640 + i * 40}ms" '
                    f'x="{48 + 40 + i * 16}" y="{ly - 10}" width="11" height="11" rx="2.5" fill="{c}"/>')
    body.append(f'<text class="an-rise mu" style="animation-delay:{base + 850}ms" '
                f'x="{48 + 40 + len(LEVEL_COLORS) * 16 + 8}" y="{ly}" font-size="10.5" '
                f'fill="{th["muted"]}">M&#225;s</text>')
    return svg_doc(w, h, build_style(faces, th), "\n".join(body))


# ------------------------------------------------------------------ main ----

def main() -> int:
    prof = load_json(ROOT / "data" / "profile.json")
    th = dict(prof["theme"], muted=prof["theme"]["inkMuted"])
    data = load_json(ROOT / "data" / "contributions.json")
    fonts = {p.stem: p for p in (ROOT / "fonts").glob("*.woff")}
    missing = {"outfit-700", "outfit-600", "sourcesans-400", "sourcesans-600"} - set(fonts)
    if missing:
        print(f"missing fonts: {missing} — run scripts/build_fonts.py", file=sys.stderr)
        return 1

    CARDS.mkdir(exist_ok=True)
    cards: dict[str, str] = {"header.svg": card_header(prof, th, fonts)}
    for i, tile in enumerate(prof["tiles"], 1):
        cards[f"tile-{i}.svg"] = card_tile(prof, th, fonts, tile, i - 1)
    cards["contributions-monthly.svg"] = card_monthly(prof, th, data, fonts)
    for i, repo in enumerate(prof["repos"]):
        slug = re.sub(r"[^a-z0-9]+", "-", repo["name"].lower()).strip("-")
        cards[f"repo-{slug}.svg"] = card_repo(prof, th, fonts, repo, i)
    cards["contributions-graph.svg"] = card_graph(prof, th, data, fonts)

    for name, content in cards.items():
        path = CARDS / name
        path.write_text(content, encoding="utf-8")
        print(f"{name}: {path.stat().st_size / 1024:.1f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
