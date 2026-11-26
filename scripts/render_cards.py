#!/usr/bin/env python3
"""Render the GitHub profile README cards as animated SVGs.

Visual language: the profile owner's portfolio — warm-black paper (#1c1c1c),
cream ink (#ede6db), coral-red accent (#ed6a5b), Anton display type for the
condensed uppercase name, Manrope for body text and JetBrains Mono for the
terminal motif. Data comes from data/profile.json (identity, tiles, featured
repos, theme) and data/contributions.json (refreshed daily by
.github/workflows/update.yml). One SVG per card in cards/:

    header.svg                     role line, stacked name, terminal, portrait
    tile-1..3.svg                  linked tiles (shown at width 32.5%)
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

def wrap(text: str, width_px: int, font_size: float = 14.0) -> list[str]:
    """Greedy word wrap assuming ~0.55em average glyph width."""
    limit = max(10, int(width_px / (0.55 * font_size)))
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
text{{font-family:'Manrope',ui-sans-serif,system-ui,sans-serif;fill:{ink}}}
.dsp{{font-family:'Anton','Arial Narrow',Impact,sans-serif;font-weight:400}}
.mono{{font-family:'JetBrains Mono',ui-monospace,SFMono-Regular,Menlo,monospace}}
.outline{{fill:none;stroke:{ink};stroke-width:1.5;paint-order:stroke}}
.mu{{fill:{muted}}}
.ac{{fill:{accent}}}
.wide{{letter-spacing:2px;text-transform:uppercase}}
.an-rise{{animation:rise .55s cubic-bezier(.2,.7,.3,1) both}}
.an-riseBig{{animation:riseBig .6s cubic-bezier(.2,.7,.3,1) both}}
.an-tilt{{animation:tilt .65s cubic-bezier(.2,.7,.3,1) both}}
.an-grow{{animation:grow .6s cubic-bezier(.2,.7,.3,1) both;transform-box:fill-box;transform-origin:bottom}}
.an-pop{{animation:pop .35s cubic-bezier(.2,.7,.3,1) both;transform-box:fill-box;transform-origin:center}}
.an-slide{{animation:slide .55s cubic-bezier(.2,.7,.3,1) both}}
.an-sweep{{animation:sweep 3s ease-in-out infinite}}
.an-pulse{{animation:pulse 2.4s ease-in-out infinite;transform-box:fill-box;transform-origin:center}}
.an-blink{{animation:blink 1.1s steps(2) infinite}}
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
@keyframes blink{50%{opacity:0}}
@keyframes nudge{50%{transform:translateX(4px)}}
"""

REDUCED_MOTION = """
@media (prefers-reduced-motion: reduce){
  *{animation:none!important}
  .cf{display:none!important}
  .smil{display:none!important}
}
"""


def build_style(faces: list[tuple[str, str, int]], th: dict) -> str:
    css = ""
    for fam, woff, weight in faces:
        b64 = base64.b64encode(woff.read_bytes()).decode()
        css += (f"@font-face{{font-family:'{fam}';font-weight:{weight};"
                f"src:url(data:font/woff;base64,{b64}) format('woff')}}\n")
    css += BASE_CSS.format(**th)
    if not STATIC:
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
            f'fill="{th["paperRaised"]}" stroke="{th["line"]}" stroke-width="1"/>')


def shine_defs(th: dict) -> str:
    """Gradient for the SMIL shine: a moving highlight over cream ink."""
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


# ------------------------------------------------------------- cards ----

def card_header(prof: dict, th: dict, fonts: dict) -> str:
    w, h = 880, 380
    faces = [("Anton", fonts["anton-400"], 400),
             ("Manrope", fonts["manrope-400"], 400),
             ("JetBrains Mono", fonts["jetbrains-400"], 400)]
    body = [card_frame(w, h, th)]
    if not STATIC:  # SMIL shine: plain ink text below carries the final frame
        body.append(shine_defs(th))

    words = prof["name"].upper().split()
    x = 48

    # role line, mono red, letterspaced — like the portfolio hero
    role = prof["tagline"].upper()
    role_lines = wrap(role, 430, 10.5)
    for j, line in enumerate(role_lines[:2]):
        body.append(
            f'<text class="mono ac an-rise" style="animation-delay:{j * 60}ms" '
            f'x="{x}" y="{54 + j * 18}" font-size="10.5" letter-spacing="1.6" '
            f'fill="{th["accent"]}">{xesc(line)}</text>'
        )

    # stacked condensed name: solid, solid (SMIL shine), outlined
    ny = [134, 194, 254]
    for i, word in enumerate(words[:3]):
        outlined = i == 2
        # CSS text{fill:...} beats presentation attributes, so the hollow
        # line needs its own class instead of fill="none"
        cls = "dsp an-riseBig outline" if outlined else "dsp an-riseBig"
        body.append(
            f'<text class="{cls}" style="animation-delay:{100 + i * 80}ms" x="{x - 3}" y="{ny[i]}" '
            f'font-size="56">{xesc(word)}</text>'
        )
        if i == 1 and not STATIC:  # shine twin over the solid middle line
            body.append(
                f'<text class="dsp smil" x="{x - 3}" y="{ny[i]}" font-size="56" '
                f'fill="url(#shine)">{xesc(word)}</text>'
            )

    # about, with the red emphasis from the site hero
    about = prof["about"]
    em = "inteligencia artificial"
    about_lines = wrap(about, 460, 13.5)[:3]
    for j, line in enumerate(about_lines):
        content = line
        if em in line and not STATIC:
            head, _, tail = line.partition(em)
            content = (f'{xesc(head)}<tspan fill="{th["accent"]}">{xesc(em)}</tspan>'
                       f'{xesc(tail)}')
            content = content.replace(xesc(head), xesc(head), 1)
        else:
            content = xesc(line)
        body.append(
            f'<text class="an-rise mu" style="animation-delay:{320 + j * 60}ms" x="{x}" '
            f'y="{304 + j * 20}" font-size="13.5" fill="{th["muted"]}">{content}</text>'
        )

    # portrait (optional): circular, embedded data URI
    portrait = get_portrait(prof)
    if portrait:
        ps = 150
        px, py = w - 52 - ps, 44
        body.append(
            f'<clipPath id="pc"><rect x="{px}" y="{py}" width="{ps}" height="{ps}" rx="75"/></clipPath>'
            f'<g class="an-pop" style="animation-delay:150ms">'
            f'<image href="{portrait}" x="{px}" y="{py}" width="{ps}" height="{ps}" '
            f'preserveAspectRatio="xMidYMid slice" clip-path="url(#pc)"/>'
            f"</g>"
        )

    # terminal card, bottom right — the portfolio's whoami motif
    term = prof.get("terminal", {})
    tx, ty, tw_, thh = 552, 218, 280, 142
    body.append(
        f'<g class="an-slide" style="animation-delay:260ms">'
        f'<rect x="{tx}" y="{ty}" width="{tw_}" height="{thh}" rx="10" fill="{th["paper"]}" '
        f'stroke="{th["line"]}" stroke-width="1"/>'
        f'<path d="M{tx} {ty + 26} h{tw_}" stroke="{th["line"]}" stroke-width="1"/>'
        f'<circle cx="{tx + 16}" cy="{ty + 13}" r="4" fill="{th["accent"]}"/>'
        f'<text class="mono mu" x="{tx + 30}" y="{ty + 17}" font-size="10.5" '
        f'fill="{th["muted"]}">{xesc(term.get("title", ""))}</text>'
    )
    body.append(
        f'<text class="mono" x="{tx + 16}" y="{ty + 48}" font-size="11.5">'
        f'<tspan fill="{th["accent"]}">$ </tspan>'
        f'<tspan fill="{th["ink"]}">{xesc(term.get("cmd", ""))}</tspan></text>'
    )
    for j, line in enumerate(term.get("output", [])):
        body.append(
            f'<text class="mono an-rise" style="animation-delay:{360 + j * 70}ms" '
            f'x="{tx + 16}" y="{ty + 70 + j * 18}" font-size="11.5" '
            f'fill="{th["ink"]}">{xesc(line)}</text>'
        )
    # prompt + blinking cursor at the end (visible by default: final state)
    cursor_y = ty + 70 + len(term.get("output", [])) * 18
    body.append(
        f'<text class="mono" x="{tx + 16}" y="{cursor_y}" font-size="11.5" '
        f'fill="{th["accent"]}">$ </text>'
    )
    # visible by default: it blinks only when animations run
    body.append(
        f'<rect class="an-blink" x="{tx + 34}" y="{cursor_y - 10}" width="8" height="13" '
        f'fill="{th["ink"]}"/>'
    )
    body.append("</g>")
    return svg_doc(w, h, build_style(faces, th), "\n".join(body))


def card_tile(prof: dict, th: dict, fonts: dict, tile: dict, idx: int) -> str:
    w, h = 286, 160
    faces = [("Anton", fonts["anton-400"], 400),
             ("Manrope", fonts["manrope-400"], 400),
             ("JetBrains Mono", fonts["jetbrains-400"], 400)]
    delay = idx * 90
    body = [
        f'<defs><clipPath id="tc{idx}"><rect x="1.5" y="1.5" width="{w - 3}" height="{h - 3}" rx="16"/></clipPath></defs>',
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
            f'<g clip-path="url(#tc{idx})" class="smil">'
            f'<rect class="an-sweep" style="animation-delay:{2.2 + idx * 0.4:.1f}s" '
            f'x="-80" y="-20" width="60" height="{h + 40}" fill="{th["ink"]}" opacity=".05" '
            f'transform="skewX(-18)"/></g>'
        )
    body.append(
        f'<text class="dsp an-tilt" style="animation-delay:{delay}ms" x="26" y="62" '
        f'font-size="20" fill="{th["ink"]}">{xesc(tile["label"])}</text>'
    )
    body.append(
        f'<text class="an-rise mu" style="animation-delay:{delay + 140}ms" x="26" y="88" '
        f'font-size="12.5" fill="{th["muted"]}">{xesc(tile["caption"])}</text>'
    )
    body.append(
        f'<g class="an-rise" style="animation-delay:{delay + 220}ms">'
        f'<rect x="26" y="106" width="{int(7.2 * len(tile["stat"])) + 20}" height="24" rx="12" '
        f'fill="{th["accentSoft"]}"/>'
        f'<text class="mono" x="36" y="122" font-size="10.5" fill="{th["accent"]}">'
        f'{xesc(tile["stat"])}</text></g>'
    )
    body.append(
        f'<text class="an-nudge" x="{w - 40}" y="{h - 22}" font-size="18" '
        f'fill="{th["accent"]}">&#8594;</text>'
    )
    return svg_doc(w, h, build_style(faces, th), "\n".join(body))


LEVEL_COLORS = ["#33312d", "#4a2f2b", "#7a3f38", "#b3574c", "#ed6a5b"]


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
    faces = [("Anton", fonts["anton-400"], 400),
             ("Manrope", fonts["manrope-400"], 400),
             ("Manrope", fonts["manrope-600"], 600),
             ("JetBrains Mono", fonts["jetbrains-400"], 400)]
    base = 260  # base delay on the page

    days = data["days"]
    months = [m for m in monthly_totals(days)][-12:]
    peak = most_active_day(days)
    streak = current_streak(days)
    actives = active_days(days)
    best = max(months, key=lambda m: m["total"]) if months else None

    body = [card_frame(w, h, th)]
    body.append(
        f'<text class="dsp an-rise" x="48" y="50" font-size="23" fill="{th["ink"]}">'
        f'CONTRIBUCIONES · &#218;LTIMOS 12 MESES</text>'
    )
    body.append(
        f'<text class="an-rise mu" style="animation-delay:70ms" x="48" y="74" '
        f'font-size="12.5" fill="{th["muted"]}">{data["totalContributions"]} contribuciones en el &#250;ltimo a&#241;o</text>'
    )

    # bars
    gx, gy, gh = 48, 98, 92
    pitch = (w - 2 * gx) / max(len(months), 1)
    bw = min(30, pitch * 0.52)
    max_total = max((m["total"] for m in months), default=1) or 1
    for i, m in enumerate(months):
        bh = max(3, (m["total"] / max_total) * gh)
        bx = gx + i * pitch + (pitch - bw) / 2
        is_best = best and m["ym"] == best["ym"]
        color = th["accent"] if is_best else "#55524d"
        d = base + 60 + i * 45
        body.append(
            f'<rect class="an-grow" style="animation-delay:{d}ms" x="{bx:g}" y="{gy + gh - bh:g}" '
            f'width="{bw:g}" height="{bh:g}" rx="3" fill="{color}"/>'
        )
        lbl = MONTHS_ES[int(m["ym"][5:]) - 1]
        body.append(
            f'<text class="mono an-pop mu" style="animation-delay:{d + 200}ms" '
            f'x="{bx + bw / 2:g}" y="{gy + gh + 18}" font-size="10" text-anchor="middle" '
            f'fill="{th["muted"]}">{lbl}</text>'
        )
        if is_best:
            body.append(
                f'<g class="an-pop" style="animation-delay:{d + 380}ms">'
                f'<text class="mono" x="{bx + bw / 2:g}" y="{gy + gh - bh - 8:g}" font-size="12" '
                f'text-anchor="middle" fill="{th["accent"]}">{m["total"]}</text></g>'
            )
    body.append(f'<line x1="{gx}" y1="{gy + gh}" x2="{w - gx}" y2="{gy + gh}" '
                f'stroke="{th["line"]}" stroke-width="1"/>')

    # stat chips: streak / active days / busiest day; the first two count up with SMIL
    chips = [("Racha actual", "streak", 48),
             ("D&#237;as activos", "actives", 48 + 258),
             ("D&#237;a m&#225;s activo", "peak", 48 + 2 * 258)]
    for i, (label, kind, cx) in enumerate(chips):
        d = base + 520 + i * 130
        vx, vy = cx + 14, 274
        attrs = f'class="mono" font-size="13" fill="{th["ink"]}"'
        if kind == "streak":
            value = countup(vx, vy, streak, begin=0.8, dur=0.7, attrs=attrs, suffix=" días")
        elif kind == "actives":
            value = countup(vx, vy, actives, begin=0.9, dur=0.7, attrs=attrs, suffix=" días")
        else:
            peak_txt = f'{fmt_date(peak["date"])} · {peak["count"]}' if peak else "—"
            value = f'<text class="mono" x="{vx}" y="{vy}" font-size="13" fill="{th["ink"]}">{peak_txt}</text>'
        body.append(
            f'<g class="an-rise" style="animation-delay:{d}ms">'
            f'<rect x="{cx}" y="240" width="242" height="44" rx="10" fill="{th["paper"]}" '
            f'stroke="{th["line"]}" stroke-width="1"/>'
            f'<text x="{cx + 14}" y="258" font-size="11" fill="{th["muted"]}">{label}</text>'
            f"{value}"
            f"</g>"
        )
    return svg_doc(w, h, build_style(faces, th), "\n".join(body))


def card_repo(prof: dict, th: dict, fonts: dict, repo: dict, idx: int) -> str:
    w, h = 880, 150
    faces = [("Anton", fonts["anton-400"], 400),
             ("Manrope", fonts["manrope-400"], 400),
             ("JetBrains Mono", fonts["jetbrains-400"], 400)]
    delay = 420 + idx * 140

    body = [card_frame(w, h, th)]
    body.append(
        f'<rect x="1.5" y="1.5" width="4" height="{h - 3}" rx="2" fill="{th["accent"]}" '
        f'class="an-pop" style="animation-delay:{delay + 300}ms"/>'
    )
    x = 40
    body.append(
        f'<text class="dsp an-slide" style="animation-delay:{delay}ms" x="{x}" y="44" '
        f'font-size="20" fill="{th["ink"]}">{xesc(repo["title"].upper())}</text>'
    )
    # status chip, top right — mono, like the site's button chips
    label = repo["status"]
    is_prod = label == "En producción"
    color = th["accent"] if is_prod else th["warn"]
    chip_w = int(7.2 * len(label)) + 24
    body.append(
        f'<g class="an-rise" style="animation-delay:{delay + 160}ms">'
        f'<rect x="{w - 48 - chip_w}" y="24" width="{chip_w}" height="24" rx="12" '
        f'fill="{th["accentSoft"] if is_prod else th["paper"]}" stroke="{th["line"]}" stroke-width="1"/>'
        f'<text class="mono" x="{w - 48 - chip_w + 12}" y="40" font-size="10" '
        f'fill="{color}">{xesc(label)}</text></g>'
    )
    for j, line in enumerate(wrap(repo["description"], w - 2 * x - 150, 13.0)[:2]):
        body.append(
            f'<text class="an-rise mu" style="animation-delay:{delay + 220 + j * 60}ms" '
            f'x="{x}" y="{72 + j * 19}" font-size="13" fill="{th["muted"]}">{xesc(line)}</text>'
        )
    y = h - 26
    body.append(
        f'<g class="an-rise" style="animation-delay:{delay + 340}ms">'
        f'<circle cx="{x + 5}" cy="{y - 4}" r="5" fill="{repo["langColor"]}"/>'
        f'<text x="{x + 16}" y="{y}" font-size="12" fill="{th["muted"]}">{xesc(repo["language"])}</text>'
    )
    tx = x + 30 + 6.2 * len(repo["language"])
    for topic in repo["topics"][:4]:
        tw = int(6.4 * len(topic)) + 18
        body.append(
            f'<rect x="{tx}" y="{y - 15}" width="{tw}" height="20" rx="10" fill="{th["paper"]}" '
            f'stroke="{th["line"]}" stroke-width="1"/>'
            f'<text class="mono" x="{tx + 9}" y="{y}" font-size="9.5" fill="{th["muted"]}">'
            f'{xesc(topic)}</text>'
        )
        tx += tw + 8
    if repo.get("demo"):
        body.append(
            f'<text class="mono an-rise" style="animation-delay:{delay + 420}ms" '
            f'x="{w - 48}" y="{y}" font-size="11.5" text-anchor="end" fill="{th["accent"]}">'
            f'Demo &#8594;</text>'
        )
    body.append("</g>")
    return svg_doc(w, h, build_style(faces, th), "\n".join(body))


def card_graph(prof: dict, th: dict, data: dict, fonts: dict) -> str:
    w, h = 880, 212
    faces = [("Anton", fonts["anton-400"], 400),
             ("Manrope", fonts["manrope-400"], 400),
             ("Manrope", fonts["manrope-600"], 600),
             ("JetBrains Mono", fonts["jetbrains-400"], 400)]
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
    body.append(
        f'<text class="dsp an-rise" x="48" y="46" font-size="22" fill="{th["ink"]}">'
        f'TODOS LOS D&#205;AS, <tspan fill="{th["accent"]}">EN ROJO</tspan></text>'
    )
    body.append(
        f'<text class="mono wide an-rise" style="animation-delay:60ms" x="{w - 48}" y="44" '
        f'font-size="10" text-anchor="end" fill="{th["muted"]}">Se redibuja a diario</text>'
    )
    peak_line = f'pico {peak["count"]} el {fmt_date(peak["date"])}' if peak else "aún sin picos"
    body.append(
        f'<text class="an-rise" style="animation-delay:80ms" x="48" y="68" font-size="12.5" '
        f'fill="{th["muted"]}"><tspan font-weight="600" fill="{th["ink"]}">{total}</tspan> contribuciones · '
        f'{active_days(days)} días activos · {peak_line}</text>'
    )

    # grid: pop in left to right
    gx, gy, pitch, size = 48, 80, 14, 11
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
    data = load_json(ROOT / "data" / "contributions.json")
    fonts = {p.stem: p for p in (ROOT / "fonts").glob("*.woff")}
    required = {"anton-400", "manrope-400", "manrope-600", "jetbrains-400"}
    missing = required - set(fonts)
    if missing:
        print(f"missing fonts: {missing} — run scripts/build_fonts.py", file=sys.stderr)
        return 1
    th = dict(prof["theme"], muted=prof["theme"]["inkMuted"])

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
