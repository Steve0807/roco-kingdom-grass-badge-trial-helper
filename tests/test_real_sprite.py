"""The one piece of real game art in this repository, checked at many sizes.

`docs/screenshot-*.png` are screenshots of the app itself, but the two large
panels in them hold a *real* in-game sprite straight off the author's screen -
one panel the pasted screenshot crop, the other the same sprite after the app
normalised it.  That is real art: a beveled disc on the game's own textured
background, not the synthetic icons `test_pipeline.py` draws.

So this script takes the real sprite out of the screenshot, stores it in a
database, and asks the app to recognise it again the way the live watcher has
to: at other sizes, with other crops, and with a bit of the screen's noise.
It does *not* test telling two different spirits apart - that needs a real
multi-sprite sheet, which is what tests/test_real_icons.py is for (and which
skips when the sample folder is not to hand).

    python tests/test_real_sprite.py
"""
from __future__ import annotations

import random
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from iconmatch import imaging                       # noqa: E402
from iconmatch.database import IconDB               # noqa: E402

DOCS = Path(__file__).resolve().parent.parent / "docs"
SHOTS = ("screenshot-zh.png", "screenshot-en.png")
MIN_PANEL, MAX_PANEL = 200, 520      # the icon panels' side, in pixels
MIN_FILL = 0.6                       # how solid a panel rectangle has to be
MIN_SIM = 0.90                       # every re-seen sprite must clear this


def find_panels(path: Path) -> list[tuple[int, int, int, int]]:
    """The two sprite panels, left to right, as (left, top, right, bottom).

    The app paints every panel with its canonical background, so the panels are
    exactly the columns that hold a lot of that colour: one span of columns for
    each of them, and inside a span the rows that are equally busy.  Doing it by
    projection rather than by walking pixels keeps this instant.
    """
    arr = np.asarray(Image.open(path).convert("RGB")).astype(np.int16)
    canon = np.abs(arr - np.array(imaging.config.CANON_BG, dtype=np.int16)).max(axis=2)
    mask = canon <= 12
    if not mask.any():
        return []

    busy_col = mask.sum(axis=0) > 0.25 * mask.sum(axis=0).max()
    busy_row = mask.sum(axis=1) > 0.25 * mask.sum(axis=1).max()
    cols = _spans(busy_col)
    rows = _spans(busy_row)
    boxes = []
    for c0, c1 in cols:
        for r0, r1 in rows:
            w, h = c1 - c0, r1 - r0
            if not (MIN_PANEL <= w <= MAX_PANEL and MIN_PANEL <= h <= MAX_PANEL):
                continue
            inside = mask[r0:r1, c0:c1]
            if inside.mean() >= MIN_FILL:
                boxes.append((c0, r0, c1, r1, w * h))
    boxes.sort(key=lambda b: -b[4])
    return sorted(b[:4] for b in boxes[:2])


def _spans(flags: np.ndarray) -> list[tuple[int, int]]:
    """Contiguous runs of True, as (start, end) pairs."""
    out, start = [], None
    for i, flag in enumerate(flags):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            out.append((start, i))
            start = None
    if start is not None:
        out.append((start, len(flags)))
    return out


def variants(crop: Image.Image, seed: int) -> list[Image.Image]:
    """The same sprite as another encounter would show it: other size, other crop."""
    rng = random.Random(seed)
    w, h = crop.size
    out = [crop.resize((max(8, int(w * s)), max(8, int(h * s))), Image.LANCZOS)
           for s in (0.45, 0.7, 1.0, 1.35, 1.8)]
    for _ in range(4):
        side = int(min(w, h) * rng.uniform(0.72, 1.0))
        ox = (w - side) // 2 + rng.randint(-8, 8)
        oy = (h - side) // 2 + rng.randint(-8, 8)
        out.append(crop.crop((max(0, ox), max(0, oy), max(0, ox) + side, max(0, oy) + side)))
    arr = np.asarray(crop).astype(np.int16)          # lighting / texture drift
    out.append(Image.fromarray(
        np.clip(arr + rng.randint(-5, 5) + np.random.default_rng(seed).integers(-4, 5, arr.shape),
                0, 255).astype(np.uint8), "RGB"))
    return out


def main() -> int:
    missing = [n for n in SHOTS if not (DOCS / n).is_file()]
    if missing:
        print(f"doc screenshots not available ({', '.join(missing)}) - skipped")
        return 0

    failures: list[str] = []
    tmp = Path(tempfile.mkdtemp(prefix="iconmatch_real_"))
    try:
        panels = find_panels(DOCS / SHOTS[0])
        print(f"real sprite panels in {SHOTS[0]}: {panels}")
        if len(panels) != 2:
            print("could not find the two sprite panels - skipped")
            return 0
        l, t, r, b = panels[0]
        sprite = Image.open(DOCS / SHOTS[0]).convert("RGB").crop((l + 3, t + 3, r - 2, b - 2))

        db = IconDB.create(tmp, 1, "real")
        db.add(sprite, "real_sprite")
        print(f"stored one real sprite of {sprite.size[0]}x{sprite.size[1]}px")

        hits, worst = 0, 1.0
        for i, v in enumerate(variants(sprite, 7)):
            found = db.search(v, top=1)
            hits += db.is_match(found)
            worst = min(worst, found.similarity)
            print(f"  {str(v.size):>12}  similarity {found.similarity:.3f}  "
                  f"stand-out {found.confidence:.3f}  "
                  f"{'Y' if db.is_match(found) else 'N'}")
            if not db.is_match(found):
                failures.append(f"the real sprite at {v.size} was not recognised "
                                f"(similarity {found.similarity:.3f}, "
                                f"stand-out {found.confidence:.3f})")
        print(f"  recognised {hits}/{len(variants(sprite, 7))}, worst similarity {worst:.3f}")
        if hits and worst < MIN_SIM:
            failures.append(f"worst similarity {worst:.3f} is below {MIN_SIM}")

        # the same sprite as the other screenshot shows it (a second real capture)
        for name in SHOTS[1:]:
            other = find_panels(DOCS / name)
            if len(other) != 2:
                continue
            l, t, r, b = other[0]
            crop = Image.open(DOCS / name).convert("RGB").crop((l + 3, t + 3, r - 2, b - 2))
            found = db.search(crop, top=1)
            print(f"  {name}: similarity {found.similarity:.3f}  "
                  f"stand-out {found.confidence:.3f}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for line in failures:
        print("  FAIL:", line)
    print("RESULT:", "PASS" if not failures else "FAIL")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
