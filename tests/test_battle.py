"""The battle screen, and a card screen whose spirits have been re-rolled.

Two things the watcher has to get right beyond reading a card screen:

* A re-rolled card screen - one or three new spirits on the same cards - is a
  change of *one portrait* on a whole screen, which a coarse whole-screen
  comparison cannot see.  The portraits found last time are therefore compared
  at their own resolution, so the new spirits are picked up without the player
  pressing anything.
* The battle that follows names the opponent at the top right.  Which of the
  spirits on offer that is, is decided by comparing them, and only a clear lead
  answers at all (see iconmatch/battle.py).

    python tests/test_battle.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_cards import fake_screen, fake_spirit              # noqa: E402
from iconmatch import battle, cards, config, imaging, watcher  # noqa: E402
from iconmatch.database import IconDB                         # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BATTLE_SHOT = ROOT / "战斗画面.png"
CARD_SHOT = ROOT / "对局内画面.png"
USER_ROOT = Path(r"C:\Users\minec\Desktop")     # the author's own database, if to hand
USER_OPPONENT = "0238"                          # the spirit this fight is against
MIN_REAL_SCORE = 0.70                           # measured 0.76 for that spirit


class Script:
    """A stand-in for the screen: hands out the next frame on every shot."""

    def __init__(self, frames):
        self.frames = list(frames)

    def __call__(self, region=None):
        if len(self.frames) > 1:
            return self.frames.pop(0)
        return self.frames[0]


def check_reroll(failures):
    """One card re-rolled on an otherwise identical screen must be picked up."""
    before = fake_screen(seeds=(1, 2, 3))
    after = fake_screen(seeds=(1, 9, 3))            # the middle card re-rolled

    coarse = watcher.looks_same(watcher.fingerprint(before), watcher.fingerprint(after))
    boxes = [box for _crop, box in cards.offers(before)]
    if len(boxes) != 3:
        failures.append(f"the fake card screen should offer 3 portraits, got {len(boxes)}")
        return
    if not coarse:
        print("reroll      : the whole-screen comparison already sees it - "
              "the focused comparison is not what this test needs")
        return

    watch = watcher.ScreenWatcher(interval=0.01, grabber=Script(
        [before, before, after, after, after, before, before]))
    watch.region = watcher.Region(0, 0, 1280, 720)     # the grabber ignores it
    watch.focus_on(before, boxes)
    got = [watch.poll() is not None for _ in range(7)]
    if got != [False, True, False, True, False, False, True]:
        failures.append(f"a re-rolled screen gave {got}, expected "
                        f"[F, T, F, T, F, F, T] (report once per new screen)")
    else:
        print("reroll      : one card re-rolled on a coarse-identical screen -> "
              "picked up on its own  ok")


def synthetic_hud(spirit_tile: Image.Image, size=(1280, 720)) -> Image.Image:
    """A battle HUD like the game's: a dark disc with the opponent's head on it."""
    img = Image.new("RGB", size, (120, 170, 90))
    draw = ImageDraw.Draw(img)
    width, height = size
    cx, cy = config.BATTLE_ENEMY_CENTRE[0] * width, config.BATTLE_ENEMY_CENTRE[1] * height
    radius = config.BATTLE_ENEMY_HALF * width * 0.7
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(28, 30, 40))
    # the battle header draws the spirit closer than the card does: the head only
    inner = radius * 0.75
    head = spirit_tile.crop((int(spirit_tile.width * 0.2), int(spirit_tile.height * 0.15),
                             int(spirit_tile.width * 0.8), int(spirit_tile.height * 0.75)))
    head = head.resize((int(inner * 2), int(inner * 2)), Image.LANCZOS).convert("RGB")
    img.paste(head, (int(cx - inner), int(cy - inner)))
    return img


def check_battle_synthetic(failures):
    """A drawn battle HUD: the opponent is the spirit whose head is on it."""
    screen = fake_screen(seeds=(1, 2, 3))
    tiles = [imaging.normalize(crop) for crop in cards.portraits(screen)]
    hud = synthetic_hud(tiles[1])
    vecs = battle.offer_matrix(tiles)
    if not battle._looks_like_hud(hud):
        failures.append("a drawn battle HUD was not recognised as one")
        return
    answer = battle.fought(hud, vecs)
    if answer is None:
        failures.append("the opponent drawn on a battle HUD was not identified "
                        "(no answer at all)")
        return
    index, best, second = answer
    if index != 1:
        failures.append(f"the opponent was card 2, but card {index + 1} was picked "
                        f"({best:.3f} against {second:.3f})")
    else:
        print(f"synthetic   : a drawn battle HUD named card 2 "
              f"({best:.3f} against {second:.3f} for the next best)  ok")


def check_battle_real(failures):
    """The real screenshots: the opponent is not one of the cards on offer."""
    if not (BATTLE_SHOT.is_file() and CARD_SHOT.is_file()):
        print("real battle : screenshots not available - skipped")
        return
    battle_shot = Image.open(BATTLE_SHOT).convert("RGB")
    card_shot = Image.open(CARD_SHOT).convert("RGB")
    if not battle._looks_like_hud(battle_shot):
        failures.append("the real battle HUD was not recognised as one")
    if battle._looks_like_hud(card_shot):
        failures.append("the real card screen was mistaken for a battle HUD")

    tiles = [imaging.normalize(crop) for crop in cards.portraits(card_shot)]
    if battle.fought(battle_shot, battle.offer_matrix(tiles)) is not None:
        failures.append("a fight against a spirit that was *not* on offer was "
                        "attributed to one of the cards")

    # ... and with that spirit among the offers, it is the one picked
    if not (USER_ROOT / "db_001").is_dir():
        print("real battle : no database at hand to take the opponent's icon from "
              "- the positive half is skipped")
        return
    tmp = Path(tempfile.mkdtemp(prefix="iconmatch_battle_"))
    try:
        shutil.copytree(USER_ROOT / "db_001", tmp / "db_001")
        db = IconDB.open(tmp, 1)
        icon = db.get(USER_OPPONENT)
        if icon is None:
            print(f"real battle : {USER_OPPONENT} is not in the database - skipped")
            return
        offers = [icon.tile, tiles[0], tiles[1]]
        answer = battle.fought(battle_shot, battle.offer_matrix(offers))
        if answer is None:
            failures.append("the opponent was not identified even with its own icon "
                            "among the offers")
        else:
            index, best, second = answer
            if index != 0:
                failures.append(f"the opponent matched offer {index} instead of its "
                                f"own icon ({best:.3f} against {second:.3f})")
            elif best < MIN_REAL_SCORE:
                failures.append(f"the opponent only scored {best:.3f} against its own "
                                f"icon (expected >= {MIN_REAL_SCORE})")
            elif best - second < config.BATTLE_MATCH_MARGIN:
                failures.append(f"the opponent's lead was only {best - second:.3f}")
            else:
                print(f"real battle : the opponent matched its own icon "
                      f"{best:.3f} against {second:.3f} for the next best  ok")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    failures: list[str] = []
    check_reroll(failures)
    check_battle_synthetic(failures)
    check_battle_real(failures)
    for line in failures:
        print("  FAIL:", line)
    print("RESULT:", "PASS" if not failures else "FAIL")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
