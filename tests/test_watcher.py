"""The live watcher: change detection, splitting, verdicts, and one-click storing.

Everything here runs off a scripted "camera", so no screen is ever touched:
the frames are pictures this test builds, and the grabber the watcher is given
hands them out one at a time.

    python tests/test_watcher.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_pipeline import BG, make_icon          # noqa: E402  the shared fake icons
from iconmatch import settings, watcher          # noqa: E402
from iconmatch.database import IconDB            # noqa: E402

CELL = 200          # one icon per cell of the fake game screen


def screen(*seeds: int) -> Image.Image:
    """A fake encounter screen: one icon per cell, two per row."""
    cols = 2
    rows = (len(seeds) + cols - 1) // cols
    img = Image.new("RGB", (cols * CELL, rows * CELL), BG)
    for i, seed in enumerate(seeds):
        art = make_icon(seed, size=int(CELL * 0.55))     # canvas is 1.6x its size
        img.paste(art, ((i % cols) * CELL, (i // cols) * CELL))
    return img


class Script:
    """A stand-in for the screen: hands out the next frame on every shot."""

    def __init__(self, frames):
        self.frames = list(frames)
        self.shots = 0

    def __call__(self, region=None):
        frame = self.frames[min(self.shots, len(self.frames) - 1)]
        self.shots += 1
        return frame


def check_region(failures):
    region = watcher.Region(100, 200, 300, 400)
    if region.box != (100, 200, 400, 600):
        failures.append(f"Region.box gave {region.box}")
    if region.to_dict() != {"x": 100, "y": 200, "w": 300, "h": 400}:
        failures.append("Region.to_dict is wrong")
    if watcher.Region.from_dict(region.to_dict()) != region:
        failures.append("Region did not survive a round trip through JSON")
    if watcher.Region.from_dict({"x": 1, "y": 2, "w": 3, "h": 4}) is not None:
        failures.append("a 3x4 region should be rejected as a mis-drag")
    if watcher.Region.from_dict("nonsense") is not None:
        failures.append("a non-dict region should be rejected")
    print("region      : box, round trip, and rejecting mis-drags  ok")


def check_fingerprint(failures):
    a = screen(1, 2, 3, 4)
    b = screen(1, 2, 3, 4)
    c = screen(9, 8, 7, 6)
    fa, fb, fc = (watcher.fingerprint(x) for x in (a, b, c))
    if not watcher.looks_same(fa, fb):
        failures.append("two renders of the same screen should count as the same")
    if watcher.looks_same(fa, fc):
        failures.append("a different screen should count as a change")

    arr = np.asarray(a).astype(np.int16)             # idle animation: a little noise
    noisy = Image.fromarray(np.clip(arr + np.random.default_rng(0).integers(-3, 4, arr.shape),
                                    0, 255).astype(np.uint8), "RGB")
    if not watcher.looks_same(fa, watcher.fingerprint(noisy)):
        failures.append("gentle screen noise should not look like a change")
    print("fingerprint : identical, changed, and noisy-but-still ok")


def check_split(failures):
    four = watcher.crops_of(screen(1, 2, 3, 4))
    if len(four) != 4:
        failures.append(f"a 2x2 screen should give 4 crops, got {len(four)}")
    single = watcher.crops_of(make_icon(5))
    if len(single) != 1:
        failures.append(f"a single icon should stay one crop, got {len(single)}")
    blank = watcher.crops_of(Image.new("RGB", (400, 300), BG))
    if blank:
        failures.append(f"an empty patch of screen should give nothing, got {len(blank)}")
    speck = Image.new("RGB", (400, 300), BG)
    ImageDraw.Draw(speck).rectangle((10, 10, 16, 14), fill=(20, 20, 20))
    if watcher.crops_of(speck):
        failures.append("a speck of UI in a big region should not count as an icon")
    print(f"split       : 2x2 -> {len(four)} crops, single -> {len(single)}, "
          f"blank -> {len(blank)}  ok")


def check_verdicts(db, tmp, failures):
    # an empty database cannot recognise anything: every icon is new
    empty = IconDB.create(tmp, 2, "empty")
    states = {d.state for d in watcher.scan(empty, screen(1, 2))}
    if states != {watcher.NEW}:
        failures.append(f"with an empty DB everything should be NEW, got {states}")

    # icons that are in the database come back as already fought
    known = watcher.scan(db, screen(0, 1, 2, 3))
    if len(known) != 4:
        failures.append(f"expected 4 detections, got {len(known)}")
    for det, seed in zip(known, (0, 1, 2, 3)):
        if det.state != watcher.PLAYED:
            failures.append(f"icon {seed} is stored but was judged {det.state} "
                            f"(sim {det.similarity:.3f} stand-out {det.confidence:.3f})")
    print("verdicts    : empty DB -> all NEW, stored icons -> all PLAYED  ok")


def check_recording(db, failures):
    """The click: a new icon goes into the database and is then known."""
    fresh = watcher.scan(db, screen(10, 11))
    det = fresh[0]
    if det.state == watcher.PLAYED:
        failures.append("icon 10 should not be in the database yet")
    before = len(db.icons)

    icon = det.record(db, "蘑菇怪")
    if det.icon is None or not det.logged:
        failures.append("recording did not mark the detection as logged")
    if len(db.icons) != before + 1:
        failures.append("recording did not add exactly one icon")
    if icon.name != "蘑菇怪":
        failures.append(f"the typed name was lost (got {icon.name!r})")
    if not (db.norm_dir / f"{icon.id}.png").is_file():
        failures.append("the normalised tile was not written to disk")
    if db.get(icon.id) is None or not db.is_match(db.search(det.crop, top=1)):
        failures.append("the stored icon does not match itself afterwards")

    again = watcher.scan(db, screen(10, 11))
    if again[0].state != watcher.PLAYED:
        failures.append(f"after recording, icon 10 is {again[0].state} instead of PLAYED")

    det.unrecord(db)
    if det.logged or db.get(icon.id) is not None:
        failures.append("undo did not remove the icon again")
    if len(db.icons) != before:
        failures.append("undo left the database changed")
    print(f"recording   : stored as {icon.id} {icon.name!r}, seen as PLAYED after, "
          f"undone  ok")


def check_watcher_scheduling(failures):
    """One frame per new, settled picture - never the same encounter twice."""
    a, b = screen(1, 2, 3, 4), screen(5, 6, 7, 8)
    script = Script([a, a, a, a, b, b, b])
    watch = watcher.ScreenWatcher(interval=0.01, grabber=script)
    watch.region = watcher.Region(0, 0, 400, 400)     # the grabber ignores it

    got = [watch.poll() is not None for _ in range(7)]
    if got != [False, True, False, False, False, True, False]:
        failures.append(f"scheduling was {got}, expected "
                        f"[F, T, F, F, F, T, F] (settle, report, ignore repeats)")

    # a screen that comes back to what was already reported stays quiet - the
    # player has already been asked about it; only a third, different screen
    # is worth another look
    c = screen(9, 10, 11, 12)
    script = Script([a, a, b, a, a, c, c])
    watch = watcher.ScreenWatcher(interval=0.01, grabber=script)
    got = [watch.poll() is not None for _ in range(7)]
    if got != [False, True, False, False, False, False, True]:
        failures.append(f"scheduling across three screens was {got}")

    # and the thread hands those frames over through the queue
    script = Script([a])
    watch = watcher.ScreenWatcher(interval=0.01, grabber=script)
    watch.start(watcher.Region(0, 0, 400, 400))
    deadline = time.time() + 5.0
    frame = None
    while frame is None and time.time() < deadline:
        frame = watch.take()
        time.sleep(0.02)
    if frame is None:
        failures.append("the watch thread never handed over a frame")
    watch.stop()
    if watch.running:
        failures.append("stop() left the thread running")

    # a grab that blows up must not take the app down with it
    def broken(region=None):
        raise watcher.CaptureError("no screen here")

    watch = watcher.ScreenWatcher(interval=0.01, grabber=broken)
    watch.start(watcher.Region(0, 0, 400, 400))
    deadline = time.time() + 5.0
    while watch.error is None and time.time() < deadline:
        time.sleep(0.02)
    watch.stop()
    if not watch.error:
        failures.append("a failing grab did not report an error")
    print("scheduling  : settle/report/repeat, thread hand-off, grab failure  ok")


def check_region_setting(failures):
    """The framed region is remembered, without touching the real settings file."""
    original = settings.settings_path
    tmp = Path(tempfile.mkdtemp(prefix="iconmatch_settings_"))
    settings.settings_path = lambda: tmp / "settings.json"
    try:
        region = watcher.Region(10, 20, 300, 200)
        watcher.save_region(region)
        if watcher.load_region() != region:
            failures.append("the saved region did not come back")
        watcher.save_region(None)
        if watcher.load_region() is not None:
            failures.append("clearing the region did not stick")
    finally:
        settings.settings_path = original
        shutil.rmtree(tmp, ignore_errors=True)
    print("settings    : region saved, reloaded, cleared  ok")


def main() -> int:
    failures: list[str] = []
    tmp = Path(tempfile.mkdtemp(prefix="iconmatch_watch_"))
    try:                       # a database holding icons 0..5 of the fake game
        db = IconDB.create(tmp, 1, "watcher")
        for seed in range(6):
            db.add(make_icon(seed), f"icon_{seed:02d}")

        check_region(failures)
        check_split(failures)
        check_fingerprint(failures)
        check_verdicts(db, tmp, failures)
        check_recording(db, failures)
        check_watcher_scheduling(failures)
        check_region_setting(failures)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for line in failures:
        print("  FAIL:", line)
    print("RESULT:", "PASS" if not failures else "FAIL")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
