"""Watch a corner of the screen and say which icons on it are new.

The clipboard workflow asks the player to crop a screenshot by hand for every
single encounter.  This module is the other way round: the app re-photographs
a region the player framed, notices when that picture settles on something new,
cuts it into single icons and classifies each one against the database - so all
the player has to do is say which of them they are about to fight.

What is worth reading is a *screen*, not a picture full of icons: the game's
"pick a spirit to fight" screen offers three portraits, and :mod:`iconmatch.cards`
finds them.  Anything else - the world, a fight, a menu - holds nothing to
compare, and a frame small enough to be a hand-made crop still gets cut into
icons the old way, for a region the player framed around them tightly.
"""
from __future__ import annotations

import ctypes
import queue
import threading
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageGrab

from . import cards, config, imaging, settings
from .database import Icon, IconDB, SearchResult
from .i18n import t

# What a detection means to the player.
PLAYED = "played"        # already in the database -> you fought this one
NEW = "new"              # nothing like it stored -> a fresh one, worth fighting
UNCLEAR = "unclear"      # something similar is stored, but the thresholds are not sure

REGION_KEY = "watch_region"


class CaptureError(RuntimeError):
    pass


# ------------------------------------------------------------------ region
@dataclass(frozen=True)
class Region:
    """A rectangle of the desktop, in physical screen pixels."""

    x: int
    y: int
    w: int
    h: int

    @property
    def box(self) -> tuple[int, int, int, int]:
        """The (left, top, right, bottom) tuple PIL wants."""
        return (self.x, self.y, self.x + self.w, self.y + self.h)

    @property
    def usable(self) -> bool:
        return self.w >= config.WATCH_MIN_SIDE and self.h >= config.WATCH_MIN_SIDE

    def to_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}

    @classmethod
    def from_dict(cls, data) -> "Region | None":
        try:
            region = cls(int(data["x"]), int(data["y"]), int(data["w"]), int(data["h"]))
        except (TypeError, KeyError, ValueError):
            return None
        return region if region.usable else None

    @property
    def label(self) -> str:
        return t("watch.region_label", w=self.w, h=self.h, x=self.x, y=self.y)


def load_region() -> Region | None:
    """The region framed last time, if it was worth remembering."""
    stored = settings.get(REGION_KEY)
    return Region.from_dict(stored) if isinstance(stored, dict) else None


def save_region(region: Region | None) -> None:
    settings.update(**{REGION_KEY: region.to_dict() if region else None})


# ----------------------------------------------------------------- capture
def grab(region: Region | None = None) -> Image.Image:
    """Photograph `region`, or the whole desktop when region is None."""
    try:
        if region is None:
            return ImageGrab.grab(all_screens=True)
        return ImageGrab.grab(bbox=region.box, all_screens=True)
    except Exception as exc:                      # OS specific - no screen, no session
        raise CaptureError(t("watch.capture_failed", error=exc)) from exc


def virtual_screen() -> tuple[int, int, int, int]:
    """(x, y, w, h) of the whole desktop, for the region picker's overlay."""
    try:
        user32 = ctypes.windll.user32
        return (user32.GetSystemMetrics(76), user32.GetSystemMetrics(77),
                user32.GetSystemMetrics(78), user32.GetSystemMetrics(79))
    except Exception:                             # not Windows
        return (0, 0, 0, 0)


def place_overlay(window, x: int, y: int, w: int, h: int) -> None:
    """Put a Toplevel at an absolute desktop position.

    Tk reads a negative coordinate in a geometry string as an offset from the
    right (or bottom) edge, so on a desktop that starts left of the primary
    monitor - a second screen at x < 0 - the region picker would land somewhere
    else entirely.  Windows' own SetWindowPos has no such idea.
    """
    window.geometry(f"{w}x{h}+{max(x, 0)}+{max(y, 0)}")
    if x >= 0 and y >= 0:
        return
    try:
        ctypes.windll.user32.SetWindowPos(window.winfo_id(), 0, x, y, w, h,
                                          0x0004 | 0x0010)    # NOZORDER | NOACTIVATE
    except Exception:                        # pragma: no cover - non-Windows
        pass


def enable_dpi_awareness() -> float:
    """Let Tk and the screen grab agree on what one pixel is.

    Without this, a 125%-scaled Windows display reports mouse positions in
    scaled units while the screenshot comes back in physical ones, and the
    region the player framed would be captured shifted and shrunk.  Returns
    the DPI so the caller can scale the fonts to match.
    """
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)       # per-monitor v2
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:                        # pragma: no cover - old systems
            return 96.0
    try:
        hdc = ctypes.windll.user32.GetDC(0)
        dpi = float(ctypes.windll.gdi32.GetDeviceCaps(hdc, 88))     # LOGPIXELSY
        ctypes.windll.user32.ReleaseDC(0, hdc)
        return dpi if dpi > 0 else 96.0
    except Exception:
        return 96.0


# ----------------------------------------------------- change detection
def fingerprint(image: Image.Image) -> np.ndarray:
    """A coarse grey thumbnail of the screen, cheap enough to take often."""
    size = config.WATCH_FP_SIZE
    grey = image.convert("L").resize((size, size), Image.BILINEAR)
    return np.asarray(grey, dtype=np.float32)


def looks_same(a: np.ndarray, b: np.ndarray) -> bool:
    """Whether two fingerprints are the same picture, idle animation aside."""
    return float(np.abs(a - b).mean()) <= config.WATCH_FP_TOL


def alike(a: list[np.ndarray], b: list[np.ndarray]) -> bool:
    """Whether two lists of fingerprints match up, one by one."""
    return len(a) == len(b) and all(looks_same(x, y) for x, y in zip(a, b))


# ---------------------------------------------------------- classification
def _framed_crops(frame: Image.Image) -> list[tuple[Image.Image, tuple | None]]:
    """The old reading of a tightly framed crop: one icon, or a grid of them.

    Only small frames get this far - a whole screen is a scene, and splitting a
    scene into "icons" is how a watching app ends up crying wolf on every screen
    it looks at (see config.WATCH_CROP_MAX_SIDE).
    """
    crops = imaging.split_grid(frame)
    if crops:
        return [(crop, None) for crop in crops]
    blob = imaging.largest_blob(frame)
    if blob is None or blob.area < config.WATCH_MIN_BLOB_SHARE * frame.width * frame.height:
        return []
    return [(frame, (0, 0, frame.width, frame.height))]


def _crops_and_kind(frame: Image.Image) -> tuple[list[tuple[Image.Image, tuple | None]], bool]:
    """(crops to compare with where they came from, whether they are an encounter)."""
    sprites = cards.offers(frame)
    if sprites:
        return sprites, True
    if max(frame.size) > config.WATCH_CROP_MAX_SIDE:
        return [], False
    return _framed_crops(frame), False


def crops_of(frame: Image.Image) -> list[Image.Image]:
    """Cut a screenshot into one crop per icon; a screen with no icons is nothing.

    A frame with nothing to read in it at all - an empty patch of game, a
    loading screen, the world as you walk through it - is *nothing* rather than
    one mystery icon, so that waiting for the next encounter does not raise a
    false alarm on every poll.
    """
    return [crop for crop, _box in _crops_and_kind(frame)[0]]


@dataclass
class Detection:
    """One icon spotted on screen, with what the database thinks of it."""

    crop: Image.Image
    found: SearchResult
    state: str
    encounter: bool = False      # ... came off the pick-a-spirit screen
    box: tuple[int, int, int, int] | None = None   # where it sat on that screen
    icon: Icon | None = field(default=None, repr=False)   # set once recorded

    @property
    def tile(self) -> Image.Image:
        return self.found.tile

    @property
    def best(self) -> Icon | None:
        return self.found.best

    @property
    def similarity(self) -> float:
        return self.found.similarity

    @property
    def confidence(self) -> float:
        return self.found.confidence

    @property
    def logged(self) -> bool:
        return self.icon is not None

    def record(self, db: IconDB, name: str = "") -> Icon:
        """Store this one in the database and mark it as fought."""
        self.icon = db.add(self.crop, name, tile=self.found.tile)
        return self.icon

    def unrecord(self, db: IconDB) -> None:
        if self.icon is not None:
            db.remove(self.icon.id)
            self.icon = None


def classify(db: IconDB, found: SearchResult) -> str:
    if db.is_match(found):
        return PLAYED
    if db.is_duplicate(found):
        return UNCLEAR
    return NEW


def state_label(state: str) -> str:
    return t({"new": "match.state_new", "played": "match.state_played",
              "unclear": "match.state_unclear"}.get(state, "match.state_unclear"))


def tiles_alike(a: Image.Image, b: Image.Image) -> bool:
    """Whether two normalised portraits are the same picture of the same spirit.

    Both sides come out of :func:`database.IconDB.search`, so they are already
    framed and scaled the same way; what differs between two frames of one
    screen is only the game's idle animation, and what differs between two
    encounters is the spirit itself.
    """
    diff = np.abs(np.asarray(a, dtype=np.int16) - np.asarray(b, dtype=np.int16))
    return float(diff.mean()) <= config.WATCH_TILE_TOL


def detail_line(det: "Detection") -> str:
    """What the database says about one detection, in one line."""
    best = det.best
    if best is None:
        return t("match.detail_none")
    if det.state == NEW:
        return t("match.detail_closest", id=best.id, sim=det.similarity)
    return t("match.detail_named", id=best.id, name=best.name,
             sim=det.similarity, rel=det.confidence)


def scan(db: IconDB, frame: Image.Image) -> list[Detection]:
    """Every icon in `frame`, in reading order, with its verdict."""
    crops, encounter = _crops_and_kind(frame)
    out = []
    for crop, box in crops:
        found = db.search(crop, top=1)
        out.append(Detection(crop=crop, found=found, state=classify(db, found),
                             encounter=encounter, box=box))
    return out


# -------------------------------------------------------------- the thread
class ScreenWatcher:
    """Re-photographs a region on a timer and hands over each new, settled frame.

    A frame is handed over when it has appeared on two shots in a row - the game
    has stopped moving between them - and it differs from the frame handed over
    last time, so one encounter is never reported twice.  Grabbing runs in a
    thread; the frames come back through a queue that the UI drains on its own
    timer, which keeps the window responsive while a shot is being taken.
    """

    def __init__(self, interval: float = config.WATCH_POLL, grabber=None):
        self.interval = float(interval)
        self._grabber = grabber or grab          # injectable, so tests need no screen
        self.region: Region | None = None
        self.frames: queue.Queue = queue.Queue(maxsize=4)
        self.error: str | None = None
        self.polls = 0
        self.focus: list[tuple[int, int, int, int]] = []   # see focus_on()
        self._held: np.ndarray | None = None      # fingerprint of the previous shot
        self._last: np.ndarray | None = None      # fingerprint handed over last time
        self._focus: list[np.ndarray] = []        # ... and of the focused parts
        self._held_focus: list[np.ndarray] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------ lifecycle
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, region: Region | None, interval: float | None = None) -> None:
        self.stop()
        self.region = region
        if interval is not None:
            self.interval = float(interval)
        self.error = None
        self.polls = 0
        self._held = self._last = None
        self._focus = self._held_focus = []
        self._stop.clear()
        self._drop_frames()
        self._thread = threading.Thread(target=self._run, name="screen-watcher", daemon=True)
        self._thread.start()

    def focus_on(self, frame: Image.Image, boxes) -> None:
        """Watch these parts of the picture closely - the portraits on the cards.

        The whole picture is compared coarsely, because a game screen idles and
        animates and that must not count as a change.  A coarse picture is far
        too blind to notice a card being re-rolled, though: three portraits are a
        fraction of a percent of a whole screen.  These boxes are compared at
        their own resolution instead, so the re-rolled spirits are seen and read
        without the player pressing anything.
        """
        self.focus = [tuple(int(v) for v in box) for box in boxes]
        self._focus = self._focus_fps(frame)

    def stop(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None and thread.is_alive():
            thread.join(timeout=3.0)
        self._drop_frames()

    def _drop_frames(self) -> None:
        while True:
            try:
                self.frames.get_nowait()
            except queue.Empty:
                return

    # -------------------------------------------------------------- polling
    def _focus_fps(self, frame: Image.Image) -> list[np.ndarray]:
        """Fingerprints of the focused parts of a frame, at their own scale."""
        out = []
        for left, top, right, bottom in self.focus:
            if right - left < 8 or bottom - top < 8:      # a box gone to nothing
                continue
            out.append(fingerprint(frame.crop((left, top, right, bottom))))
        return out

    def poll(self) -> Image.Image | None:
        """One shot; returns a frame when it is new and has settled."""
        self.polls += 1
        frame = self._grabber(self.region)
        print_fp = fingerprint(frame)
        focus_fp = self._focus_fps(frame)
        if (self._last is not None and looks_same(print_fp, self._last)
                and alike(focus_fp, self._focus)):
            self._held = None                     # the same screen as last time
            return None
        if (self._held is not None and looks_same(print_fp, self._held)
                and alike(focus_fp, self._held_focus)):
            self._held = None                     # stable and new -> report it
            self._last = print_fp
            self._focus = focus_fp
            return frame
        self._held = print_fp                     # first sighting: wait one more shot
        self._held_focus = focus_fp
        return None

    def take(self) -> Image.Image | None:
        """The next frame to look at, if the thread has handed one over."""
        try:
            return self.frames.get_nowait()
        except queue.Empty:
            return None

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                frame = self.poll()
            except Exception as exc:              # a dead grab must reach the UI
                self.error = str(exc)
                self._stop.set()
                return
            if frame is not None:
                try:
                    self.frames.put_nowait(frame)
                except queue.Full:                # the UI is behind; the newer frame wins
                    pass
            self._stop.wait(self.interval)
