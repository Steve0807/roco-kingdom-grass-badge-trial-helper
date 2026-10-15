"""Tunable constants for the icon matcher."""

# --- normalisation -----------------------------------------------------
NORM_SIZE = 128          # normalised icon is NORM_SIZE x NORM_SIZE RGBA
BG_TOL = 30              # per-channel distance from background colour that
                         # still counts as background (bg has light texture)
FRAME_FACTOR = 1.45      # crop side, as a multiple of the icon equivalent
                         # diameter (see imaging.Blob)
MARGIN = 0.10            # extra padding on top of that, as a fraction
CANON_BG = (236, 230, 214)   # every normalised icon gets this background
DESC_BLUR = 1.6          # blur applied to both sides before describing, so a
                         # 60px screenshot and a 220px one compare fairly

# --- descriptor weights (must sum to 1.0) ------------------------------
# (tuned on tests/test_pipeline.py, which is deliberately harsher than real
#  icons: every synthetic icon there shares the same frame, eyes and mouth)
W_GRID = 0.30            # coarse colour layout
W_HIST = 0.35            # colour histogram over the icon pixels only
W_HASH = 0.15            # perceptual (DCT) hash of the greyscale icon
W_SHAPE = 0.20           # silhouette

# --- decision thresholds (overridable per DB in its index.json) --------
# The verdict uses two numbers.  "similarity" is the raw descriptor score of
# the best candidate; "stand-out" is how far that candidate rises above the
# median of the rest of the database.  Similarity alone is not enough: every
# icon of this game shares a black disc on the same background, so the whole
# similarity scale slides upwards as the database grows.  Stand-out is scale
# free and keeps one operating point from 14 icons to 250 (see tests/).
MATCH_SIM = 0.80         # both must hold for a "Y"
MATCH_REL = 0.70
DUP_SIM = 0.78           # both must hold to warn before adding; deliberately
DUP_REL = 0.55           # looser than the match rule - over-warning is cheap,
                         # a duplicate icon in the database is not
MIN_ICONS_FOR_REL = 4    # below this the median is meaningless -> similarity only

# --- live watch --------------------------------------------------------
# The app re-photographs the region the player framed and looks at it only
# once the picture holds still.  "Still" is measured on a coarse grey
# fingerprint, so idle animations on the screen do not count as motion.
WATCH_POLL = 0.6         # seconds between two shots of the watched region
WATCH_FP_SIZE = 16       # the fingerprint is this many grey pixels per side
WATCH_FP_TOL = 5.0       # mean grey difference that still means "same screen"
WATCH_TILE_TOL = 8.0     # ... and between two normalised portraits: the app's
                         # own window is inside the picture it takes, so a click
                         # there repaints the frame without changing the spirits
WATCH_MIN_SIDE = 24      # a framed region thinner than this is a mis-drag
WATCH_MIN_BLOB_SHARE = 0.02   # ...and a lone blob covering less of the frame than
                              # this is background clutter, not an icon (the region
                              # is meant to be framed around the icons)
WATCH_CROP_MAX_SIDE = 1200    # a frame longer than this is a whole screen, not a
                              # hand-made crop: only the pick-a-spirit screen is
                              # worth reading there (see cards.py), because cutting
                              # a scene into "icons" finds faces in the scenery

# --- the pick-a-spirit screen (see cards.py) ---------------------------
# The trial offers three spirits as three cards in a row: a big dark panel each,
# with the spirit's round portrait sitting on the panel's top edge.  Every
# number below is a fraction of the frame or of the panel itself, so the same
# values hold at any UI scale.
SELECT_PANEL_DARK = 110  # max(RGB) below this counts as dark ...
SELECT_PANEL_SPREAD = 12 # ... and this neutral - scenery never is this grey
SELECT_PANEL_MIN_W = 0.05     # of the frame's width ...
SELECT_PANEL_MIN_H = 0.08     # ... and of its height
SELECT_PANEL_ASPECT = (1.1, 2.6)   # panel width / height
SELECT_PANEL_FILL = 0.60     # of its own bounding box (rounded corners included)
SELECT_CARD_TOP_TOL = 0.02   # card tops within this much of the frame's height
SELECT_CARD_SIZE_TOL = 0.15  # ... and widths/heights within this share of each other
SELECT_CARD_GAP = (1.0, 2.5)       # centre gaps, in panel widths - one row,
                                   # not panels that touch, nor two strays.  The
                                   # game's own rows measure ~1.10, and scenery
                                   # touching a card (a dark tree behind the row)
                                   # inflates the measured panel width, so the
                                   # floor stays well below that ratio
SELECT_CARDS_MIN = 2         # a row shorter than this is not the pick-a-spirit screen

SELECT_PORTRAIT_RISE = 0.32     # the disc's centre sits this far * panel height
                                # above the panel's top edge
SELECT_PORTRAIT_RADIUS = 0.18   # the disc's radius, in panel heights
SELECT_PORTRAIT_MARGIN = 1.12   # crop side = 2 * radius * this
SELECT_PORTRAIT_KEEP = 1.02     # pixels further than this * radius from the centre
                                # are flattened onto the canonical background
SELECT_PORTRAIT_BRIGHT = 0.30   # share of bright pixels that says "artwork here"
SELECT_PORTRAIT_SPREAD = 20.0   # ... or this much spread of the max channel

# --- the battle screen (see battle.py) ---------------------------------
# The battle HUD names the opponent at the top right - its portrait, its name
# and its level.  The portrait is the same art as the card's, framed closer, so
# it is matched against the spirits that were just on offer rather than against
# the whole database.  Position as a fraction of the frame, measured on a
# 2560x1440 capture of the trial.
BATTLE_ENEMY_CENTRE = (0.9414, 0.0889)   # of the frame's width and height
BATTLE_ENEMY_HALF = 0.035                # half the crop's side, in frame widths
BATTLE_MATCH_MIN = 0.68                  # the opponent has to look this much
                                         # like one of the spirits on offer ...
BATTLE_MATCH_MARGIN = 0.06               # ... and this far ahead of the others

DESCRIPTOR_VERSION = 1
