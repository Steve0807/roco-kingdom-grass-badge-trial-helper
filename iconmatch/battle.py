"""Read the battle screen: which of the spirits on offer is the one being fought.

A round of the trial goes: three spirits are offered, the player picks one, and
the fight starts.  The battle HUD names the opponent at the top right - its
portrait, its name and its level - and that portrait is the same art as the one
on the card, drawn closer (the battle header zooms in on the head).

Because the framing differs, that portrait does not match the database on its
own: on a real capture the opponent scored 0.74 against its own stored icon, but
0.70 against two quite different spirits.  What it separates well instead is the
short list of spirits that were just on offer - there the opponent's own card
scored 0.76 while the other two scored 0.55 and 0.65.  So that is what this
module compares, and it insists on a clear lead before it will answer.

Being wrong is expensive: storing a spirit as fought which was not fought would
make the helper skip a spirit that still pays a reward.  A comparison that is
not clear therefore answers nothing at all, and the choice stays with the player.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

from . import config, features, imaging

# the crop, in the frame's own pixels
def _box(size: tuple[int, int]) -> tuple[int, int, int, int]:
    width, height = size
    cx = config.BATTLE_ENEMY_CENTRE[0] * width
    cy = config.BATTLE_ENEMY_CENTRE[1] * height
    half = config.BATTLE_ENEMY_HALF * width
    return (int(round(cx - half)), int(round(cy - half)),
            int(round(cx + half)), int(round(cy + half)))


def _looks_like_hud(frame: Image.Image) -> bool:
    """Whether that corner holds a portrait on a dark disc, not just scenery.

    A portrait is dark (the disc and the shading of the spirit) *and* light
    (the spirit's own colours) in one small patch; plain sky is only light and
    plain foliage is only dark-ish, so one look at the corner is enough to stop
    the expensive comparison from running on every screen the player walks past.
    """
    rgb = imaging.to_rgb(frame)
    left, top, right, bottom = _box(frame.size)
    win = np.asarray(rgb.crop((max(0, left), max(0, top),
                               min(rgb.width, right), min(rgb.height, bottom)))).astype(np.int16)
    if win.size == 0:
        return False
    hi = win.max(axis=2)
    dark = float((hi < config.SELECT_PANEL_DARK).mean())
    bright = float((hi >= 150).mean())
    return dark >= 0.10 and bright >= 0.10


def opponent(frame: Image.Image) -> Image.Image:
    """The opponent's portrait off the battle HUD, as a normalised tile.

    The HUD keeps it at a fixed spot, so the crop is taken by position rather
    than by looking for a circle: the portrait is drawn over trees, sky and its
    own name plate, and no circle-finder picks it out reliably - while the
    position is the same in every fight.
    """
    left, top, right, bottom = _box(frame.size)
    rgb = imaging.to_rgb(frame)
    canvas = Image.new("RGB", (right - left, bottom - top), config.CANON_BG)
    src = rgb.crop((max(0, left), max(0, top),
                    min(rgb.width, right), min(rgb.height, bottom)))
    canvas.paste(src, (max(0, -left), max(0, -top)))
    return imaging.normalize(canvas)


def offer_matrix(tiles: list[Image.Image]) -> np.ndarray:
    """The descriptors of the spirits on offer, ready to be scored against."""
    if not tiles:
        return np.zeros((0, 0), dtype=np.float32)
    return np.stack([features.describe(tile) for tile in tiles]).astype(np.float32)


def fought(frame: Image.Image, vecs: np.ndarray) -> tuple[int, float, float] | None:
    """Which of the spirits on offer is being fought, if it is clear enough.

    `vecs` are the descriptors from :func:`offer_matrix`.  Answers (index, its
    score, the best of the others) when the opponent looks clearly more like one
    of them than like the rest, and None when the picture is not a battle HUD
    at all or when the answer would be a guess.
    """
    if vecs.size == 0 or len(vecs) < 2 or not _looks_like_hud(frame):
        return None
    scores = features.score_matrix(features.describe_query(opponent(frame)), vecs)
    order = np.argsort(-scores)
    best, second = float(scores[order[0]]), float(scores[order[1]])
    if best < config.BATTLE_MATCH_MIN or best - second < config.BATTLE_MATCH_MARGIN:
        return None
    return int(order[0]), best, second
