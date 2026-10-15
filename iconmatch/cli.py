"""Headless companion to the GUI: work with image files instead of the clipboard.

    python -m iconmatch.cli list
    python -m iconmatch.cli match  --db 1 shot.png
    python -m iconmatch.cli scan   --db 1 screen.png             # what the watcher sees
    python -m iconmatch.cli scan   --db 1 screen.png --fight 2   # ...and store one
    python -m iconmatch.cli add    --db 1 shot.png --name Pikachu
    python -m iconmatch.cli add    --db 1 folder/*.png --force
    python -m iconmatch.cli add    --db 1 grid_screenshot.png   # split automatically
    python -m iconmatch.cli remove --db 1 0003

Messages follow the language set with --lang (Simplified Chinese by default).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from PIL import Image

from . import i18n, imaging, watcher
from .database import DEFAULT_ROOT, IconDB, list_dbs
from .i18n import t


def _indexes(raw: str) -> list[int]:
    """The --fight list ("1,3" or "1 3") as 1-based numbers."""
    out = []
    for part in re.split(r"[,\s]+", raw.strip()):
        if not part:
            continue
        try:
            out.append(int(part))
        except ValueError:
            raise SystemExit(t("cli.fight_bad", value=part))
    return out


def _open_or_create(root: Path, db_id: int, create: bool) -> IconDB:
    db = IconDB(root, db_id)
    if db.exists:
        db.load()
        return db
    if not create:
        raise SystemExit(t("cli.no_db", id=db_id, root=root))
    return IconDB.create(root, db_id)


def main(argv=None) -> int:
    # --lang has to be read before the help texts are built
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--lang", choices=sorted(i18n.LANGUAGES))
    known, _ = pre.parse_known_args(argv)
    if known.lang:
        i18n.set_language(known.lang)
    else:
        i18n.load_language()
    try:                                  # never die on a console that cannot
        sys.stdout.reconfigure(errors="replace")   # encode a Chinese message
    except Exception:                     # pragma: no cover - odd stdout
        pass

    ap = argparse.ArgumentParser(prog="iconmatch.cli", description=t("cli.desc"),
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT, help=t("cli.help.root"))
    ap.add_argument("--lang", choices=sorted(i18n.LANGUAGES), help=t("cli.help.lang"))
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help=t("cli.help.list"))

    p = sub.add_parser("match", help=t("cli.help.match"))
    p.add_argument("--db", type=int, required=True)
    p.add_argument("files", nargs="+", type=Path)
    p.add_argument("--top", type=int, default=3)

    p = sub.add_parser("scan", help=t("cli.help.scan"))
    p.add_argument("--db", type=int, required=True)
    p.add_argument("files", nargs="+", type=Path)
    p.add_argument("--fight", default="", help=t("cli.help.fight"))

    p = sub.add_parser("add", help=t("cli.help.add"))
    p.add_argument("--db", type=int, required=True)
    p.add_argument("files", nargs="+", type=Path)
    p.add_argument("--name", default="", help=t("cli.help.name"))
    p.add_argument("--create", action="store_true", help=t("cli.help.create"))
    p.add_argument("--force", action="store_true", help=t("cli.help.force"))
    p.add_argument("--no-split", action="store_true", help=t("cli.help.no_split"))

    p = sub.add_parser("remove", help=t("cli.help.remove"))
    p.add_argument("--db", type=int, required=True)
    p.add_argument("icon_id")

    args = ap.parse_args(argv)

    if args.cmd == "list":
        rows = list_dbs(args.root)
        if not rows:
            print(t("cli.no_dbs", root=args.root))
        for db_id, count in rows:
            print(t("cli.db_row", id=db_id, count=count))
        return 0

    if args.cmd == "match":
        db = _open_or_create(args.root, args.db, create=False)
        for f in args.files:
            found = db.search(Image.open(f), top=args.top)
            if not found.results:
                print(t("cli.match_empty", file=f))
                continue
            verdict = "Y" if db.is_match(found) else "N"
            extra = "  ".join(f"{i.id}:{s:.3f}" for i, s in found.results[1:])
            print(t("cli.match_row", file=f, verdict=verdict, id=found.best.id,
                    name=found.best.name, sim=found.similarity,
                    rel=found.confidence, extra=extra))
        return 0

    if args.cmd == "scan":
        # exactly what the live watcher does with a frame, minus the screen:
        # useful for dry-running a region against a screenshot you already have
        db = _open_or_create(args.root, args.db, create=False)
        for f in args.files:
            detections = watcher.scan(db, Image.open(f))
            if not detections:
                print(t("cli.scan_empty", file=f))
                continue
            fresh = sum(1 for d in detections if d.state == watcher.NEW)
            print(t("cli.scan_head", file=f, total=len(detections), new=fresh))
            for n, det in enumerate(detections, 1):
                print(t("cli.scan_row", index=n, state=watcher.state_label(det.state),
                        detail=watcher.detail_line(det)))
            for index in _indexes(args.fight):
                if 1 <= index <= len(detections):
                    icon = detections[index - 1].record(db, "")
                    print(t("cli.fought", index=index, id=icon.id, name=icon.name))
        return 0

    if args.cmd == "add":
        db = _open_or_create(args.root, args.db, create=args.create)
        for f in args.files:
            image = Image.open(f)
            crops = [] if args.no_split else imaging.split_grid(image)
            if crops:
                print(t("cli.grid", file=f, count=len(crops)))
                pieces = [(c, f"{f.stem}_{i:02d}") for i, c in enumerate(crops)]
            else:
                pieces = [(image, args.name
                           if (args.name and len(args.files) == 1) else f.stem)]
            for piece, name in pieces:
                found = db.search(piece, top=1)
                if db.is_duplicate(found) and not args.force:
                    print(t("cli.skipped", name=name, id=found.best.id,
                            best=found.best.name, sim=found.similarity,
                            rel=found.confidence))
                    continue
                icon = db.add(piece, name, tile=found.tile)
                print(t("cli.added", name=name, id=icon.id, stored=icon.name))
        return 0

    if args.cmd == "remove":
        db = _open_or_create(args.root, args.db, create=False)
        db.remove(args.icon_id)
        print(t("cli.removed", id=args.icon_id))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
