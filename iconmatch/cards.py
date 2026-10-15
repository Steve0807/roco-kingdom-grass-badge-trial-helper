"""Read the game's "pick a spirit to fight" screen: the cards, and the portraits.

The trial offers three spirits at a time: three cards in a row, each one a big
dark panel (name, trait, rewards) with a round portrait of the spirit sitting on
the panel's top edge.  The portraits are what the database knows about, so this
module finds the row of cards and cuts each portrait out of it.

A portrait comes out as a *disc*: a square crop around the round frame, with
everything outside it flattened onto the canonical background.  What is left is
the spirit itself - not the card, not the little element/gender badges hanging
off the disc, not the grass behind it - which is exactly the shape an icon has
in the database, so a spirit seen in the game matches the one stored earlier.

The cards are found by their panels rather than by the portraits, because a
panel is a large, uniform, colourless block that nothing in the scenery
resembles, while circles are everywhere on a game screen.  Each dimension is a
fraction of the panel's own height, so nothing here depends on the game's UI
scale.
"""
from __future__ import annotations

from statistics import median

import numpy as np
from PIL import Image

from . import config, imaging


def _panels(frame: Image.Image) -> list[imaging.Blob]:
    """The dark, colourless blocks on screen - the bodies of the cards.

    The neutrality is what makes this reliable: grass, trees, rocks and the
    game's own UI are all either bright or coloured, and the panel is neither.
    """
    arr = np.asarray(imaging.to_rgb(frame)).astype(np.int16)
    hi = arr.max(axis=2)
    lo = arr.min(axis=2)
    mask = (hi < config.SELECT_PANEL_DARK) & (hi - lo <= config.SELECT_PANEL_SPREAD)

    height, width = mask.shape
    out = []
    # a fine analysis scale: every later dimension - where the portrait sits,
    # how big it is - is derived from these boxes
    for blob in imaging.find_blobs(mask, max_side=1024):
        left, top, right, bottom = blob.bbox
        w, h = right - left, bottom - top
        if w < config.SELECT_PANEL_MIN_W * width or h < config.SELECT_PANEL_MIN_H * height:
            continue
        low, high = config.SELECT_PANEL_ASPECT
        if not low <= w / h <= high:
            continue
        if blob.area < config.SELECT_PANEL_FILL * w * h:
            continue
        out.append(blob)
    return out


def row(frame: Image.Image) -> list[imaging.Blob]:
    """The cards on screen, left to right - [] unless this really is that screen.

    A row has to agree on a shelf, on a size and on an even spacing, because
    two dark panels somewhere on a game screen are otherwise easy to come by.
    """
    panels = _panels(frame)
    frame_h = frame.height

    shelves: list[list[imaging.Blob]] = []
    for blob in sorted(panels, key=lambda b: b.cy):
        for shelf in shelves:
            if abs(shelf[0].bbox[1] - blob.bbox[1]) <= config.SELECT_CARD_TOP_TOL * frame_h:
                shelf.append(blob)
                break
        else:
            shelves.append([blob])

    best: list[imaging.Blob] = []
    for shelf in shelves:
        if len(shelf) < config.SELECT_CARDS_MIN or len(shelf) <= len(best):
            continue
        row_ = sorted(shelf, key=lambda b: b.cx)
        widths = [b.bbox[2] - b.bbox[0] for b in row_]
        heights = [b.bbox[3] - b.bbox[1] for b in row_]
        mid_w, mid_h = median(widths), median(heights)
        tol = config.SELECT_CARD_SIZE_TOL
        if any(abs(w - mid_w) > tol * mid_w or abs(h - mid_h) > tol * mid_h
               for w, h in zip(widths, heights)):
            continue
        gaps = [b.cx - a.cx for a, b in zip(row_, row_[1:])]
        low, high = config.SELECT_CARD_GAP
        if min(gaps) < low * mid_w or max(gaps) > high * mid_w:
            continue
        best = row_
    return best


def disc_crop(frame: Image.Image, cx: float, cy: float, radius: float) -> Image.Image:
    """A square crop around a portrait, with everything outside the disc gone."""
    side = int(round(2 * radius * config.SELECT_PORTRAIT_MARGIN))
    left, top = int(round(cx - side / 2)), int(round(cy - side / 2))
    rgb = imaging.to_rgb(frame)

    # a crop that reaches past the edge of the frame is padded, not clipped:
    # PIL fills an out-of-bounds crop with black, which would read as disc
    canvas = Image.new("RGB", (side, side), config.CANON_BG)
    src = rgb.crop((max(0, left), max(0, top),
                    min(rgb.width, left + side), min(rgb.height, top + side)))
    canvas.paste(src, (max(0, -left), max(0, -top)))

    arr = np.asarray(canvas).copy()
    yy, xx = np.mgrid[0:side, 0:side]
    outside = np.hypot(yy - (side - 1) / 2, xx - (side - 1) / 2) > \
        radius * config.SELECT_PORTRAIT_KEEP
    arr[outside] = config.CANON_BG
    return Image.fromarray(arr, "RGB")


def _is_portrait(crop: Image.Image, radius: float) -> bool:
    """Whether that disc holds artwork, rather than a plain piece of panel.

    A portrait is bright or at least colourful; a panel is flat dark grey, so
    the two are told apart by either measure on its own.
    """
    arr = np.asarray(crop)
    hi = arr.max(axis=2)
    side = arr.shape[0]
    yy, xx = np.mgrid[0:side, 0:side]
    inside = np.hypot(yy - (side - 1) / 2, xx - (side - 1) / 2) <= radius
    bright = float((hi[inside] >= 140).mean())
    spread = float(hi[inside].std())
    return bright >= config.SELECT_PORTRAIT_BRIGHT or spread >= config.SELECT_PORTRAIT_SPREAD


def offers(frame: Image.Image) -> list[tuple[Image.Image, tuple[int, int, int, int]]]:
    """The spirits offered on the pick-a-spirit screen, each with where it sits.

    A screen that is not that screen - the world, a fight, a menu, this app's
    own window - has no row of cards on it, so nothing is returned and the
    caller has nothing to compare or to make a noise about.
    """
    row_ = row(frame)
    if not row_:
        return []

    out: list[tuple[Image.Image, tuple[int, int, int, int]]] = []
    for card in row_:
        height = card.bbox[3] - card.bbox[1]
        cx = card.cx
        cy = card.bbox[1] - config.SELECT_PORTRAIT_RISE * height
        radius = config.SELECT_PORTRAIT_RADIUS * height
        crop = disc_crop(frame, cx, cy, radius)
        if _is_portrait(crop, radius):
            side = crop.width
            out.append((crop, (int(round(cx - side / 2)), int(round(cy - side / 2)),
                               int(round(cx - side / 2)) + side,
                               int(round(cy - side / 2)) + side)))
    return out if len(out) >= config.SELECT_CARDS_MIN else []


def portraits(frame: Image.Image) -> list[Image.Image]:
    """The spirits offered on the pick-a-spirit screen, or [] on any other screen."""
    return [crop for crop, _box in offers(frame)]
