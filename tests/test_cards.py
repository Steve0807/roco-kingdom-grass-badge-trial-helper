"""The pick-a-spirit screen: finding the cards, and the portrait on each.

Two kinds of screen are used here.  ``对局内画面.png`` in the project root is a
real still of the trial: three spirits on offer, grass, trees, sky and the game's
whole HUD around them - the screen that used to be read as one enormous "icon".
And a synthetic one, laid out the way the game lays it out but at another size,
so the geometry is exercised on a screen this repository draws itself.

    python tests/test_cards.py
"""
from __future__ import annotations

import random
import shutil
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from iconmatch import cards, config, watcher          # noqa: E402
from iconmatch.database import IconDB                 # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SHOT = ROOT / "对局内画面.png"

# the layout, as the real screenshot measures it (2560x1440)
PANEL_RATIO = 435 / 275          # panel width / height
CARD_GAP_RATIO = 480 / 2560      # centre-to-centre, in frame widths
CARD_X_RATIO = 802 / 2560        # first card's centre
PANEL_TOP_RATIO = 539 / 1440
PANEL_H_RATIO = 274 / 1440
PANEL_RGB = (42, 45, 46)         # the panel, straight off the screenshot
SKY_RGB = (150, 205, 230)
GRASS_RGB = (120, 170, 90)


def fake_screen(width: int = 1280, height: int = 720, seeds=(1, 2, 3)) -> Image.Image:
    """A screen laid out like the trial's: three cards, a portrait on each."""
    img = Image.new("RGB", (width, height), GRASS_RGB)
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, width, height * 0.35), fill=SKY_RGB)

    panel_h = int(height * PANEL_H_RATIO)
    panel_w = int(panel_h * PANEL_RATIO)
    top = int(height * PANEL_TOP_RATIO)
    radius = int(config.SELECT_PORTRAIT_RADIUS * panel_h)
    for n, seed in enumerate(seeds):
        cx = int(width * (CARD_X_RATIO + n * CARD_GAP_RATIO))
        draw.rectangle((cx - panel_w // 2, top, cx + panel_w // 2, top + panel_h),
                       fill=PANEL_RGB)
        disc = fake_spirit(seed, 2 * radius)
        img.paste(disc, (cx - radius, top - int(config.SELECT_PORTRAIT_RISE * panel_h)
                         - radius))
    return img


def fake_spirit(seed: int, size: int) -> Image.Image:
    """One portrait: a dark round frame with a coloured creature on it."""
    img = Image.new("RGB", (size, size), (246, 241, 228))
    draw = ImageDraw.Draw(img)
    rng = random.Random(seed)
    draw.ellipse((0, 0, size - 1, size - 1), fill=(28, 30, 40))
    body = (rng.randint(60, 240), rng.randint(60, 240), rng.randint(60, 240))
    draw.ellipse((size * 0.18, size * 0.26, size * 0.82, size * 0.88), fill=body)
    draw.ellipse((size * 0.30, size * 0.50, size * 0.44, size * 0.64), fill=(250, 250, 250))
    draw.ellipse((size * 0.56, size * 0.50, size * 0.70, size * 0.64), fill=(250, 250, 250))
    return img


def check_layout(failures):
    """The synthetic screen: three cards found, one portrait each, evenly spaced."""
    screen = fake_screen()
    row = cards.row(screen)
    if len(row) != 3:
        failures.append(f"the fake screen should show 3 cards, found {len(row)}")
    else:
        gaps = [b.cx - a.cx for a, b in zip(row, row[1:])]
        if max(gaps) - min(gaps) > 0.02 * max(gaps):
            failures.append(f"the fake cards are not evenly spaced: {gaps}")

    found = cards.portraits(screen)
    if len(found) != 3:
        failures.append(f"3 portraits expected on the fake screen, got {len(found)}")
    for crop in found:
        if crop.width > 0.1 * screen.width:
            failures.append(f"a portrait crop of {crop.size} is too big to be one disc")
    print(f"layout      : fake 1280x720 screen -> {len(row)} cards, "
          f"{len(found)} portraits  ok")


def check_fake_recording(failures, tmp):
    """Store the three fake spirits, then meet them again at another size."""
    screen = fake_screen()
    db = IconDB.create(tmp, 3, "fake_screen")
    for n, crop in enumerate(cards.portraits(screen)):
        db.add(crop, f"fake_{n}")

    smaller = fake_screen(width=960, height=540)
    detections = watcher.scan(db, smaller)
    if len(detections) != 3:
        failures.append(f"3 spirits expected at 960x540, got {len(detections)}")
    else:
        for det in detections:
            if det.state != watcher.PLAYED:
                failures.append(f"a stored fake spirit came back as {det.state} "
                                f"(best {det.best.id if det.best else None}, "
                                f"similarity {det.similarity:.3f}, "
                                f"stand-out {det.confidence:.3f})")
            if not det.encounter:
                failures.append("a spirit off the card screen should be an encounter")
    print(f"fake db     : stored 3, met them again at 960x540 -> "
          f"{[d.state for d in detections]}  ok")


def check_scenes(failures):
    """Anything that is not that screen is nothing: no crops, so no alarms."""
    big = Image.new("RGB", (1600, 900), GRASS_RGB)
    ImageDraw.Draw(big).rectangle((40, 40, 1560, 860), fill=(60, 90, 50))
    if watcher.crops_of(big):
        failures.append("a large frame holding one huge blob is a scene, not an icon")

    blank = Image.new("RGB", (1600, 900), GRASS_RGB)
    if watcher.crops_of(blank):
        failures.append("an empty scene should give nothing to compare")

    # the screen with its cards painted out: the panel row is what identifies it
    if SHOT.is_file():
        shot = Image.open(SHOT).convert("RGB").copy()
        draw = ImageDraw.Draw(shot)
        for box in ((500, 360, 1100, 900), (980, 360, 1580, 900), (1450, 320, 2090, 900)):
            draw.rectangle(box, fill=GRASS_RGB)
        if cards.portraits(shot):
            failures.append("cards painted over, yet portraits were still reported")
    print("scenes      : big blob, empty patch, cards painted out -> nothing  ok")


def check_real_screen(failures, tmp):
    """The real screenshot: three spirits, each found, none of them the screen."""
    if not SHOT.is_file():
        print(f"real screen : {SHOT.name} not available - skipped")
        return

    shot = Image.open(SHOT).convert("RGB")
    found = cards.portraits(shot)
    if len(found) != 3:
        failures.append(f"3 spirits expected on the real screen, got {len(found)}")
        return
    for crop in found:
        if max(crop.size) > 0.1 * shot.width:
            failures.append(f"a crop of {crop.size} is most of the screen, not a portrait")
    if [c.size for c in watcher.crops_of(shot)] != [c.size for c in found]:
        failures.append("the watcher did not take the portraits off that screen")

    # three different spirits, not the same one three times: every crop has to
    # match the icon stored from that crop, and not one of its neighbours
    db = IconDB.create(tmp, 1, "real_screen")
    for n, crop in enumerate(found):
        db.add(crop, f"spirit_{n}")
    for n, crop in enumerate(found):
        best = db.search(crop, top=1).best
        if best is None or best.name != f"spirit_{n}":
            failures.append(f"portrait {n} matched {best.name if best else None} "
                            f"instead of itself")

    # and met again on a screen captured at another size
    for factor in (0.8, 1.3):
        again = shot.resize((int(shot.width * factor), int(shot.height * factor)),
                            Image.LANCZOS)
        detections = watcher.scan(db, again)
        states = [d.state for d in detections]
        if len(detections) != 3 or any(s != watcher.PLAYED for s in states):
            failures.append(f"the same three spirits at {factor:.2f}x came back "
                            f"as {states} "
                            f"({[round(d.similarity, 3) for d in detections]})")
        else:
            print(f"real screen : {shot.size} and {factor:.2f}x -> 3/3 'already fought'  ok")
    print(f"real screen : 3 portraits of {[c.size for c in found]}, "
          f"all distinguishable  ok")


def main() -> int:
    failures: list[str] = []
    tmp = Path(tempfile.mkdtemp(prefix="iconmatch_cards_"))
    try:
        check_layout(failures)
        check_scenes(failures)
        check_fake_recording(failures, tmp)
        check_real_screen(failures, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for line in failures:
        print("  FAIL:", line)
    print("RESULT:", "PASS" if not failures else "FAIL")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
