"""The app's announcements: the bell, the storing, and the pictures it shows.

It builds the real window, so it needs a display; where there is none it says so
and passes, like the tests that skip on missing sample art.

The database here is filled with the three spirits of the real card screen, and
the "encounter" that must ring is a drawn card screen holding three spirits that
database has never seen.

    python tests/test_bell.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_battle import synthetic_hud                       # noqa: E402
from test_cards import fake_screen                          # noqa: E402
from iconmatch import cards, imaging, settings                  # noqa: E402
from iconmatch.database import IconDB                       # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SHOT = ROOT / "对局内画面.png"


def bell_counter(app):
    """Count the bells this app rings, without making a sound."""
    rung: list[int] = []
    app.root.bell = lambda: rung.append(1)
    return rung


def check_auto_store(failures, app, db):
    """A card screen, then the battle after it: the fought spirit is stored.

    The database knows the three spirits of the real card screen, so the drawn
    card screen here is three spirits it has never seen; the fight is then a
    drawn battle HUD showing the second of them - the one the player picked.
    """
    screen = fake_screen()
    app.process_frame(screen)
    fresh = sum(1 for det in app.detections if det.state == "new")
    if len(app.detections) != 3 or fresh != 3:
        failures.append(f"the drawn card screen gave {len(app.detections)} rows, "
                        f"{fresh} of them new")
        return
    tiles = [imaging.normalize(crop) for crop in cards.portraits(screen)]

    rows_before = [id(det) for det in app.detections]
    before = len(db.icons)
    app.process_frame(synthetic_hud(tiles[1]))          # the fight against #2
    if len(db.icons) != before + 1:
        failures.append(f"the fight stored {len(db.icons) - before} icons, expected 1")
        return
    stored = db.icons[-1]
    if app.detections[1].icon is None or app.detections[1].icon.id != stored.id:
        failures.append("the stored icon is not the row that was being fought")
    if not app.detections[1].logged:
        failures.append("the row of the fought spirit is not marked as stored")
    if [id(det) for det in app.detections] != rows_before:
        failures.append("the rows of the card screen were thrown away by the fight")

    # with the switch off, the fight is nobody's business but the player's
    app.autolog_var.set(False)
    before = len(db.icons)
    app.process_frame(fake_screen(seeds=(31, 32, 33)))
    app.process_frame(synthetic_hud(tiles[0]))
    if len(db.icons) != before:
        failures.append("a fight was stored with the switch off")
    app.autolog_var.set(True)
    print("auto store  : the fight after the cards stored the spirit being fought, "
          "and nothing with the switch off  ok")


def check_pictures(failures, app, db):
    """A row shows the spirit on screen *and* the closest stored icon.

    That pair is what a "looks similar" answer is judged on: the game prints the
    spirit's element badge over the portrait's lower left, so the score alone is
    not something the player should have to trust.
    """
    from iconmatch.app import ReviewDialog

    app.process_frame(fake_screen(seeds=(41, 42, 43)))       # three unknown spirits
    for det in app.detections:
        pair = app._row_images(det)
        if len(pair) != 2 or pair[1][0] is None:
            failures.append("an unseen spirit's row does not show the closest "
                            "stored icon next to it")
            break
        if pair[1][0] is not det.best.tile:
            failures.append("the picture beside a row is not the closest stored icon")
            break
    else:
        print("pictures    : every row shows the screen's spirit beside the closest "
              "stored icon  ok")

    dialog = ReviewDialog(app.root, app.detections[0])
    if len(dialog._photos) != 2:
        failures.append(f"the enlarged comparison showed {len(dialog._photos)} "
                        f"picture(s), expected 2")
    else:
        print("pictures    : clicking a row opens the pair, enlarged  ok")
    dialog.destroy()

    # an empty database has nothing to put beside the spirit on screen
    empty = IconDB.create(Path(db.dir).parent, 2, "empty")
    app.open_db(empty)
    app.process_frame(fake_screen(seeds=(41, 42, 43)))
    pair = app._row_images(app.detections[0])
    if len(pair) != 2 or pair[1][0] is not None:
        failures.append("a row drew a stored icon although the database is empty")
    app.open_db(db)


def main() -> int:
    if not SHOT.is_file():
        print(f"{SHOT.name} not available - skipped")
        return 0
    try:
        import tkinter as tk
    except Exception:                                        # pragma: no cover - no Tk
        print("Tk is not available here - skipped")
        return 0

    from iconmatch.app import App

    failures: list[str] = []
    tmp = Path(tempfile.mkdtemp(prefix="iconmatch_bell_"))
    original_path = settings.settings_path
    settings.settings_path = lambda: tmp / "settings.json"
    root = None
    try:
        root = tk.Tk()
        root.withdraw()
        app = App(root, tmp)

        # a database that knows the three spirits of the real card screen, so
        # that screen is the quiet case and a drawn one is the encounter
        shot = Image.open(SHOT).convert("RGB")
        db = IconDB.create(tmp, 1, "bell")
        for n, crop in enumerate(cards.portraits(shot)):
            db.add(crop, f"met_{n}")
        app.open_db(db)
        rung = bell_counter(app)

        app.process_frame(shot)                          # all three already fought
        states = [d.state for d in app.detections]
        if len(states) != 3 or any(s != "played" for s in states):
            failures.append(f"the stored screen came back as {states}")
        if rung:
            failures.append("an all-already-fought screen rang the bell")

        first = fake_screen()
        app.process_frame(first)                         # three unknown spirits
        fresh = [d for d in app.detections if d.state == "new"]
        if len(app.detections) != 3 or len(fresh) != 3:
            failures.append(f"the drawn screen gave {len(app.detections)} detections, "
                            f"{len(fresh)} of them new")
        if len(rung) != 1:
            failures.append(f"meeting three unknown spirits rang {len(rung)} bell(s)")

        app.process_frame(first)                         # the same spirits again
        if len(rung) != 1:
            failures.append("the same encounter was rung out twice")

        app.process_frame(fake_screen(seeds=(210, 211, 212)))   # three *other* spirits
        if len(rung) != 2:
            failures.append(f"meeting three other spirits rang {len(rung) - 1} bell(s)")

        app.sound_var.set(False)
        app.process_frame(first)
        if len(rung) != 2:
            failures.append("the bell rang with the sound switched off")
        app.sound_var.set(True)

        # a screen of scenery: nothing compared, nothing rung, and the list of the
        # last pick-a-spirit screen stays up for the player to use
        before = [id(det) for det in app.detections]
        grass = Image.new("RGB", shot.size, (120, 170, 90))
        ImageDraw.Draw(grass).rectangle((300, 300, 2200, 900), fill=(60, 90, 50))
        app.process_frame(grass)
        if [id(det) for det in app.detections] != before:
            failures.append("a screen without cards threw away the list of spirits "
                            "that were on offer")
        if len(rung) != 2:
            failures.append("a screen without cards rang the bell")
        if len(db.icons) != 3:
            failures.append("a screen without cards stored something")
        print("bell        : 0 for an all-fought screen, 1 for the encounter, "
              "0 for the same one again, 1 for the next, 0 with the sound off, "
              "0 for the world (list kept)  ok")

        check_auto_store(failures, app, db)
        check_pictures(failures, app, db)
    except tk.TclError as exc:                           # pragma: no cover - no display
        print(f"no display for the window ({exc}) - skipped")
    finally:
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass
        settings.settings_path = original_path
        shutil.rmtree(tmp, ignore_errors=True)

    for line in failures:
        print("  FAIL:", line)
    print("RESULT:", "PASS" if not failures else "FAIL")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
