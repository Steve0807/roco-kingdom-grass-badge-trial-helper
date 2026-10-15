"""Turn an arbitrary screenshot crop of one icon into a canonical RGBA tile.

The pipeline is deliberately independent of the black round frame that most
icons sit on: some icons (horns, wings, tails) stick out of that circle, so we
segment against the *background* colour instead and keep everything that is
not background.
"""
from __future__ import annotations

from collections import deque
from typing import NamedTuple

import numpy as np
from PIL import Image, ImageFilter

from . import config


# ---------------------------------------------------------------- loading
def to_rgb(img: Image.Image, bg=config.CANON_BG) -> Image.Image:
    """Flatten any mode (incl. transparency) onto a solid background."""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        flat = Image.new("RGB", img.size, bg)
        flat.paste(img, mask=img.split()[-1])
        return flat
    return img.convert("RGB")


# ------------------------------------------------------------ background
def estimate_background(arr: np.ndarray) -> np.ndarray:
    """Median colour of the outer frame of the image."""
    h, w = arr.shape[:2]
    b = max(1, int(round(min(h, w) * 0.06)))
    ring = np.concatenate([
        arr[:b, :, :].reshape(-1, 3),
        arr[-b:, :, :].reshape(-1, 3),
        arr[:, :b, :].reshape(-1, 3),
        arr[:, -b:, :].reshape(-1, 3),
    ])
    return np.median(ring, axis=0)


def foreground_mask(arr: np.ndarray, bg: np.ndarray, tol: int = config.BG_TOL) -> np.ndarray:
    diff = np.abs(arr.astype(np.int16) - bg.astype(np.int16)).max(axis=2)
    return diff > tol


def _clean(mask: np.ndarray) -> np.ndarray:
    """Erode away background texture speckle, then dilate back."""
    m = Image.fromarray((mask * 255).astype(np.uint8), "L")
    m = m.filter(ImageFilter.MinFilter(3))
    m = m.filter(ImageFilter.MaxFilter(5))
    return np.asarray(m) > 127


class Blob(NamedTuple):
    """The icon found in an image, in full-resolution pixel coordinates."""
    bbox: tuple[int, int, int, int]
    cx: float
    cy: float
    area: float

    @property
    def equivalent_diameter(self) -> float:
        """Diameter of a disc with the same area.

        Framing on this instead of on the bounding box is what makes the crop
        reproducible: a tight screenshot that clips an ear or a tail changes
        the bounding box abruptly, but barely moves the area or the centroid.
        """
        return 2.0 * np.sqrt(max(self.area, 1.0) / np.pi)


def largest_component(mask: np.ndarray, max_side: int = 192) -> Blob | None:
    """Largest 8-connected blob of the mask, in full-resolution coordinates."""
    blobs = find_blobs(mask, max_side)
    return max(blobs, key=lambda b: b.area) if blobs else None


def largest_blob(img: Image.Image) -> Blob | None:
    """The biggest thing in `img` that is not background, or None if there is none.

    The segmentation :func:`normalize` runs, on its own, so a caller can ask
    "is there an icon in this picture at all?" before deciding to crop it.
    """
    arr = np.asarray(to_rgb(img))
    return largest_component(_clean(foreground_mask(arr, estimate_background(arr))))


def find_blobs(mask: np.ndarray, max_side: int = 192) -> list[Blob]:
    """Every 8-connected blob of the mask, in full-resolution coordinates."""
    h, w = mask.shape
    scale = min(1.0, max_side / max(h, w))
    if scale < 1.0:
        small = np.asarray(
            Image.fromarray((mask * 255).astype(np.uint8), "L").resize(
                (max(1, int(w * scale)), max(1, int(h * scale))), Image.BILINEAR
            )
        ) > 127
    else:
        small = mask
    sh, sw = small.shape

    seen = np.zeros_like(small, dtype=bool)
    inv = 1.0 / scale if scale < 1.0 else 1.0
    blobs: list[Blob] = []
    ys, xs = np.nonzero(small)
    for y0, x0 in zip(ys.tolist(), xs.tolist()):
        if seen[y0, x0]:
            continue
        q = deque([(y0, x0)])
        seen[y0, x0] = True
        area = 0
        sum_x = sum_y = 0
        t = b = y0
        l = r = x0
        while q:
            y, x = q.popleft()
            area += 1
            sum_x += x
            sum_y += y
            if y < t: t = y
            if y > b: b = y
            if x < l: l = x
            if x > r: r = x
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < sh and 0 <= nx < sw and small[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        q.append((ny, nx))
        blobs.append(Blob(
            bbox=(max(0, int(l * inv) - 1),
                  max(0, int(t * inv) - 1),
                  min(w - 1, int((r + 1) * inv) + 1),
                  min(h - 1, int((b + 1) * inv) + 1)),
            cx=(sum_x / area) * inv,
            cy=(sum_y / area) * inv,
            area=area * inv * inv,
        ))
    return blobs


# ------------------------------------------------------------ normalise
def normalize(img: Image.Image,
              margin: float = config.MARGIN,
              size: int = config.NORM_SIZE) -> Image.Image:
    """Crop to the icon, square it up, and rescale to a canonical RGBA tile.

    Alpha marks the icon pixels; RGB background is flattened to CANON_BG so
    that background texture/lighting differences cannot influence matching.
    """
    rgb = to_rgb(img)
    arr = np.asarray(rgb)
    h, w = arr.shape[:2]

    bg = estimate_background(arr)
    blob = largest_component(_clean(foreground_mask(arr, bg)))
    if blob is None:                      # nothing found -> use the whole frame
        cx, cy, side = w / 2.0, h / 2.0, float(min(w, h))
    else:
        cx, cy = blob.cx, blob.cy
        side = blob.equivalent_diameter * config.FRAME_FACTOR
    side *= 1.0 + 2 * margin
    half = side / 2.0

    # paste onto a background-coloured canvas so an off-image crop is padded,
    # not clipped (icons often touch the edge of a tight screenshot)
    canvas = Image.new("RGB", (int(round(side)), int(round(side))),
                       tuple(int(v) for v in bg))
    canvas.paste(rgb, (int(round(-(cx - half))), int(round(-(cy - half)))))
    tile = canvas.resize((size, size), Image.LANCZOS)

    tarr = np.asarray(tile)
    tmask = foreground_mask(tarr, bg)
    tmask = np.asarray(
        Image.fromarray((tmask * 255).astype(np.uint8), "L").filter(ImageFilter.MedianFilter(3))
    ) > 127

    out = tarr.copy()
    out[~tmask] = np.array(config.CANON_BG, dtype=np.uint8)
    rgba = np.dstack([out, (tmask * 255).astype(np.uint8)])
    return Image.fromarray(rgba, "RGBA")


def flatten(tile: Image.Image, bg=config.CANON_BG) -> Image.Image:
    """Normalised tile -> plain RGB, for display."""
    return to_rgb(tile, bg)


# --------------------------------------------------------------- grid split
def _cluster(values: list[float], gap: float) -> list[int]:
    """Index of the cluster each value belongs to, splitting on gaps > `gap`."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    index = [0] * len(values)
    group = 0
    for pos, i in enumerate(order):
        if pos and values[i] - values[order[pos - 1]] > gap:
            group += 1
        index[i] = group
    return index


def _bbox_gap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    """Distance between two bounding boxes (0 if they overlap)."""
    dx = max(b[0] - a[2], a[0] - b[2], 0)
    dy = max(b[1] - a[3], a[1] - b[3], 0)
    return float(np.hypot(dx, dy))


def split_grid(img: Image.Image, min_icons: int = 2) -> list[Image.Image]:
    """Cut a screenshot holding a grid of icons into one crop per icon.

    The grid does not have to be of any particular size, and rows do not have
    to be full: icons are found as blobs of non-background, grouped into rows
    and columns by the gaps between them, and cut apart on those gaps.  Returns
    [] when the image holds a single icon (or nothing recognisable), so callers
    can fall back to treating it as one.
    """
    rgb = to_rgb(img)
    arr = np.asarray(rgb)
    h, w = arr.shape[:2]
    bg = estimate_background(arr)
    blobs = find_blobs(_clean(foreground_mask(arr, bg)))
    if len(blobs) < min_icons:
        return []

    # drop specks: text, borders, bits of background texture
    biggest = max(b.area for b in blobs)
    blobs = [b for b in blobs if b.area >= 0.12 * biggest]
    if len(blobs) < min_icons:
        return []

    # one icon can break into several blobs (a floating tail, a detached ear),
    # so group by grid cell rather than trusting the blob count
    typical = float(np.median([b.equivalent_diameter for b in blobs]))
    rows = _cluster([b.cy for b in blobs], typical * 0.55)
    cols = _cluster([b.cx for b in blobs], typical * 0.55)

    cells: dict[tuple[int, int], list[Blob]] = {}
    for blob, r, c in zip(blobs, rows, cols):
        cells.setdefault((r, c), []).append(blob)
    if len(cells) < min_icons:
        return []

    boxes = {}
    for key, group in cells.items():
        boxes[key] = (min(b.bbox[0] for b in group), min(b.bbox[1] for b in group),
                      max(b.bbox[2] for b in group), max(b.bbox[3] for b in group))

    crops = []
    for key in sorted(boxes):                      # reading order: row, then column
        l, t, r, b = boxes[key]
        # pad, but never more than halfway to the nearest neighbouring icon
        room = min((_bbox_gap(boxes[key], other)
                    for other_key, other in boxes.items() if other_key != key),
                   default=float(max(w, h)))
        pad = int(min(0.12 * max(r - l, b - t), 0.45 * room))
        crops.append(rgb.crop((max(0, l - pad), max(0, t - pad),
                               min(w, r + 1 + pad), min(h, b + 1 + pad))))
    return crops
