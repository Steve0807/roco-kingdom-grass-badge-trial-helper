"""Tkinter front end: pick a database, watch the game, grow the database.

Two ways in, one database below both: the live watcher re-photographs a region
of the screen the player framed and lists every icon in it (see
:mod:`iconmatch.watcher`), while the clipboard route still handles a single
hand-cropped icon.

Every visible string comes from :mod:`iconmatch.i18n`; the Language menu
redraws the window in place.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from PIL import Image, ImageTk

from . import battle, clipboard, config, i18n, imaging, settings, watcher
from .database import DEFAULT_ROOT, Icon, IconDB, list_dbs
from .i18n import t
from .watcher import Region, ScreenWatcher

PANEL = 260
CANDIDATES = 10          # rows shown in the Candidates tab after a Ctrl+V check
PAIR_THUMB = 48          # the size of the two pictures a Match row puts side by side
ROW_BG = "#fafafa"       # background of those rows when nothing is wrong with them
BADGE_W = 112            # the status badge's box, wide enough for its longest text
BADGE_H = 34


def ui_font() -> str:
    """Segoe UI has no CJK glyphs of its own; YaHei is the Windows default for them."""
    if sys.platform != "win32":
        return "TkDefaultFont"
    return "Microsoft YaHei UI" if i18n.get_language() == "zh" else "Segoe UI"


def _tile_photo(tile: Image.Image | None, size: int = PANEL) -> ImageTk.PhotoImage | None:
    if tile is None:
        return None
    return ImageTk.PhotoImage(imaging.flatten(tile).resize((size, size), Image.LANCZOS))


# --------------------------------------------------------------- dialogs
class DBChooser(tk.Toplevel):
    """Startup dialog: open an existing database or create one by numeric id."""

    def __init__(self, master, root_dir: Path, current: int | None = None):
        super().__init__(master)
        self.title(t("dbchooser.title"))
        self.root_dir = Path(root_dir)
        self.result: IconDB | None = None
        self.resizable(False, False)
        self.transient(master)

        ttk.Label(self, text=t("dbchooser.heading"), font=(ui_font(), 11, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", padx=12, pady=(12, 4))
        ttk.Label(self, text=str(self.root_dir), foreground="#666").grid(
            row=1, column=0, columnspan=3, sticky="w", padx=12)

        self.listbox = tk.Listbox(self, width=42, height=10, font=(ui_font(), 10),
                                  activestyle="dotbox", exportselection=False)
        self.listbox.grid(row=2, column=0, columnspan=3, padx=12, pady=8)
        self.listbox.bind("<Double-Button-1>", lambda _e: self._open())

        ttk.Label(self, text=t("dbchooser.new_id")).grid(row=3, column=0, sticky="e", padx=(12, 4))
        self.new_id = ttk.Entry(self, width=8)
        self.new_id.grid(row=3, column=1, sticky="w")
        ttk.Button(self, text=t("btn.create"), command=self._create).grid(row=3, column=2, sticky="w", padx=(0, 12))

        bar = ttk.Frame(self)
        bar.grid(row=4, column=0, columnspan=3, sticky="ew", padx=12, pady=12)
        ttk.Button(bar, text=t("btn.open"), command=self._open).pack(side="left")
        ttk.Button(bar, text=t("btn.delete"), command=self._delete).pack(side="left", padx=6)
        ttk.Button(bar, text=t("btn.cancel"), command=self.destroy).pack(side="right")

        self._refresh(select=current)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Return>", lambda _e: self._open())
        self.bind("<Escape>", lambda _e: self.destroy())

    def _refresh(self, select: int | None = None):
        self.dbs = list_dbs(self.root_dir)
        self.listbox.delete(0, tk.END)
        for db_id, count in self.dbs:
            self.listbox.insert(tk.END, t("dbchooser.row", id=db_id, count=count))
        if self.dbs:
            idx = next((i for i, (d, _) in enumerate(self.dbs) if d == select), 0)
            self.listbox.selection_set(idx)
            self.listbox.see(idx)

    def _selected_id(self) -> int | None:
        sel = self.listbox.curselection()
        return self.dbs[sel[0]][0] if sel else None

    def _open(self):
        db_id = self._selected_id()
        if db_id is None:
            messagebox.showinfo(t("dbchooser.pick_title"), t("dbchooser.pick_body"), parent=self)
            return
        try:
            self.result = IconDB.open(self.root_dir, db_id)
        except Exception as exc:
            messagebox.showerror(t("dbchooser.cannot_open"), str(exc), parent=self)
            return
        self.destroy()

    def _create(self):
        raw = self.new_id.get().strip()
        if not raw.isdigit():
            messagebox.showwarning(t("dbchooser.invalid_title"), t("dbchooser.invalid_body"),
                                   parent=self)
            return
        try:
            self.result = IconDB.create(self.root_dir, int(raw))
        except FileExistsError as exc:
            messagebox.showwarning(t("dbchooser.exists_title"), str(exc), parent=self)
            self._refresh(select=int(raw))
            return
        self.destroy()

    def _delete(self):
        db_id = self._selected_id()
        if db_id is None:
            return
        if messagebox.askyesno(
                t("dbchooser.delete_title"),
                t("dbchooser.delete_body", id=db_id),
                parent=self, default="no"):
            IconDB(self.root_dir, db_id).destroy()
            self._refresh()


class SimilarIconDialog(tk.Toplevel):
    """Shown when an icon being added looks like one already in the database."""

    def __init__(self, master, new_tile: Image.Image, icon, score: float):
        super().__init__(master)
        self.title(t("similar.title"))
        self.result = "cancel"
        self.transient(master)
        self.resizable(False, False)

        ttk.Label(self, text=t("similar.headline", score=score,
                               id=icon.id, name=icon.name),
                  font=(ui_font(), 11, "bold")).pack(padx=14, pady=(14, 2))
        ttk.Label(self, text=t("similar.sub"),
                  foreground="#555").pack(padx=14)

        row = ttk.Frame(self)
        row.pack(padx=14, pady=12)
        self._photos = []
        for title, tile in ((t("similar.new"), new_tile),
                            (t("similar.existing", id=icon.id), icon.tile)):
            cell = ttk.Frame(row)
            cell.pack(side="left", padx=8)
            ttk.Label(cell, text=title, font=(ui_font(), 10, "bold")).pack()
            photo = _tile_photo(tile, 220)
            self._photos.append(photo)
            tk.Label(cell, image=photo, bd=1, relief="solid").pack()

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=14, pady=(0, 14))
        ttk.Button(bar, text=t("similar.add"), command=lambda: self._done("add")).pack(side="left")
        ttk.Button(bar, text=t("similar.replace", id=icon.id),
                   command=lambda: self._done("replace")).pack(side="left", padx=6)
        ttk.Button(bar, text=t("btn.cancel"),
                   command=lambda: self._done("cancel")).pack(side="right")
        self.bind("<Escape>", lambda _e: self._done("cancel"))
        self.protocol("WM_DELETE_WINDOW", lambda: self._done("cancel"))

    def _done(self, result: str):
        self.result = result
        self.destroy()


def _modal(dialog: tk.Toplevel):
    dialog.update_idletasks()
    try:
        dialog.grab_set()
    except tk.TclError:                  # already gone (the picker can close on click)
        pass
    dialog.wait_window()


class ReviewDialog(tk.Toplevel):
    """The spirit on screen and the closest stored icon, big, side by side.

    A row that says "looks similar" is a question, and the answer is easier by
    eye than by score - all the more so because the game prints the spirit's
    element badge over the portrait's lower left, which costs a little
    similarity.  Nothing is changed from here; the row's own buttons do that.
    """

    def __init__(self, master, det):
        super().__init__(master)
        self.title(t("review.title"))
        self.transient(master)
        self.resizable(False, False)
        self._photos = []

        best = det.best
        headline = t("review.headline",
                     sim=det.similarity if best is not None else 0.0,
                     rel=det.confidence if best is not None else 0.0)
        ttk.Label(self, text=headline, font=(ui_font(), 11, "bold")).pack(
            padx=14, pady=(14, 2))
        ttk.Label(self, text=t("review.sub"), foreground="#555",
                  justify="left").pack(padx=14)

        pair = [(t("review.screen"), det.tile)]
        if best is not None:
            pair.append((t("review.stored", id=best.id), best.tile))
        row_frame = ttk.Frame(self)
        row_frame.pack(padx=14, pady=12)
        for label, tile in pair:
            cell = ttk.Frame(row_frame)
            cell.pack(side="left", padx=8)
            ttk.Label(cell, text=label, font=(ui_font(), 10, "bold")).pack()
            photo = _tile_photo(tile, 240)
            self._photos.append(photo)
            tk.Label(cell, image=photo, bd=1, relief="solid").pack()

        ttk.Button(self, text=t("btn.close"), command=self.destroy).pack(pady=(0, 14))
        self.bind("<Escape>", lambda _e: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)


class RegionPicker(tk.Toplevel):
    """A translucent overlay over every monitor: drag a box around the icons.

    The rectangle comes out in physical screen pixels, the same coordinates the
    screen grab uses - which is why :func:`watcher.enable_dpi_awareness` has to
    have run before the window is ever opened.
    """

    def __init__(self, master):
        super().__init__(master)
        self.title(t("watch.region_btn"))
        self.result: Region | None = None

        x, y, w, h = watcher.virtual_screen()
        if not w or not h:                       # not Windows: whatever Tk can see
            x = y = 0
            w, h = self.winfo_screenwidth(), self.winfo_screenheight()

        self.overrideredirect(True)
        watcher.place_overlay(self, x, y, w, h)
        self.attributes("-topmost", True)
        try:
            self.attributes("-alpha", 0.35)      # the game stays visible underneath
        except tk.TclError:                      # pragma: no cover - no compositor
            pass

        self.canvas = tk.Canvas(self, bg="#101010", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_text(w // 2, h // 2, text=t("watch.picker_hint"), fill="#ffffff",
                                font=(ui_font(), 18, "bold"), justify="center")
        self._origin: tuple[int, int] | None = None
        self._box: int | None = None

        self.canvas.bind("<Button-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.bind("<Escape>", lambda _e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.focus_force()

    def _press(self, event):
        self._origin = (event.x_root, event.y_root)
        if self._box is not None:
            self.canvas.delete(self._box)
        self._box = self.canvas.create_rectangle(event.x, event.y, event.x, event.y,
                                                 outline="#4ade80", width=3)

    def _drag(self, event):
        if self._origin is None or self._box is None:
            return
        ox, oy = self.winfo_rootx(), self.winfo_rooty()
        self.canvas.coords(self._box, self._origin[0] - ox, self._origin[1] - oy,
                           event.x_root - ox, event.y_root - oy)

    def _release(self, event):
        if self._origin is None:
            return
        x0, y0 = self._origin
        self._origin = None
        region = Region(min(x0, event.x_root), min(y0, event.y_root),
                        abs(event.x_root - x0), abs(event.y_root - y0))
        if region.usable:                        # a small twitch is not a region
            self.result = region
            self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


class ScrollFrame(ttk.Frame):
    """A frame that scrolls vertically, with the mouse wheel wired up."""

    def __init__(self, master, height=460, width=760):
        super().__init__(master)
        self.canvas = tk.Canvas(self, height=height, width=width,
                                highlightthickness=0, bg="#fafafa")
        bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")

        self.inner = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda _e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        for widget in (self.canvas, self.inner):
            widget.bind("<MouseWheel>", self._on_wheel)

    def _on_wheel(self, event):
        self.canvas.yview_scroll(-1 * (event.delta // 120), "units")

    def bind_wheel(self, widget):
        widget.bind("<MouseWheel>", self._on_wheel)


class BatchAddDialog(tk.Toplevel):
    """Resolve a pasted grid icon by icon: add each one, or skip it.

    Every row is a choice between the icon you pasted (left) and whatever the
    database already holds that looks like it (right).  Rows where something
    similar was found start *undecided* - nothing is added or dropped until you
    say which side wins.
    """

    ROW_BG = "#fafafa"
    UNDECIDED_BG = "#fff3d6"
    # A radiobutton whose variable equals its -tristatevalue (the empty string,
    # by default) draws itself in tri-state, which on Windows looks *ticked*.
    # An undecided row therefore has to hold a non-empty sentinel, or both
    # sides of the row appear chosen at once.
    UNDECIDED = "?"

    def __init__(self, master, db, items):
        """items: [(crop, SearchResult), ...] in reading order."""
        super().__init__(master)
        self.title(t("batch.title", count=len(items)))
        self.db = db
        self.items = items
        self.result: list[tuple[int, str]] | None = None   # [(index, name), ...]
        self.single = False                                # "treat as one icon"
        self.transient(master)

        ttk.Label(self, text=t("batch.headline", count=len(items)),
                  font=(ui_font(), 12, "bold")).pack(anchor="w", padx=14, pady=(14, 0))
        ttk.Label(self, text=t("batch.sub"), wraplength=900,
                  foreground="#555").pack(anchor="w", padx=14, pady=(2, 8))

        scroll = ScrollFrame(self, height=470, width=940)
        scroll.pack(fill="both", expand=True, padx=14)

        self.choices: list[tk.StringVar] = []
        self.rows: list[tk.Frame] = []
        self.conflicts: list[int] = []
        self.names: list[ttk.Entry] = []
        self._photos = []

        next_id = int(db._next_id())
        for index, (_crop, found) in enumerate(items):
            conflict = db.is_duplicate(found)
            if conflict:
                self.conflicts.append(index)
            choice = tk.StringVar(value=self.UNDECIDED if conflict else "add")
            choice.trace_add("write", lambda *_a, i=index: self._on_choice(i))
            self.choices.append(choice)

            row = tk.Frame(scroll.inner, bg=self.UNDECIDED_BG if conflict else self.ROW_BG,
                           bd=1, relief="solid", padx=6, pady=5)
            row.grid(row=index, column=0, sticky="ew", pady=2)
            self.rows.append(row)
            scroll.bind_wheel(row)

            # ---- left: the icon you pasted
            tk.Radiobutton(row, variable=choice, value="add", bg=row["bg"],
                           text=t("batch.add_as_new"), compound="right",
                           font=(ui_font(), 9)).grid(row=0, column=0, rowspan=2, padx=(0, 4))
            photo = _tile_photo(found.tile, 76)
            self._photos.append(photo)
            tk.Label(row, image=photo, bd=1, relief="solid",
                     bg=row["bg"]).grid(row=0, column=1, rowspan=2)
            entry = ttk.Entry(row, width=20)
            entry.insert(0, f"{next_id + index:04d}")
            entry.grid(row=0, column=2, rowspan=2, padx=8)
            self.names.append(entry)

            # ---- middle: why this row is a conflict at all
            if conflict:
                verdict = (t("batch.already_in") if db.is_match(found)
                           else t("batch.looks_similar"))
                scores = t("scores", sim=found.similarity, rel=found.confidence)
                tk.Label(row, text=f"{verdict}\n{scores}",
                         bg=row["bg"], fg="#b9770e", justify="center",
                         width=26).grid(row=0, column=3, rowspan=2)
                match_photo = _tile_photo(found.best.tile, 76)
                self._photos.append(match_photo)
                tk.Label(row, image=match_photo, bd=1, relief="solid",
                         bg=row["bg"]).grid(row=0, column=4, rowspan=2, padx=(0, 2))
                right_text = t("batch.skip_keep", id=found.best.id, name=found.best.name)
            else:
                tk.Label(row, text=t("batch.nothing_similar"), bg=row["bg"], fg="#1e8449",
                         width=26).grid(row=0, column=3, rowspan=2)
                tk.Label(row, text="", bg=row["bg"], width=11).grid(row=0, column=4, rowspan=2)
                right_text = t("batch.skip_this")

            # ---- right: keep what is stored
            tk.Radiobutton(row, variable=choice, value="skip", bg=row["bg"],
                           text=right_text, font=(ui_font(), 9)).grid(row=0, column=5,
                                                                 rowspan=2, sticky="w")

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=14, pady=(4, 0))
        self.summary = ttk.Label(bar, text="", font=(ui_font(), 10, "bold"))
        self.summary.pack(side="left")
        ttk.Button(bar, text=t("batch.undecided_skip"),
                   command=lambda: self._resolve_rest("skip")).pack(side="right")
        ttk.Button(bar, text=t("batch.undecided_add"),
                   command=lambda: self._resolve_rest("add")).pack(side="right", padx=6)

        bar2 = ttk.Frame(self)
        bar2.pack(fill="x", padx=14, pady=12)
        self.add_button = ttk.Button(bar2, text=t("batch.import"), command=self._confirm)
        self.add_button.pack(side="left")
        ttk.Button(bar2, text=t("btn.cancel"), command=self.destroy).pack(side="right")
        ttk.Button(bar2, text=t("batch.not_a_grid"),
                   command=self._as_single).pack(side="right", padx=6)
        self.bind("<Escape>", lambda _e: self.destroy())
        self._refresh_summary()

    # ------------------------------------------------------------- choices
    def _on_choice(self, index: int):
        row = self.rows[index]
        decided = self.choices[index].get() != self.UNDECIDED
        colour = self.ROW_BG if decided else self.UNDECIDED_BG
        row.configure(bg=colour)
        for child in row.winfo_children():
            if not isinstance(child, ttk.Entry):
                child.configure(bg=colour)
        self._refresh_summary()

    def _resolve_rest(self, value: str):
        for choice in self.choices:
            if choice.get() == self.UNDECIDED:
                choice.set(value)

    def _counts(self):
        values = [c.get() for c in self.choices]
        return (values.count("add"), values.count("skip"),
                values.count(self.UNDECIDED))

    def _refresh_summary(self):
        add, skip, undecided = self._counts()
        text = t("batch.summary", add=add, skip=skip)
        if undecided:
            text += t("batch.summary_undecided", count=undecided)
        self.summary.config(text=text, foreground="#b9770e" if undecided else "#333")
        self.add_button.config(text=t("batch.import_n", count=add),
                               state="disabled" if undecided else "normal")

    def _as_single(self):
        self.single = True
        self.destroy()

    def _confirm(self):
        self.result = [(i, self.names[i].get().strip())
                       for i, choice in enumerate(self.choices) if choice.get() == "add"]
        self.destroy()


class DBEditor(tk.Toplevel):
    """Browse the database as thumbnails; rename and delete from there."""

    COLUMNS = 5

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.db = app.db
        self.title(t("editor.title", id=self.db.id))
        self.transient(master)
        self.vars: dict[str, tk.BooleanVar] = {}
        self._photos = []

        head = ttk.Frame(self, padding=(14, 12, 14, 6))
        head.pack(fill="x")
        self.heading = ttk.Label(head, text="", font=(ui_font(), 12, "bold"))
        self.heading.pack(side="left")
        ttk.Label(head, text=t("editor.filter")).pack(side="left", padx=(16, 4))
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *_a: self._populate())
        ttk.Entry(head, textvariable=self.filter_var, width=22).pack(side="left")

        self.scroll = ScrollFrame(self, height=520, width=780)
        self.scroll.pack(fill="both", expand=True, padx=14)

        bar = ttk.Frame(self, padding=(14, 10))
        bar.pack(fill="x")
        ttk.Button(bar, text=t("editor.rename_btn"), command=self.rename).pack(side="left")
        ttk.Button(bar, text=t("editor.delete_ticked"), command=self.delete).pack(side="left", padx=6)
        ttk.Button(bar, text=t("editor.tick_all"), command=lambda: self._set_all(True)).pack(side="left")
        ttk.Button(bar, text=t("editor.untick_all"), command=lambda: self._set_all(False)).pack(side="left", padx=6)
        ttk.Button(bar, text=t("btn.close"), command=self.destroy).pack(side="right")

        self._populate()
        self.bind("<Escape>", lambda _e: self.destroy())

    def _populate(self):
        for child in self.scroll.inner.winfo_children():
            child.destroy()
        self._photos.clear()
        needle = self.filter_var.get().strip().lower()
        icons = [i for i in self.db.icons
                 if not needle or needle in i.name.lower() or needle in i.id.lower()]
        self.vars = {i.id: self.vars.get(i.id, tk.BooleanVar(value=False)) for i in icons}
        self.heading.config(text=t("db.summary", id=self.db.id, count=len(self.db.icons))
                                 + (t("editor.shown", count=len(icons)) if needle else ""))

        for n, icon in enumerate(icons):
            cell = ttk.Frame(self.scroll.inner, padding=6)
            cell.grid(row=n // self.COLUMNS, column=n % self.COLUMNS)
            photo = _tile_photo(icon.tile, 108)
            self._photos.append(photo)
            button = tk.Checkbutton(
                cell, image=photo, text=f"{icon.id}  {icon.name}", compound="top",
                variable=self.vars[icon.id], indicatoron=False, bd=1, relief="ridge",
                bg="#ffffff", selectcolor="#cfe3ff", font=(ui_font(), 8), width=118)
            button.pack()
            button.bind("<Double-Button-1>", lambda _e, i=icon: self._rename_icon(i))
            self.scroll.bind_wheel(button)
            self.scroll.bind_wheel(cell)

        if not icons:
            ttk.Label(self.scroll.inner,
                      text=t("editor.empty") if not self.db.icons else t("editor.no_match"),
                      foreground="#777", padding=20).grid(row=0, column=0)

    def _set_all(self, value: bool):
        for var in self.vars.values():
            var.set(value)

    def _ticked(self):
        return [i for i in self.db.icons if i.id in self.vars and self.vars[i.id].get()]

    def _rename_icon(self, icon):
        name = simpledialog.askstring(t("rename.title"), t("rename.prompt", id=icon.id),
                                      initialvalue=icon.name, parent=self)
        if name and name.strip():
            self.db.rename(icon.id, name.strip())
            self._populate()
            self.app.refresh_db_views()
            self.app.set_status(t("status.renamed", id=icon.id, name=name.strip()))

    def rename(self):
        ticked = self._ticked()
        if len(ticked) != 1:
            messagebox.showinfo(t("rename.title"), t("editor.rename_one"), parent=self)
            return
        self._rename_icon(ticked[0])

    def delete(self):
        ticked = self._ticked()
        if not ticked:
            messagebox.showinfo(t("btn.delete"), t("editor.delete_pick"), parent=self)
            return
        names = "\n".join(f"  {i.id}  {i.name}" for i in ticked[:12])
        more = t("common.and_more", count=len(ticked) - 12) if len(ticked) > 12 else ""
        if not messagebox.askyesno(t("editor.delete_title"),
                                   t("editor.delete_body", id=self.db.id, count=len(ticked),
                                     names=names, more=more),
                                   parent=self, default="no"):
            return
        for icon in ticked:
            self.db.remove(icon.id)
            self.vars.pop(icon.id, None)
        self._populate()
        self.app.refresh_db_views()
        self.app.set_status(t("status.deleted_n", id=self.db.id, count=len(ticked)))


# ------------------------------------------------------------------ app
class App:
    def __init__(self, root: tk.Tk, db_root: Path = DEFAULT_ROOT):
        self.root = root
        self.db_root = Path(db_root)
        self.db_root.mkdir(parents=True, exist_ok=True)
        self.db: IconDB | None = None
        self.query_tile: Image.Image | None = None
        self.candidates: list[tuple] = []
        self._photo_in = None
        self._photo_match = None
        self._last_image: Image.Image | None = None

        # live watch: what the screen showed last, and what was stored from it
        self.watcher = ScreenWatcher()
        self.region: Region | None = watcher.load_region()
        self.detections: list[watcher.Detection] = []
        self.session: list[Icon] = []
        self._names: dict[int, str] = {}      # names typed into the Match tab's rows
        self._defaults: dict[int, str] = {}   # the id each row suggests instead
        self._row_entries: dict[int, ttk.Entry] = {}
        self._row_photos: list = []
        self._scanned = False
        self._pump_job = None
        self._encounter: list = []            # portraits announced the time before
        self._offered: list[watcher.Detection] = []   # the spirits last on offer
        self._offered_vecs = None             # ... and their descriptors

        root.title(t("app.title"))
        root.minsize(900, 620)
        self._build()
        self._build_menu()
        self._bind_keys()
        root.protocol("WM_DELETE_WINDOW", self.quit)
        self._apply_topmost(announce=False)
        root.after(80, self.startup)

    def _bind_keys(self):
        root = self.root
        root.bind("<Control-v>", lambda _e: self.do_match())
        root.bind("<Control-m>", lambda _e: self.do_match())
        root.bind("<Control-n>", lambda _e: self.do_add())
        root.bind("<F5>", lambda _e: self.reload())
        root.bind("<F8>", lambda _e: self.capture_now())
        root.bind("<F1>", lambda _e: self.show_help())
        root.bind("<Control-e>", lambda _e: self.edit_db())

    def startup(self):
        """Reopen the database used last time; a session then starts with no clicks."""
        remembered = settings.get("last_db")
        if isinstance(remembered, int):
            try:
                self.open_db(IconDB.open(self.db_root, remembered))
                self.set_status(t("status.reopened", id=self.db.id, count=len(self.db.icons)))
            except Exception:            # deleted or unreadable -> ask as usual
                remembered = None
        if remembered is None:
            self.choose_db()
            if self.db is None:          # the chooser was closed without a database
                return
        if self.region is not None:      # a framed region means "I came here to play"
            self.start_watch()

    def quit(self):
        self.stop_watch(note=False)
        self.root.destroy()

    # ---------------------------------------------------------- language
    def switch_language(self, lang: str):
        """Redraw the window in `lang`, keeping the open database."""
        if lang == i18n.get_language():
            return
        i18n.set_language(lang)
        i18n.save_language(lang)
        db, self.db = self.db, None
        for child in self.root.winfo_children():
            child.destroy()
        self.query_tile = None
        self.candidates = []
        self._photo_in = self._photo_match = None
        self.root.title(t("app.title"))
        self._build()
        self._build_menu()
        self._bind_keys()
        self.db = db
        if db is not None:
            self.sim_var.set(db.threshold("match_sim"))
            self.rel_var.set(db.threshold("match_rel"))
            self.refresh_db_views()
        self._row_photos.clear()
        self.render_detections()
        self._update_region_label()
        self._sync_watch_button()
        self._apply_topmost(announce=False)
        self.set_status(t("status.language_switched"))

    # ------------------------------------------------------------- layout
    def _build(self):
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")

        top = ttk.Frame(self.root, padding=(10, 8))
        top.pack(fill="x")
        self.db_label = ttk.Label(top, text=t("main.no_db"), font=(ui_font(), 12, "bold"))
        self.db_label.pack(side="left")
        ttk.Button(top, text=t("main.switch_db"), command=self.choose_db).pack(side="left", padx=10)
        ttk.Button(top, text=t("main.open_folder"), command=self.open_folder).pack(side="left")

        # packed right to left, so each label ends up to the LEFT of its own box
        self.rel_var = tk.DoubleVar(value=config.MATCH_REL)
        ttk.Spinbox(top, from_=0.0, to=1.0, increment=0.05, width=5, format="%.2f",
                    textvariable=self.rel_var, command=self._save_thresholds).pack(side="right")
        ttk.Label(top, text=t("main.rel_label")).pack(side="right", padx=(16, 6))
        self.sim_var = tk.DoubleVar(value=config.MATCH_SIM)
        ttk.Spinbox(top, from_=0.0, to=1.0, increment=0.01, width=5, format="%.2f",
                    textvariable=self.sim_var, command=self._save_thresholds).pack(side="right")
        ttk.Label(top, text=t("main.sim_label")).pack(side="right", padx=(16, 6))

        watch = ttk.Frame(self.root, padding=(10, 0, 10, 6))
        watch.pack(fill="x")
        ttk.Label(watch, text=t("watch.title"), font=(ui_font(), 10, "bold")).pack(side="left")
        ttk.Button(watch, text=t("watch.region_btn"),
                   command=self.pick_region).pack(side="left", padx=(6, 4))
        self.watch_btn = ttk.Button(watch, text=t("watch.start"), command=self.toggle_watch)
        self.watch_btn.pack(side="left", padx=4)
        ttk.Button(watch, text=t("watch.capture_now"),
                   command=self.capture_now).pack(side="left", padx=4)
        self.topmost_var = tk.BooleanVar(value=bool(settings.get("topmost", True)))
        ttk.Checkbutton(watch, text=t("watch.topmost"), variable=self.topmost_var,
                        command=self._apply_topmost).pack(side="right")
        self.sound_var = tk.BooleanVar(value=bool(settings.get("watch_sound", True)))
        ttk.Checkbutton(watch, text=t("watch.sound"), variable=self.sound_var,
                        command=self._apply_sound).pack(side="right", padx=8)
        self.autolog_var = tk.BooleanVar(value=bool(settings.get("watch_autolog", True)))
        ttk.Checkbutton(watch, text=t("watch.autolog"), variable=self.autolog_var,
                        command=self._apply_autolog).pack(side="right", padx=8)
        self.region_label = ttk.Label(watch, text="", foreground="#666")
        self.region_label.pack(side="left", padx=12)
        self._update_region_label()

        self.verdict = tk.Label(self.root, text=t("idle_hint"),
                                font=(ui_font(), 16, "bold"), bg="#e9e9e9", fg="#333", pady=10)
        self.verdict.pack(fill="x", padx=10)

        # the status bar and the action buttons are packed before the body so
        # that a short window shrinks the panels instead of hiding the buttons
        self.status = tk.StringVar(value=t("status.ready"))
        ttk.Label(self.root, textvariable=self.status, relief="sunken",
                  anchor="w", padding=(6, 3)).pack(fill="x", side="bottom")

        actions = ttk.Frame(self.root, padding=(10, 8, 10, 10))
        actions.pack(fill="x", side="bottom")
        ttk.Button(actions, text=t("main.btn_check"),
                   command=self.do_match).pack(side="left", ipadx=8, ipady=4)
        ttk.Button(actions, text=t("main.btn_add"),
                   command=self.do_add).pack(side="left", padx=8, ipadx=8, ipady=4)
        ttk.Button(actions, text=t("main.btn_edit"),
                   command=self.edit_db).pack(side="left", ipadx=8, ipady=4)
        ttk.Button(actions, text=t("main.btn_help"),
                   command=self.show_help).pack(side="right", ipady=4)

        body = ttk.Frame(self.root, padding=10)
        body.pack(fill="both", expand=True)

        panels = ttk.Frame(body)
        panels.pack(side="left")
        self.in_title = ttk.Label(panels, text=t("main.input_title"), font=(ui_font(), 10, "bold"))
        self.in_title.grid(row=0, column=0, pady=(0, 4))
        self.match_title = ttk.Label(panels, text=t("main.match_title"), font=(ui_font(), 10, "bold"))
        self.match_title.grid(row=0, column=1, pady=(0, 4))
        # a tk.Label with no image sizes width/height in characters and lines,
        # not pixels, which asked for a window taller than the screen and
        # pushed the action row out of sight until the first paste
        self._blank = ImageTk.PhotoImage(Image.new("RGB", (PANEL, PANEL), "#ffffff"))
        self.in_canvas = tk.Label(panels, bd=1, relief="solid", bg="#ffffff",
                                  image=self._blank, width=PANEL, height=PANEL)
        self.in_canvas.grid(row=1, column=0, padx=(0, 10))
        self.match_canvas = tk.Label(panels, bd=1, relief="solid", bg="#ffffff",
                                     image=self._blank, width=PANEL, height=PANEL)
        self.match_canvas.grid(row=1, column=1)
        self.in_sub = ttk.Label(panels, text="-", foreground="#666")
        self.in_sub.grid(row=2, column=0, pady=4)
        self.match_sub = ttk.Label(panels, text="-", foreground="#666")
        self.match_sub.grid(row=2, column=1, pady=4)

        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True, padx=(14, 0))
        self.tabs = ttk.Notebook(right)
        self.tabs.pack(fill="both", expand=True)
        self.match_tab = self._build_match_tab(self.tabs)
        self.cand_tree = self._make_tree(self.tabs, ("rank", "icon", "score"))
        self.all_tree = self._make_tree(self.tabs, ("id", "name", "added"))
        self.tabs.add(self.match_tab, text=t("match.tab"))
        self.tabs.add(self.cand_tree.master, text=t("main.tab_candidates"))
        self.tabs.add(self.all_tree.master, text=t("main.tab_all"))
        self.tabs.select(self.match_tab)
        self.cand_tree.bind("<<TreeviewSelect>>", self._on_candidate_select)
        self.all_tree.bind("<<TreeviewSelect>>", self._on_all_select)

        tools = ttk.Frame(right)
        tools.pack(fill="x", pady=(8, 0))
        ttk.Button(tools, text=t("btn.rename"), command=self.rename_selected).pack(side="left")
        ttk.Button(tools, text=t("btn.delete"), command=self.delete_selected).pack(side="left", padx=6)
        ttk.Button(tools, text=t("main.reload"), command=self.reload).pack(side="left")

    def _build_menu(self):
        menubar = tk.Menu(self.root)

        db_menu = tk.Menu(menubar, tearoff=0)
        db_menu.add_command(label=t("menu.switch_create"), command=self.choose_db)
        db_menu.add_command(label=t("menu.edit_db"),
                            accelerator="Ctrl+E", command=self.edit_db)
        db_menu.add_command(label=t("menu.open_folder"), command=self.open_folder)
        db_menu.add_command(label=t("menu.reload"), accelerator="F5", command=self.reload)
        db_menu.add_separator()
        db_menu.add_command(label=t("menu.quit"), command=self.root.destroy)
        menubar.add_cascade(label=t("menu.database"), menu=db_menu)

        watch_menu = tk.Menu(menubar, tearoff=0)
        watch_menu.add_command(label=t("menu.pick_region"), command=self.pick_region)
        watch_menu.add_command(label=t("menu.capture_now"), accelerator="F8",
                               command=self.capture_now)
        watch_menu.add_command(label=t("menu.toggle_watch"), command=self.toggle_watch)
        watch_menu.add_separator()
        watch_menu.add_checkbutton(label=t("menu.topmost"), variable=self.topmost_var,
                                   command=self._apply_topmost)
        watch_menu.add_checkbutton(label=t("menu.sound"), variable=self.sound_var,
                                   command=self._apply_sound)
        watch_menu.add_checkbutton(label=t("menu.autolog"), variable=self.autolog_var,
                                   command=self._apply_autolog)
        menubar.add_cascade(label=t("menu.watch"), menu=watch_menu)

        icon_menu = tk.Menu(menubar, tearoff=0)
        icon_menu.add_command(label=t("menu.check"),
                              accelerator="Ctrl+V", command=self.do_match)
        icon_menu.add_command(label=t("menu.add"),
                              accelerator="Ctrl+N", command=self.do_add)
        icon_menu.add_separator()
        icon_menu.add_command(label=t("menu.rename_selected"), command=self.rename_selected)
        icon_menu.add_command(label=t("menu.delete_selected"), command=self.delete_selected)
        menubar.add_cascade(label=t("menu.icon"), menu=icon_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label=t("menu.help_item"),
                              accelerator="F1", command=self.show_help)
        menubar.add_cascade(label=t("menu.help"), menu=help_menu)

        # always bilingual, so it stays findable whichever language is on
        lang_menu = tk.Menu(menubar, tearoff=0)
        self.lang_var = tk.StringVar(value=i18n.get_language())
        for code, label in i18n.LANGUAGES.items():
            lang_menu.add_radiobutton(label=label, value=code, variable=self.lang_var,
                                      command=lambda c=code: self.switch_language(c))
        menubar.add_cascade(label=t("menu.language"), menu=lang_menu)

        self.root.config(menu=menubar)

    def edit_db(self):
        if self.db:
            _modal(DBEditor(self.root, self))

    def show_help(self):
        messagebox.showinfo(t("app.title"), t("help.text"), parent=self.root)

    def _build_match_tab(self, parent) -> ttk.Frame:
        """The Match tab: one row per icon the watcher found on screen."""
        frame = ttk.Frame(parent, padding=(8, 8, 8, 4))
        head = ttk.Frame(frame)
        head.pack(fill="x")
        ttk.Button(head, text=t("match.rescan"),
                   command=self.capture_now).pack(side="right")
        # the summary and the hint wrap to whatever width the tab ends up with,
        # so a long translation cannot run underneath the button beside them
        self.match_summary = ttk.Label(frame, text="", font=(ui_font(), 10, "bold"),
                                       justify="left", anchor="w")
        self.match_summary.pack(fill="x")
        self.match_hint = ttk.Label(frame, text=t("match.hint"), foreground="#666",
                                    justify="left", anchor="w")
        self.match_hint.pack(fill="x", pady=(2, 6))
        for label in (self.match_summary, self.match_hint):
            label.bind("<Configure>",
                       lambda e, w=label: w.config(wraplength=max(120, e.width - 8)))
        self.match_scroll = ScrollFrame(frame, height=360, width=560)
        self.match_scroll.pack(fill="both", expand=True)
        return frame

    def _make_tree(self, parent, columns):
        frame = ttk.Frame(parent)
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=12)
        widths = {"rank": 45, "score": 70, "id": 60, "added": 130}
        for c in columns:
            tree.heading(c, text=t("col." + c))
            tree.column(c, width=widths.get(c, 150), anchor="w")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="left", fill="y")
        return tree

    # -------------------------------------------------------------- state
    def open_db(self, db: IconDB):
        """Adopt `db` everywhere: thresholds, views, the Match tab, and settings."""
        self.db = db
        self.sim_var.set(db.threshold("match_sim"))
        self.rel_var.set(db.threshold("match_rel"))
        self._clear_results()
        self.refresh_db_views()
        self.clear_detections()
        settings.update(last_db=db.id)

    def choose_db(self):
        dlg = DBChooser(self.root, self.db_root, current=self.db.id if self.db else None)
        _modal(dlg)
        if dlg.result is not None:
            self.open_db(dlg.result)
            hint = t("hint.use_keys") if self.db.icons else t("hint.empty_db")
            self.set_status(t("status.opened_db", id=self.db.id,
                              count=len(self.db.icons), hint=hint))
        elif self.db is None:
            self.root.destroy()

    def reload(self):
        if self.db:
            self.db.load()
            self.refresh_db_views()
            self.set_status(t("status.reloaded", id=self.db.id))

    def refresh_db_views(self):
        if not self.db:
            return
        self.db_label.config(text=t("db.summary", id=self.db.id, count=len(self.db.icons)))
        self.all_tree.delete(*self.all_tree.get_children())
        for icon in self.db.icons:
            self.all_tree.insert("", "end", iid=icon.id,
                                 values=(icon.id, icon.name, icon.added.replace("T", " ")))

    def _save_thresholds(self):
        if self.db:
            self.db.set_thresholds(match_sim=self.sim_var.get(), match_rel=self.rel_var.get())
            self.set_status(t("status.thresholds", sim=self.sim_var.get(),
                              rel=self.rel_var.get()))

    def set_status(self, text: str):
        self.status.set(text)

    def open_folder(self):
        if not self.db:
            return
        path = str(self.db.dir)
        if sys.platform == "win32":
            os.startfile(path)                      # noqa: S606
        else:
            subprocess.Popen(["xdg-open", path])

    # -------------------------------------------------------------- watch
    def _region_text(self) -> str:
        return self.region.label if self.region else t("watch.region_none")

    def _update_region_label(self):
        self.region_label.config(text=self._region_text())

    def _sync_watch_button(self):
        self.watch_btn.config(text=t("watch.stop") if self.watcher.running
                              else t("watch.start"))

    def _apply_topmost(self, announce: bool = True):
        value = bool(self.topmost_var.get())
        self.root.attributes("-topmost", value)
        settings.update(topmost=value)
        if announce:
            self.set_status(t("status.topmost_on") if value else t("status.topmost_off"))

    def _apply_sound(self, announce: bool = True):
        value = bool(self.sound_var.get())
        settings.update(watch_sound=value)
        if announce:
            self.set_status(t("status.sound_on") if value else t("status.sound_off"))

    def _apply_autolog(self, announce: bool = True):
        value = bool(self.autolog_var.get())
        settings.update(watch_autolog=value)
        if announce:
            self.set_status(t("status.autolog_on") if value else t("status.autolog_off"))

    def pick_region(self):
        """Frame the part of the game to watch; the watcher restarts around it."""
        was_running = self.watcher.running
        if was_running:
            self.stop_watch(note=False)
        try:
            picker = RegionPicker(self.root)
        except Exception as exc:           # pragma: no cover - no display to cover
            messagebox.showwarning(t("watch.region_btn"),
                                   t("watch.picker_failed", error=exc), parent=self.root)
            return
        _modal(picker)
        if picker.result is not None:
            self.region = picker.result
            watcher.save_region(self.region)
            self._update_region_label()
            self.set_status(t("status.region_picked", region=self.region.label))
        else:
            self.set_status(t("status.region_cancelled"))
        if was_running:
            self.start_watch()
        elif picker.result is not None:
            self.capture_now()             # show straight away what that framed

    def toggle_watch(self):
        if self.watcher.running:
            self.stop_watch()
        else:
            self.start_watch()

    def start_watch(self):
        if self.db is None:
            return
        if self.region is None:               # the whole desktop, this window included
            if messagebox.askyesno(t("watch.region_btn"), t("watch.no_region_body"),
                                   parent=self.root):
                self.pick_region()
                if self.region is None:       # the picker was cancelled
                    return
        self.watcher.start(self.region)
        self._sync_watch_button()
        self.set_status(t("status.watching_started", region=self._region_text()))
        if self._pump_job is None:
            self._pump_job = self.root.after(200, self._pump)

    def stop_watch(self, note: bool = True):
        if self._pump_job is not None:
            self.root.after_cancel(self._pump_job)
            self._pump_job = None
        self.watcher.stop()
        self._sync_watch_button()
        if note:
            self.set_status(t("watch.stopped"))

    def _pump(self):
        """Collect what the watch thread produced and keep the loop going.

        A picture that cannot be read is reported and then forgotten: an
        exception out of a Tk callback would end the loop silently, leaving the
        app looking as if it were still watching while it never looks again.
        """
        self._pump_job = None
        frame = None
        while True:
            shot = self.watcher.take()
            if shot is None:
                break
            frame = shot                      # only the newest frame is worth looking at
        if frame is not None:
            try:
                self.process_frame(frame)
            except Exception as exc:           # a strange picture must not kill the loop
                self.set_status(t("watch.scan_failed", error=exc))
        if self.watcher.error:
            error, self.watcher.error = self.watcher.error, None
            self.stop_watch(note=False)
            messagebox.showwarning(t("watch.error_title"),
                                   t("watch.error_stopped", error=error), parent=self.root)
        elif self.watcher.running:
            self._pump_job = self.root.after(200, self._pump)

    def capture_now(self):
        """One shot on demand - for testing a region, or catching one by hand."""
        if self.db is None:
            return
        self.set_status(t("status.scanning"))
        self.root.update_idletasks()
        try:
            frame = watcher.grab(self.region)
        except watcher.CaptureError as exc:
            messagebox.showwarning(t("watch.error_title"), str(exc), parent=self.root)
            self.set_status(str(exc))
            return
        self.process_frame(frame)

    def process_frame(self, frame: Image.Image):
        """Read the picture, compare every spirit on it, and tell the player the news."""
        if self.db is None:
            return
        self.set_status(t("status.scanning"))
        self.root.update_idletasks()
        try:
            found = watcher.scan(self.db, frame)
        except Exception as exc:               # a strange picture must not kill the loop
            self.set_status(t("watch.scan_failed", error=exc))
            return

        if not found:                          # not the pick-a-spirit screen
            self.watcher.focus_on(frame, [])
            if self._store_the_fought(frame):
                return
            # the list of the last pick-a-spirit screen stays up: it is what the
            # player still needs, and the fought one may be stored from it yet
            self.set_status(t("status.scanned_none"))
            self._set_verdict(t("match.no_icons"), "#e9e9e9", "#333")
            self.root.title(t("app.title"))
            return

        self.watcher.focus_on(frame, [d.box for d in found if d.box])
        self._keep_typed_names()               # a name may be half-typed right now
        again = self._same_encounter(found)
        if not again:
            self._encounter = [d.found.tile for d in found]
            self._names = {}
        self._offered = [(n, d) for n, d in enumerate(found) if d.encounter]
        self._offered_vecs = battle.offer_matrix(
            [d.found.tile for _n, d in self._offered])
        self.detections = found
        self._scanned = True
        self.render_detections()
        self.announce(ring=not again)

    def _same_encounter(self, found) -> bool:
        """Whether these are the same spirits that were announced a moment ago.

        This window sits inside the picture the watcher takes, so every repaint
        of it - a click, a keystroke in a row - arrives as a "new" screen.  Only
        a *different* row of spirits is worth a bell, or the same three would be
        rung out again while the player is still deciding which to fight.
        """
        tiles = [d.found.tile for d in found]
        if len(tiles) != len(self._encounter):
            return False
        return all(watcher.tiles_alike(a, b) for a, b in zip(tiles, self._encounter))

    def _store_the_fought(self, frame: Image.Image) -> bool:
        """Read the opponent off the battle HUD and store it, when it is clear.

        The player picks one of the spirits on offer and fights it; the battle
        HUD shows which one it is, so that one is stored without a click - unless
        the picture is not a battle HUD, or the opponent could be either of two
        of the spirits on offer, in which case the choice stays with the player.
        """
        if not self.autolog_var.get() or not self._offered:
            return False
        answer = battle.fought(frame, self._offered_vecs)
        if answer is None:
            return False
        row, best, second = answer
        row_index, det = self._offered[row]
        if det.logged or det.state == watcher.PLAYED:
            self._offered = []                 # nothing to store: already known
            self._offered_vecs = None
            return False
        icon = det.record(self.db, self._names.get(row_index, ""))
        self.session.append(icon)
        self._offered = []
        self._offered_vecs = None
        self.refresh_db_views()
        self.render_detections()
        self._set_verdict(t("match.verdict_auto", id=icon.id), "#2471a3")
        self.set_status(t("status.auto_stored", id=icon.id, name=icon.name,
                          sim=best, other=second))
        return True

    def announce(self, ring: bool = True):
        """The headline: who is new, who was already fought, and a bell for the new."""
        total = len(self.detections)
        fresh = [d for d in self.detections if d.state == watcher.NEW and not d.logged]
        unsure = [d for d in self.detections if d.state == watcher.UNCLEAR and not d.logged]
        played = [d for d in self.detections if d.state == watcher.PLAYED]

        if not total:                      # not an encounter screen, just more game
            self._set_verdict(t("match.no_icons"), "#e9e9e9", "#333")
            self.set_status(t("status.scanned_none"))
            self.root.title(t("app.title"))
            return
        self.set_status(t("status.scanned", total=total, new=len(fresh)))

        if not self.db.icons:
            self._set_verdict(t("match.verdict_empty_db"), "#b9770e")
            self.root.title(t("app.title"))
            return
        if fresh:
            nearest = fresh[0].best
            closest = (t("match.closest_hint", id=nearest.id, sim=fresh[0].similarity)
                       if nearest is not None else "")
            text = (t("match.verdict_one_new", closest=closest) if len(fresh) == 1
                    else t("match.verdict_new", count=len(fresh)))
            self._set_verdict(text, "#c0392b")
            # a bell is for spirits actually met, and only if it was asked for:
            # the player is looking at the game, not at this window
            if ring and self.sound_var.get() and any(d.encounter for d in fresh):
                self.root.bell()
        elif unsure:
            self._set_verdict(t("match.verdict_unclear",
                                ids=", ".join(d.best.id for d in unsure if d.best)),
                              "#b9770e")
        elif played:
            self._set_verdict(t("match.verdict_all_played"), "#1e8449")
        else:
            self._set_verdict(t("idle_hint"), "#e9e9e9", "#333")
        self.root.title(t("app.title_alert", count=len(fresh)) if fresh else t("app.title"))

    # ------------------------------------------------------- match rows
    def clear_detections(self):
        self.detections = []
        self.session = []
        self._names = {}
        self._defaults = {}
        self._encounter = []
        self._offered = []
        self._offered_vecs = None
        self._scanned = False
        self.render_detections()
        self.root.title(t("app.title"))

    def _free_ids(self) -> list[str]:
        """The ids the icons on screen would get if they were stored in this order.

        It repeats what IconDB.add does - the lowest number above the current
        population that is still free - so the number suggested in a row is the
        one that row really gets when its button is clicked.
        """
        used = {i.id for i in self.db.icons}
        out = []
        for _ in self.detections:
            n = len(used) + 1
            while f"{n:04d}" in used:
                n += 1
            out.append(f"{n:04d}")
            used.add(f"{n:04d}")
        return out

    def render_detections(self):
        for child in self.match_scroll.inner.winfo_children():
            child.destroy()
        self._row_photos.clear()
        self._row_entries = {}
        self._defaults = {}
        if self.db is None:
            self.match_summary.config(text="")
            return
        if not self.detections:
            ttk.Label(self.match_scroll.inner,
                      text=t("match.empty") if not self._scanned else t("match.no_icons"),
                      foreground="#777", padding=16).grid(row=0, column=0, sticky="w")
            self.match_summary.config(text="")
            return

        for index, (det, suggested) in enumerate(zip(self.detections, self._free_ids())):
            self._render_row(index, det, suggested)

        fresh = sum(1 for d in self.detections if d.state == watcher.NEW and not d.logged)
        played = sum(1 for d in self.detections if d.state == watcher.PLAYED)
        summary = t("match.summary", total=len(self.detections), new=fresh, played=played)
        if self.session:
            summary += "    " + t("match.session", count=len(self.session),
                                  names=", ".join(i.id for i in self.session[:8]))
        self.match_summary.config(text=summary)

    def _row_images(self, det) -> list[tuple[Image.Image | None, str]]:
        """What a row shows side by side: the spirit on screen, and the closest
        stored icon.

        The pair is the whole point of a "looks similar" row: the database answer
        is a score, and the player's answer is a glance - the more so because the
        game prints the spirit's element badge over the portrait's lower left,
        which costs a little similarity without meaning a different spirit.
        """
        pair: list[tuple[Image.Image | None, str]] = [(det.tile, t("match.thumb_screen"))]
        if det.best is not None:
            pair.append((det.best.tile, t("match.thumb_stored", id=det.best.id)))
        else:
            pair.append((None, t("match.thumb_none")))
        return pair

    def _render_row(self, index: int, det, default_name: str):
        colour = {"new": "#c0392b", "played": "#1e8449"}.get(det.state, "#b9770e")
        badge = t("match.state_recorded", id=det.icon.id) if det.logged else \
            watcher.state_label(det.state)
        if det.logged:
            colour = "#2471a3"

        row = tk.Frame(self.match_scroll.inner, bg=ROW_BG, bd=1, relief="solid",
                       padx=6, pady=4)
        row.grid(row=index, column=0, sticky="ew", pady=2)
        self.match_scroll.bind_wheel(row)

        # the spirit on screen and the closest icon in the database, next to each
        # other: this pair is what a "looks similar" answer has to be judged on
        for column, (tile, caption) in enumerate(self._row_images(det)):
            cell = tk.Frame(row, bg=ROW_BG)
            cell.grid(row=0, column=column, rowspan=2, padx=(0, 6))
            self.match_scroll.bind_wheel(cell)
            if tile is None:
                tk.Label(cell, text="-", bg=ROW_BG, fg="#999", width=PAIR_THUMB // 8,
                         height=3).pack()
            else:
                photo = _tile_photo(tile, PAIR_THUMB)
                self._row_photos.append(photo)
                picture = tk.Label(cell, image=photo, bd=1, relief="solid", bg=ROW_BG)
                picture.pack()
                self.match_scroll.bind_wheel(picture)
                if det.best is not None:
                    picture.bind("<Button-1>", lambda _e, d=det: self.compare(d))
                    picture.bind("<Enter>", lambda _e, w=picture: w.config(
                        relief="ridge", cursor="hand2"))
                    picture.bind("<Leave>", lambda _e, w=picture: w.config(
                        relief="solid", cursor=""))
                    photo_ref = photo
            tk.Label(cell, text=caption, bg=ROW_BG, fg="#777",
                     font=(ui_font(), 8)).pack()
            self.match_scroll.bind_wheel(cell)

        # the badge sits in a fixed box: "没遇到过" and "Already fought" have to
        # line up, and neither may be clipped to fit the other's width
        holder = tk.Frame(row, bg=ROW_BG, width=BADGE_W, height=BADGE_H)
        holder.grid(row=0, column=2, rowspan=2, padx=(0, 8))
        holder.grid_propagate(False)
        label = tk.Label(holder, text=badge, bg=colour, fg="#ffffff", justify="center",
                         font=(ui_font(), 9, "bold"), wraplength=BADGE_W - 14)
        label.pack(fill="both", expand=True)
        self.match_scroll.bind_wheel(label)
        self.match_scroll.bind_wheel(holder)

        # the row is a small stack, so that everything fits a window of normal
        # size: pictures and verdict on the left, the numbers, the name and the
        # button stacked to the right of them
        detail = tk.Label(row, text=self._row_detail(det), bg=ROW_BG, fg="#555",
                          justify="left", anchor="w", wraplength=175, font=(ui_font(), 9))
        detail.grid(row=0, column=2, sticky="w")
        self.match_scroll.bind_wheel(detail)

        if det.logged:
            shown = det.icon.name
        elif det.state == watcher.PLAYED and det.best is not None:
            shown = det.best.name                 # this row *is* that stored icon
        else:
            shown = self._names.get(index, "") or default_name
        entry = ttk.Entry(row, width=9)
        entry.insert(0, shown)
        entry.grid(row=1, column=2, sticky="ew", pady=(3, 0))
        self._row_entries[index] = entry
        self._defaults[index] = shown

        if det.logged:
            entry.state(["disabled"])
            action = ttk.Button(row, text=t("match.btn_undo"),
                                command=lambda i=index: self.undo_detection(i))
        elif det.state == watcher.PLAYED:
            entry.state(["disabled"])             # nothing to store: it is already there
            action = None
        else:
            action = ttk.Button(row, text=t("match.btn_fight"),
                                command=lambda i=index: self.record_detection(i))
        if action is not None:
            # the one button that matters: full width of the column, easy to hit
            action.grid(row=2, column=2, sticky="ew", pady=(4, 0))
        row.columnconfigure(2, weight=1)

    def _row_detail(self, det) -> str:
        """The row's numbers; the id already sits under the stored thumbnail."""
        if det.best is None:
            return t("match.detail_none")
        return t("match.detail_row", sim=det.similarity, rel=det.confidence)

    def compare(self, det):
        """Enlarge the pair of pictures, so the verdict can be checked by eye."""
        _modal(ReviewDialog(self.root, det))

    def _keep_typed_names(self):
        """Remember only the names the player actually typed, not the suggestions."""
        for row_index in range(len(self.detections)):
            typed = self._row_entries.get(row_index)
            typed = typed.get().strip() if typed is not None else ""
            if typed and typed != self._defaults.get(row_index):
                self._names[row_index] = typed
            else:
                self._names.pop(row_index, None)

    def record_detection(self, index: int):
        """The one click: this is the one I am about to fight - store it."""
        if self.db is None or index >= len(self.detections):
            return
        det = self.detections[index]
        if det.logged:
            return
        self._keep_typed_names()
        # an untouched name is only a suggestion of the next id: hand the icon
        # over unnamed and let the database call it by the id it really gets
        icon = det.record(self.db, self._names.get(index, ""))
        self.session.append(icon)
        self.refresh_db_views()
        self.render_detections()
        self.set_status(t("match.saved", id=icon.id, name=icon.name))

    def undo_detection(self, index: int):
        if self.db is None or index >= len(self.detections):
            return
        det = self.detections[index]
        if not det.logged:
            return
        icon_id = det.icon.id
        det.unrecord(self.db)
        self.session = [i for i in self.session if i.id != icon_id]
        self.refresh_db_views()
        self.render_detections()
        self.set_status(t("match.undone", id=icon_id))

    # ------------------------------------------------------------ display
    def _clear_results(self):
        self.query_tile = None
        self.candidates = []
        self._photo_in = self._photo_match = None
        self.in_canvas.config(image=self._blank, width=PANEL, height=PANEL)
        self.match_canvas.config(image=self._blank, width=PANEL, height=PANEL)
        self.in_sub.config(text="-")
        self.match_sub.config(text="-")
        self.cand_tree.delete(*self.cand_tree.get_children())
        self._set_verdict(t("idle_hint"), "#e9e9e9", "#333")

    def _set_verdict(self, text, bg, fg="#ffffff"):
        self.verdict.config(text=text, bg=bg, fg=fg)

    def _show_input(self, tile: Image.Image, note: str):
        self._photo_in = _tile_photo(tile)
        self.in_canvas.config(image=self._photo_in, width=PANEL, height=PANEL)
        self.in_sub.config(text=note)

    def _show_match(self, icon, score: float | None):
        if icon is None:
            self._photo_match = None
            self.match_canvas.config(image=self._blank, width=PANEL, height=PANEL)
            self.match_sub.config(text="-")
            return
        self._photo_match = _tile_photo(icon.tile)
        self.match_canvas.config(image=self._photo_match, width=PANEL, height=PANEL)
        suffix = t("main.score_suffix", score=score) if score is not None else ""
        self.match_sub.config(text=f"{icon.id}  {icon.name}{suffix}")

    def _fill_candidates(self, results):
        self.candidates = results
        self.cand_tree.delete(*self.cand_tree.get_children())
        for rank, (icon, score) in enumerate(results, 1):
            self.cand_tree.insert("", "end", iid=icon.id,
                                  values=(rank, f"{icon.id}  {icon.name}", f"{score:.3f}"))
        if results:
            self.tabs.select(self.cand_tree.master)
            self.cand_tree.selection_set(results[0][0].id)

    def _on_candidate_select(self, _event=None):
        sel = self.cand_tree.selection()
        if not sel:
            return
        for icon, score in self.candidates:
            if icon.id == sel[0]:
                self._show_match(icon, score)
                return

    def _on_all_select(self, _event=None):
        sel = self.all_tree.selection()
        if sel and self.db:
            icon = self.db.get(sel[0])
            if icon:
                self._show_match(icon, None)

    def _selected_icon(self):
        tree = (self.all_tree if self.tabs.index("current") == self.tabs.index(self.all_tree.master)
                else self.cand_tree)
        sel = tree.selection()
        return self.db.get(sel[0]) if (sel and self.db) else None

    # ------------------------------------------------------------ actions
    def _grab(self) -> Image.Image | None:
        try:
            self._last_image = clipboard.grab_image()
            return self._last_image
        except clipboard.ClipboardError as exc:
            messagebox.showwarning(t("clip.no_image_title"), str(exc), parent=self.root)
            return None

    def do_match(self):
        if not self.db:
            return
        image = self._grab()
        if image is None:
            return
        self.set_status(t("status.matching"))
        self.root.update_idletasks()
        found = self.db.search(image, top=CANDIDATES)
        self.query_tile = found.tile
        self._show_input(found.tile, t("main.pasted_size", w=image.size[0], h=image.size[1]))
        self._fill_candidates(found.results)

        if not found.results:
            self._show_match(None, None)
            self._set_verdict(t("verdict.empty_db"), "#c0392b")
            self.set_status(t("status.empty_db"))
            return

        icon = found.best
        self._show_match(icon, found.similarity)
        numbers = t("scores", sim=found.similarity, rel=found.confidence)
        if self.db.is_match(found):
            self._set_verdict(t("verdict.yes", name=icon.name, numbers=numbers), "#1e8449")
        else:
            self._set_verdict(t("verdict.no", numbers=numbers), "#c0392b")
        runner_up = (t("status.runner_up", score=found.results[1][1])
                     if len(found.results) > 1 else "")
        self.set_status(t("status.best", id=icon.id, name=icon.name, sim=found.similarity,
                          runner_up=runner_up, median=found.median))

    def do_add(self):
        if not self.db:
            return
        image = self._grab()
        if image is None:
            return
        self.set_status(t("status.looking"))
        self.root.update_idletasks()
        crops = imaging.split_grid(image)
        if len(crops) >= 2:
            self.do_add_batch(crops)
            return
        self.add_single(image)

    def do_add_batch(self, crops):
        """A pasted grid of icons: review them all, then store the ticked ones."""
        self.set_status(t("status.found_checking", count=len(crops)))
        self.root.update_idletasks()
        items = [(crop, self.db.search(crop, top=1)) for crop in crops]

        dlg = BatchAddDialog(self.root, self.db, items)
        _modal(dlg)
        if dlg.single:                       # user says it was really one icon
            self.add_single(self._last_image)
            return
        if dlg.result is None:
            self.set_status(t("status.import_cancelled"))
            return

        # every row was decided in the dialog, so nothing is second-guessed here:
        # what you ticked as new gets added, the rest you chose to skip
        chosen = {index for index, _ in dlg.result}
        added = [self.db.add(items[index][0], name, tile=items[index][1].tile)
                 for index, name in dlg.result]
        skipped = [items[i][1].best for i in range(len(items)) if i not in chosen]

        self.refresh_db_views()
        if added:
            self._show_input(added[-1].tile, t("main.last_added"))
            self._show_match(added[-1], None)
        self._set_verdict(t("verdict.imported", count=len(added))
                          + (t("verdict.imported_skipped", count=len(skipped))
                             if skipped else ""),
                          "#1e8449" if added else "#b9770e")
        detail = ""
        if skipped:
            lines = "\n".join(
                t("import.kept", id=icon.id, name=icon.name) if icon
                else t("import.skipped_nothing")
                for icon in skipped[:12])
            more = t("common.and_more", count=len(skipped) - 12) if len(skipped) > 12 else ""
            detail = t("import.detail", count=len(skipped), lines=lines, more=more)
        messagebox.showinfo(t("import.title"),
                            t("import.body", id=self.db.id, count=len(added), detail=detail),
                            parent=self.root)
        self.set_status(t("status.db_now_holds", id=self.db.id, count=len(self.db.icons)))

    def add_single(self, image):
        self.set_status(t("status.checking_dups"))
        self.root.update_idletasks()
        found = self.db.search(image, top=5)
        tile = found.tile
        self.query_tile = tile
        self._show_input(tile, t("main.pasted_size", w=image.size[0], h=image.size[1]))
        self._fill_candidates(found.results)

        replace_id = None
        if found.results:
            icon = found.best
            self._show_match(icon, found.similarity)
            if self.db.is_duplicate(found):
                self._set_verdict(t("verdict.similar_found", name=icon.name,
                                    sim=found.similarity, rel=found.confidence), "#b9770e")
                dlg = SimilarIconDialog(self.root, tile, icon, found.similarity)
                _modal(dlg)
                if dlg.result == "cancel":
                    self.set_status(t("status.add_cancelled"))
                    return
                if dlg.result == "replace":
                    replace_id = icon.id

        default = self.db.get(replace_id).name if replace_id else self.db._next_id()
        name = simpledialog.askstring(t("name.title"), t("name.prompt"),
                                      initialvalue=default, parent=self.root)
        if name is None:
            self.set_status(t("status.add_cancelled"))
            return

        if replace_id:
            icon = self.db.replace(replace_id, image, name.strip(), tile=tile)
            verb = t("verb.replaced")
        else:
            icon = self.db.add(image, name.strip(), tile=tile)
            verb = t("verb.added")
        self.refresh_db_views()
        self._show_match(icon, None)
        self._set_verdict(t("verdict.stored", verb=verb, id=icon.id, name=icon.name),
                          "#1e8449")
        self.set_status(t("status.stored", verb=verb, id=icon.id, dbid=self.db.id,
                          count=len(self.db.icons)))

    def rename_selected(self):
        icon = self._selected_icon()
        if not icon:
            return
        name = simpledialog.askstring(t("rename.title"), t("rename.prompt", id=icon.id),
                                      initialvalue=icon.name, parent=self.root)
        if name:
            self.db.rename(icon.id, name.strip())
            self.refresh_db_views()
            self.set_status(t("status.renamed", id=icon.id, name=name.strip()))

    def delete_selected(self):
        icon = self._selected_icon()
        if not icon:
            return
        if messagebox.askyesno(t("editor.delete_title"),
                               t("delete.one_body", id=icon.id, name=icon.name,
                                 dbid=self.db.id), parent=self.root, default="no"):
            self.db.remove(icon.id)
            self.refresh_db_views()
            self._show_match(None, None)
            self.cand_tree.delete(*[i for i in self.cand_tree.get_children() if i == icon.id])
            self.set_status(t("status.deleted_one", id=icon.id))


def main(db_root: Path = DEFAULT_ROOT, lang: str | None = None):
    if lang:
        i18n.set_language(lang)
        i18n.save_language(lang)
    else:
        i18n.load_language()
    # before Tk exists: the watcher captures physical pixels, and the window has
    # to agree with it about where the mouse is on a scaled display
    dpi = watcher.enable_dpi_awareness()
    root = tk.Tk()
    try:
        root.tk.call("tk", "scaling", dpi / 72.0)
    except tk.TclError:                            # pragma: no cover - exotic Tk
        pass
    App(root, db_root)
    root.mainloop()
