"""Bilingual message table: Simplified Chinese (default) and English.

Every user-facing string in the program lives here, as a ``(zh, en)`` pair
under a stable key.  Call sites use :func:`t`::

    t("status.reloaded", id=db.id)

The chosen language is remembered between runs in a small settings file under
the user's config folder (``%APPDATA%/roco-trial-helper/settings.json`` on
Windows), so it survives switching database folders and re-installing.
"""
from __future__ import annotations

from . import settings

DEFAULT_LANG = "zh"
LANGUAGES = {"zh": "简体中文", "en": "English"}

_lang = DEFAULT_LANG


# ------------------------------------------------------------------ state
def load_language() -> str:
    """Adopt the language remembered from the last run (or the default)."""
    lang = settings.get("language")
    set_language(lang if lang in LANGUAGES else DEFAULT_LANG)
    return _lang


def save_language(lang: str) -> None:
    """Remember `lang` for next time."""
    settings.update(language=lang)


def set_language(lang: str) -> None:
    global _lang
    if lang in LANGUAGES:
        _lang = lang


def get_language() -> str:
    return _lang


def t(key: str, **kwargs) -> str:
    """The `key` message in the current language, ``.format``-ed with kwargs."""
    zh, en = STRINGS[key]
    text = zh if _lang == "zh" else en
    return text.format(**kwargs) if kwargs else text


# ---------------------------------------------------------------- strings
# Vocabulary, kept consistent throughout:
#   数据库 = database   图标 = icon        相似度 = similarity
#   突出度 = stand-out  剪贴板 = clipboard
STRINGS: dict[str, tuple[str, str]] = {
    # ---------------------------------------------------------- shell / app
    "app.title": ("洛克王国 草系徽章试炼 助手",
                  "Roco Kingdom Grass Badge Trial Helper"),
    "app.title_alert": ("洛克王国 草系徽章试炼 助手  -  没遇到过 {count} 只",
                        "Roco Kingdom Grass Badge Trial Helper  -  {count} not seen before"),
    "menu.language": ("语言 / Language", "语言 / Language"),
    "status.language_switched": ("界面语言已切换为简体中文。",
                                 "Interface language switched to English."),
    "status.ready": ("就绪。", "Ready."),

    "idle_hint": ("复制一个图标  —  Ctrl+V 查询，Ctrl+N 录入",
                  "Copy an icon  —  Ctrl+V to check it,  Ctrl+N to add it"),

    "help.text": ("""【推荐】自动模式：对局监视

    1. 点「框选区域」把游戏窗口框起来，或者干脆不框、直接监视整个屏幕。
       程序自己会认出「选精灵」画面，也会自己找到每张卡片上的精灵头像。
       （框选的话，要把三张卡整张框进去，别只框头像。）
    2. 点「开始监视」——之后就什么都不用做了。
    3. 一进「选精灵」画面，程序自动找到头像、自动比对，在「对局」这一页列出每一只：
         没遇到过 / 打过了 / 有点像
       每一行都是两张图并排：左边是这一屏看到的，右边是库里最接近的那只，
       点一下图会放大并排给你复核（游戏把系别小圆标压在头像左下角，分数会偏低，
       所以分数低不等于不是同一只，看两眼更准）。
       卡片重抽（刷新）也会自动重新读一遍，不用按 F8。
       别的画面（走路、战斗、菜单）不会比对，也不会响铃，「对局」页上还留着上一次
       选精灵的那几只，随时能点。
    4. 选好打哪只之后：开打的一瞬间，程序从战斗画面右上角的精灵头像认出
       你打的是哪一只，自动替你登记成「打过了」（没把握分不清三只里的哪一只时
       就不登记，交给你自己点）。战斗里那只在「对局」页上会标成「已登记」，
       点错了就点「撤销登记」。
       【实验性】这个自动登记识别得还不稳定，可能认错：打完最好瞄一眼「对局」页，
       错了点「撤销登记」；不想要自动就取消勾选「战斗自动登记（实验性）」，
       每次自己点「要打这只」。

    遇到没见过的精灵会响一声提示音，不想听就取消勾选「提示音」。

    监视状态、区域、提示音、自动登记开关、上次用的数据库都会记住，下次打开直接接着用。

【手动模式】复制一个图标到剪贴板（对着一个图标截图就行，多大都可以），然后：

    Ctrl+V   查询单个图标 - 回答 Y 或 N，并显示数据库中和你的输入
             最接近的10个图标
    Ctrl+N   （批量）录入当前数据库 - 会先查一遍，
             如果数据库里已经有相似的，
             会把两个都显示出来，问你是否座位新图标添加。
             如果粘贴的是一整张网格截图会自动切成单个图标。
    Ctrl+E   编辑数据库：所有图标的缩略图，可重命名、可多选删除
    F5       从磁盘重新载入数据库
    F8       立刻抓一次画面并比对
    F1       本帮助

也可通过按钮操作。

判定会给出两个数字。“相似度”是数据库中最接近的那个图标有多像；
“突出度”是它比数据库里其余图标高出多少。判定为 Y 需要两个都达到阈值，
阈值可以在右上角调 - 每个数据库分别保存。""",
                  """[Recommended] automatic mode: live watch

    1. Press "Frame region" and drag a box around the game window - or
       skip that and watch the whole screen.  Either way the app
       recognises the "pick a spirit" screen by itself and finds the
       portrait on each card by itself.  (If you do frame a region, keep
       the whole cards inside it.)
    2. Press "Start watching" - that is all you have to do.
    3. As soon as the pick-a-spirit screen comes up the app finds the
       portraits, compares them and lists every one on the "Match" tab:
         not seen yet / already fought / looks similar
       Every row shows two pictures side by side: the spirit on screen and
       the closest one in the database.  Click either picture to enlarge
       the pair and check it by eye - the game draws the element badge
       over the portrait's lower left, which costs a little similarity,
       so a low score does not mean a different spirit.
       Re-rolling the cards is picked up as well - no need to press F8.
       No other screen - walking, fighting, menus - is compared, and none
       of them makes a noise; the list of the spirits on offer stays on
       the "Match" tab, ready to be clicked.
    4. When the fight starts, the app reads the opponent off the battle
       HUD (top right) and stores it as already fought.  When it cannot
       tell which of the three it is, it stores nothing and leaves the
       choice to you.  The row of the spirit being fought is marked as
       stored; "Undo" takes it back out.
       Experimental: this automatic storing is not reliable yet and may
       store the wrong one - glance at the "Match" tab after each fight
       and undo a mistake.  Or untick "Store the fight (experimental)"
       and store each spirit yourself with "Fight this one".

    A spirit you have not met before is announced with a bell; untick
    "Sound" if you would rather not hear it.

The watched region, the sound, the auto-storing, the last database and the
watch state are remembered, so next time you just launch and play.

[Manual mode] Copy an icon to the clipboard (any screenshot crop of one
icon, any size), then:

    Ctrl+V   check one icon  -  answers Y or N and shows the 10
             icons in the database closest to your input
    Ctrl+N   add to this database, one icon or many  -  searches
             first, and if something similar is already stored
             it shows both and asks whether to add yours as a
             new icon.
             A pasted grid screenshot is split into single icons
             automatically.
    Ctrl+E   edit the database: thumbnails of every icon, with
             rename and multi-select delete
    F5       reload the database from disk
    F8       grab the screen and compare right now
    F1       this help

All of these are buttons as well.

The verdict shows two numbers.  "similarity" is how close the
closest icon in the database is; "stand-out" is how far it
rises above the rest of the database.  A Y needs both above
their thresholds, which you can adjust at the top right -
they are saved per database."""),

    # ------------------------------------------------------- shared buttons
    "btn.open": ("打开", "Open"),
    "btn.create": ("新建", "Create"),
    "btn.delete": ("删除", "Delete"),
    "btn.cancel": ("取消", "Cancel"),
    "btn.close": ("关闭", "Close"),
    "btn.rename": ("重命名", "Rename"),

    "common.and_more": ("\n  ……还有 {count} 个", "\n  ... and {count} more"),
    "scores": ("相似度 {sim:.3f}   突出度 {rel:.3f}",
               "similarity {sim:.3f}   stand-out {rel:.3f}"),
    "db.summary": ("数据库 {id:03d}   -   {count} 个图标",
                   "DB {id:03d}   -   {count} icon(s)"),

    # ---------------------------------------------------------- DB chooser
    "dbchooser.title": ("选择数据库", "Select icon database"),
    "dbchooser.heading": ("数据库列表", "Databases"),
    "dbchooser.new_id": ("新数据库编号：", "New database id:"),
    "dbchooser.row": ("数据库 {id:03d}    {count} 个图标", "DB {id:03d}    {count} icon(s)"),
    "dbchooser.pick_title": ("选择数据库", "Select a database"),
    "dbchooser.pick_body": ("选中一个数据库，或者新建一个。", "Pick a database, or create one."),
    "dbchooser.cannot_open": ("无法打开", "Cannot open"),
    "dbchooser.invalid_title": ("编号无效", "Invalid id"),
    "dbchooser.invalid_body": ("数据库编号必须是数字。", "The database id must be a number."),
    "dbchooser.exists_title": ("已存在", "Already exists"),
    "dbchooser.delete_title": ("删除数据库", "Delete database"),
    "dbchooser.delete_body": ("确定删除数据库 {id:03d} 以及其中的每一个图标？\n此操作无法撤销。",
                              "Delete DB {id:03d} and every icon in it?\nThis cannot be undone."),

    # ------------------------------------------------------ similar dialog
    "similar.title": ("数据库中已有相似的图标", "Similar icon already in the database"),
    "similar.headline": ("最接近的已有图标得分 {score:.3f}（{id}  {name}）。",
                         "Best existing match scores {score:.3f} ({id}  {name})."),
    "similar.sub": ("数据库里的图标应当各不相同 - 新的这个真的不一样吗？",
                    "Icons are meant to be unique - is the new one really different?"),
    "similar.new": ("新图标（剪贴板）", "New (clipboard)"),
    "similar.existing": ("已有的 {id}", "Existing {id}"),
    "similar.add": ("作为新图标添加", "Add as new icon"),
    "similar.replace": ("替换 {id}", "Replace {id}"),

    # ------------------------------------------------------ review dialog
    "review.title": ("复核这一只", "Compare this spirit"),
    "review.screen": ("本屏的这一只", "on screen"),
    "review.stored": ("库里最接近的 {id}", "closest stored {id}"),
    "review.headline": ("相似度 {sim:.3f}   突出度 {rel:.3f}",
                        "similarity {sim:.3f}   stand-out {rel:.3f}"),
    "review.sub": ("放大看两眼：是同一只就别再打了，不是同一只就点「要打这只」登记。\n"
                   "游戏把系别小圆标压在头像左下角，会拉低相似度，所以分数低不等于不是同一只。",
                   "Look closely: the same spirit means no new reward; a different one is "
                   "worth storing.\nThe game prints the element badge over the portrait's "
                   "lower left, which costs a little similarity - a low score does not "
                   "mean it is a different spirit."),
    "review.none": ("数据库里还没有能拿来对比的图标。",
                    "There is nothing stored yet to compare against."),

    # -------------------------------------------------------- batch import
    "batch.title": ("从粘贴的整张截图导入 {count} 个图标",
                    "Import {count} icons from the pasted grid"),
    "batch.headline": ("在剪贴板图片里找到 {count} 个图标。",
                       "Found {count} icons in the clipboard image."),
    "batch.sub": ("勾选左边的图标表示把它作为新条目添加；勾选右边表示保留数据库里已有的那个，跳过你这个。",
                  "Tick the left icon to add it as a new entry, or the right one "
                  "to keep what is already stored and skip yours."),
    "batch.add_as_new": ("添加为新图标", "add as new"),
    "batch.already_in": ("数据库中已有", "already in the database"),
    "batch.looks_similar": ("与已有图标相似", "looks similar to"),
    "batch.skip_keep": ("跳过 - 保留 {id} {name}", "skip - keep {id} {name}"),
    "batch.nothing_similar": ("数据库中没有相似的", "nothing similar stored"),
    "batch.skip_this": ("跳过这个图标", "skip this icon"),
    "batch.summary": ("{add} 个待添加    {skip} 个待跳过",
                      "{add} to add    {skip} to skip"),
    "batch.summary_undecided": ("    还有 {count} 个未决定", "    {count} still undecided"),
    "batch.undecided_skip": ("未决定 -> 跳过", "Undecided -> skip"),
    "batch.undecided_add": ("未决定 -> 添加为新图标", "Undecided -> add as new"),
    "batch.import": ("导入", "Import"),
    "batch.import_n": ("导入 {count} 个图标", "Import {count} icon(s)"),
    "batch.not_a_grid": ("不是网格 - 按单个图标处理", "Not a grid - treat as one icon"),

    # -------------------------------------------------------------- editor
    "editor.title": ("编辑数据库 {id:03d}", "Edit DB {id:03d}"),
    "editor.filter": ("筛选：", "filter:"),
    "editor.shown": ("，显示 {count} 个", ", {count} shown"),
    "editor.rename_btn": ("重命名…", "Rename..."),
    "editor.delete_ticked": ("删除勾选的", "Delete ticked"),
    "editor.tick_all": ("全选", "Tick all"),
    "editor.untick_all": ("全不选", "Untick all"),
    "editor.empty": ("这个数据库里还没有图标。", "No icons here yet."),
    "editor.no_match": ("没有符合筛选条件的图标。", "Nothing matches the filter."),
    "editor.rename_one": ("恰好勾选一个图标来重命名（也可以直接双击它）。",
                          "Tick exactly one icon to rename (or double-click it)."),
    "editor.delete_pick": ("先勾选要删除的图标。", "Tick the icons you want to delete."),
    "editor.delete_title": ("删除图标", "Delete icons"),
    "editor.delete_body": ("确定从数据库 {id:03d} 删除 {count} 个图标？\n\n{names}{more}\n\n此操作无法撤销。",
                           "Delete {count} icon(s) from DB {id:03d}?\n\n{names}{more}\n\n"
                           "This cannot be undone."),

    # ------------------------------------------------------------ live watch
    "watch.title": ("对局监视：", "Live watch:"),
    "watch.region_none": ("整个屏幕（建议先框选区域）", "whole screen (framing a region is better)"),
    "watch.region_label": ("{w}×{h} @ ({x},{y})", "{w}x{h} at ({x},{y})"),
    "watch.region_btn": ("框选区域…", "Frame region..."),
    "watch.start": ("开始监视", "Start watching"),
    "watch.stop": ("停止监视", "Stop watching"),
    "watch.capture_now": ("立即抓图 (F8)", "Capture now (F8)"),
    "watch.topmost": ("窗口置顶", "Keep on top"),
    "watch.sound": ("提示音", "Sound"),
    "watch.autolog": ("战斗自动登记（实验性）", "Store the fight (experimental)"),
    "watch.picker_hint": ("按住鼠标左键拖动，把游戏窗口框起来（三张卡要整张框进去）\n\nEsc 取消",
                          "Drag with the left mouse button to frame the game window "
                          "(keep the whole cards inside)\n\nEsc cancels"),
    "watch.picker_failed": ("框选失败：{error}", "could not open the picker: {error}"),
    "watch.error_title": ("抓图出错", "Screen capture failed"),
    "watch.scan_failed": ("这一屏没比对成功：{error}", "Could not compare that screen: {error}"),
    "watch.no_region_body": ("还没有框选监视区域。现在直接开始的话会监视整个屏幕，\n"
                             "连这个窗口也会被抓进去，容易误报。\n\n"
                             "现在去框选区域吗？（选“否”就直接监视整个屏幕）",
                             "No region has been framed yet. Watching now would photograph "
                             "the whole desktop, this window included, which gets noisy.\n\n"
                             "Frame a region now? (\"No\" watches the whole screen anyway)"),
    "watch.capture_failed": ("抓不到屏幕画面：{error}",
                             "could not grab the screen: {error}"),
    "watch.watching": ("监视中 - 每 {sec:.1f} 秒抓一次画面，出现选精灵界面就会自动比对。",
                       "Watching - a shot every {sec:.1f}s; the pick-a-spirit screen is "
                       "compared as soon as it appears."),
    "watch.waiting": ("监视中… 等待选精灵界面。", "Watching... waiting for the pick-a-spirit screen."),
    "watch.stopped": ("已停止监视。", "Stopped watching."),
    "watch.error_stopped": ("抓图出错，监视已停止：{error}",
                            "Capture failed, watching stopped: {error}"),

    "match.tab": ("对局", "Match"),
    "match.hint": ("进入选精灵界面时这里会自动列出每一只。点「要打这只」就把它记进数据库。",
                   "Every spirit on the pick-a-spirit screen shows up here. Clicking "
                   "\"Fight this one\" stores it in the database."),
    "match.empty": ("还没抓到画面。点「开始监视」，或者用「立即抓图」先试一次。",
                    "Nothing captured yet. Press \"Start watching\", or try "
                    "\"Capture now\" once."),
    "match.no_icons": ("这一屏不是选精灵界面 - 继续玩，出现时会自动列出。",
                       "Not the pick-a-spirit screen - keep playing, it will be listed "
                       "when it appears."),
    "match.rescan": ("重新抓图并比对 (F8)", "Capture and compare again (F8)"),
    "match.state_new": ("没遇到过", "Not seen yet"),
    "match.state_played": ("打过了", "Already fought"),
    "match.state_unclear": ("有点像", "Looks similar"),
    "match.state_recorded": ("已登记 {id}", "Stored {id}"),
    "match.btn_fight": ("要打这只", "Fight this one"),
    "match.btn_undo": ("撤销登记", "Undo"),
    "match.name_label": ("名字", "name"),
    "match.detail_none": ("数据库里没有相似的", "nothing similar in the database"),
    "match.detail_closest": ("最接近 {id}   相似度 {sim:.3f}",
                             "closest {id}   similarity {sim:.3f}"),
    "match.detail_named": ("最接近 {id} {name}   相似度 {sim:.3f}   突出度 {rel:.3f}",
                           "closest {id} {name}   similarity {sim:.3f}   "
                           "stand-out {rel:.3f}"),
    "match.detail_row": ("相似度 {sim:.3f}   突出度 {rel:.3f}",
                         "similarity {sim:.3f}   stand-out {rel:.3f}"),
    "match.thumb_screen": ("本屏", "screen"),
    "match.thumb_stored": ("库中 {id}", "stored {id}"),
    "match.thumb_none": ("库里没有", "none stored"),
    "match.compare_hint": ("点这两张图放大对比", "click either picture to compare them"),
    "match.summary": ("这一屏 {total} 只：{new} 只没遇到过，{played} 只打过",
                      "{total} icon(s) on screen: {new} not seen yet, {played} fought"),
    "match.session": ("本次已登记 {count} 只：{names}", "{count} stored this session: {names}"),
    "match.verdict_new": ("没遇到过 {count} 只 —— 在下面点「要打这只」登记",
                          "{count} not seen before  -  click \"Fight this one\" below"),
    "match.verdict_one_new": ("没遇到过这一只{closest} —— 点「要打这只」登记",
                              "Not seen before{closest}  -  click \"Fight this one\""),
    "match.closest_hint": ("（最像已登记的 {id}，相似度 {sim:.3f}）",
                           " (closest stored icon {id}, similarity {sim:.3f})"),
    "match.verdict_unclear": ("有点像是在一起过的：{ids} —— 自己看一眼再决定",
                              "Close to stored icons {ids} - take a look before deciding"),
    "match.verdict_all_played": ("这一屏的精灵都打过了。", "Everything on this screen has been fought."),
    "match.verdict_empty_db": ("数据库还是空的 - 每打一只登记一只，慢慢就攒起来了。",
                               "The database is still empty - store one per fight and it "
                               "fills up."),
    "match.verdict_auto": ("【实验性】已自动登记战斗中的 {id} - 战斗画面右上角那只就是你打的。"
                           "识别不稳，登记错了就点「撤销登记」。",
                           "Experimental: stored {id} - the one you are fighting, read off "
                           "the battle HUD.  It is not reliable yet; \"Undo\" takes a "
                           "mistake back out."),
    "match.saved": ("已登记 {id} {name} - 以后再遇到会显示「打过了」。",
                    "Stored {id} {name} - next time it will show as already fought."),
    "match.undone": ("已撤销 {id}。", "Removed {id} again."),

    # --------------------------------------------------------- main window
    "main.no_db": ("未选择数据库", "No database"),
    "main.switch_db": ("切换数据库…", "Switch DB..."),
    "main.open_folder": ("打开文件夹", "Open folder"),
    "main.rel_label": ("突出度 ≥", "stand-out >="),
    "main.sim_label": ("相似度 ≥", "similarity >="),
    "main.btn_check": ("查询剪贴板图标  (Ctrl+V)", "Check clipboard icon  (Ctrl+V)"),
    "main.btn_add": ("把剪贴板图标录入数据库  (Ctrl+N)", "Add clipboard icon to DB  (Ctrl+N)"),
    "main.btn_edit": ("编辑数据库  (Ctrl+E)", "Edit database  (Ctrl+E)"),
    "main.btn_help": ("快捷键  (F1)", "Shortcuts  (F1)"),
    "main.input_title": ("输入（剪贴板）", "Input (clipboard)"),
    "main.match_title": ("最接近的图标", "Best match"),
    "main.tab_candidates": ("候选", "Candidates"),
    "main.tab_all": ("全部图标", "All icons"),
    "main.reload": ("重新载入 (F5)", "Reload (F5)"),
    "main.pasted_size": ("粘贴的图片 {w}x{h} 像素", "pasted {w}x{h}px"),
    "main.score_suffix": ("   得分 {score:.3f}", "   score {score:.3f}"),
    "main.last_added": ("最后录入的图标", "last icon added"),

    "col.rank": ("名次", "Rank"),
    "col.icon": ("图标", "Icon"),
    "col.score": ("得分", "Score"),
    "col.id": ("编号", "Id"),
    "col.name": ("名称", "Name"),
    "col.added": ("录入时间", "Added"),

    # --------------------------------------------------------------- menus
    "menu.database": ("数据库", "Database"),
    "menu.switch_create": ("切换 / 新建数据库…", "Switch / create database..."),
    "menu.edit_db": ("编辑数据库（重命名 / 删除图标）…",
                     "Edit database (rename / delete icons)..."),
    "menu.open_folder": ("打开数据库文件夹", "Open database folder"),
    "menu.reload": ("从磁盘重新载入", "Reload from disk"),
    "menu.quit": ("退出", "Quit"),
    "menu.icon": ("图标", "Icon"),
    "menu.check": ("用数据库查询剪贴板里的图标", "Check clipboard icon against the database"),
    "menu.add": ("把剪贴板里的图标录入数据库", "Add clipboard icon to the database"),
    "menu.rename_selected": ("重命名选中的", "Rename selected"),
    "menu.delete_selected": ("删除选中的", "Delete selected"),
    "menu.watch": ("对局监视", "Live watch"),
    "menu.pick_region": ("框选监视区域…", "Frame the watched region..."),
    "menu.capture_now": ("立即抓图并比对", "Capture and compare now"),
    "menu.toggle_watch": ("开始 / 停止监视", "Start / stop watching"),
    "menu.topmost": ("窗口置顶", "Keep window on top"),
    "menu.sound": ("遇到精灵时提示音", "Sound on an encounter"),
    "menu.autolog": ("战斗开始时自动登记打的那只（实验性）",
                     "Store the opponent when a battle starts (experimental)"),
    "menu.help": ("帮助", "Help"),
    "menu.help_item": ("快捷键与工作原理", "Shortcuts and how it works"),

    # ------------------------------------------------------- rename / name
    "delete.one_body": ("确定从数据库 {dbid:03d} 移除 {id}（{name}）？",
                        "Remove {id} ({name}) from DB {dbid:03d}?"),

    "rename.title": ("重命名", "Rename"),
    "rename.prompt": ("{id} 的新名称：", "New name for {id}:"),
    "name.title": ("图标名称", "Icon name"),
    "name.prompt": ("给这个图标起个名字：", "Name for this icon:"),

    # ------------------------------------------------------------ verdicts
    "verdict.empty_db": ("N  -  数据库是空的。按 Ctrl+N 把这个图标录入。",
                         "N  -  the database is empty.  Press Ctrl+N to add this icon."),
    "verdict.yes": ("Y  -  数据库中已有：{name}      {numbers}",
                    "Y  -  already in the DB:  {name}      {numbers}"),
    "verdict.no": ("N  -  数据库中没有。按Ctrl+N 录入。      {numbers}",
                   "N  -  not in the DB.  Ctrl+N adds it.      {numbers}"),
    "verdict.similar_found": ("发现相似的图标：{name}   相似度 {sim:.3f}   突出度 {rel:.3f}",
                              "Similar icon found:  {name}   similarity {sim:.3f}   "
                              "stand-out {rel:.3f}"),
    "verdict.imported": ("已从整张截图导入 {count} 个图标",
                         "Imported {count} icon(s) from the grid"),
    "verdict.imported_skipped": ("，并按你的选择跳过 {count} 个",
                                 ", skipped {count} by your choice"),
    "verdict.stored": ("{verb}  {id}  {name}", "{verb}  {id}  {name}"),
    "verb.added": ("已录入", "Added"),
    "verb.replaced": ("已替换", "Replaced"),

    # ------------------------------------------------------------ statuses
    "status.opened_db": ("已打开数据库 {id:03d}（{count} 个图标）。   {hint}",
                         "Opened DB {id:03d} ({count} icons).   {hint}"),
    "hint.use_keys": ("Ctrl+N 录入剪贴板图标，Ctrl+V 查询。",
                      "Ctrl+N adds the clipboard icon, Ctrl+V checks one."),
    "hint.empty_db": ("这个数据库是空的 - 复制一个图标，按 Ctrl+N 录入。",
                      "This database is empty - copy an icon and press Ctrl+N to add it."),
    "status.reloaded": ("已重新载入数据库 {id:03d}。", "Reloaded DB {id:03d}."),
    "status.thresholds": ("现在判定为 Y 需要相似度 ≥ {sim:.2f} 且突出度 ≥ {rel:.2f}。",
                          "Verdict now needs similarity >= {sim:.2f} and "
                          "stand-out >= {rel:.2f}."),
    "status.matching": ("查询中…", "Matching..."),
    "status.empty_db": ("还没有可以比对的图标 - 先用 Ctrl+N 录入几个。",
                        "Nothing to compare against yet - add icons with Ctrl+N first."),
    "status.best": ("最接近 {id} {name} {sim:.3f}{runner_up}   （数据库中位数 {median:.3f}）",
                    "Best {id} {name} {sim:.3f}{runner_up}   (DB median {median:.3f})"),
    "status.runner_up": ("   次接近 {score:.3f}", "   next best {score:.3f}"),
    "status.looking": ("正在寻找图标…", "Looking for icons..."),
    "status.found_checking": ("找到 {count} 个图标 - 正在逐个与数据库比对…",
                              "Found {count} icons - checking each against the database..."),
    "status.import_cancelled": ("已取消导入。", "Import cancelled."),
    "status.db_now_holds": ("数据库 {id:03d} 现在有 {count} 个图标。",
                            "DB {id:03d} now holds {count} icons."),
    "status.checking_dups": ("正在检查是否重复…", "Checking for duplicates..."),
    "status.add_cancelled": ("已取消录入。", "Add cancelled."),
    "status.stored": ("{verb} {id}，数据库 {dbid:03d} 现有 {count} 个图标。",
                      "{verb} {id} in DB {dbid:03d} ({count} icons)."),
    "status.renamed": ("已把 {id} 重命名为 {name}。", "Renamed {id} to {name}."),
    "status.deleted_one": ("已删除 {id}。", "Deleted {id}."),
    "status.deleted_n": ("已从数据库 {id:03d} 删除 {count} 个图标。",
                         "Deleted {count} icon(s) from DB {id:03d}."),
    "status.reopened": ("已自动打开上次用的数据库 {id:03d}（{count} 个图标）。",
                        "Reopened last used DB {id:03d} ({count} icons)."),
    "status.region_picked": ("监视区域已更新：{region}。", "Watched region: {region}."),
    "status.region_cancelled": ("已取消框选，监视区域不变。",
                               "Framing cancelled, the region is unchanged."),
    "status.watching_started": ("开始监视：{region}。去游戏里打吧，一进选精灵界面我就会提示。",
                                "Watching {region}. Go play - the pick-a-spirit screen is "
                                "called out as soon as it appears."),
    "status.scanning": ("正在比对画面…", "Comparing the screen..."),
    "status.scanned": ("画面里有 {total} 只，其中 {new} 只没遇到过。",
                       "{total} icon(s) on screen, {new} of them not seen before."),
    "status.scanned_none": ("这一屏不是选精灵界面 - 继续玩，出现时会自动列出。",
                            "Not the pick-a-spirit screen - keep playing, it will be "
                            "listed when it appears."),
    "status.topmost_on": ("窗口已经置顶，会一直显示在游戏上面。",
                          "The window stays on top of the game."),
    "status.topmost_off": ("窗口不再置顶。", "The window no longer stays on top."),
    "status.sound_on": ("遇到没见过的精灵时会响一声提示音。",
                        "A bell rings when a spirit you have not met turns up."),
    "status.sound_off": ("提示音已关闭，只会在画面上提示。",
                         "The bell is off - announcements stay on screen."),
    "status.autolog_on": ("【实验性】开打时自动把这一场打的那只登记成「打过了」（有把握时才登记）。"
                          "识别还不稳定，可能认错——打完最好瞄一眼「对局」页，"
                          "错了点「撤销登记」。",
                          "Experimental: the spirit you fight is stored as fought when the "
                          "battle starts, whenever it is clear which one it is.  This is "
                          "not reliable yet and may store the wrong one - check the "
                          "\"Match\" tab after each fight and undo a mistake."),
    "status.autolog_off": ("战斗自动登记已关闭，自己点「要打这只」登记。",
                           "Auto-storing is off - store the spirit with \"Fight this one\"."),
    "status.auto_stored": ("【实验性】战斗里的 {id} {name} 已自动登记为「打过了」"
                           "（相似度 {sim:.3f}，与第二像的 {other:.3f}）。"
                           "登记错了就点「撤销登记」。",
                           "Experimental: stored {id} {name} as fought - that is the one "
                           "in the battle HUD.  (score {sim:.3f} against {other:.3f} for "
                           "the next best)  \"Undo\" takes it back out."),

    # -------------------------------------------------------------- import
    "import.title": ("导入", "Import"),
    "import.body": ("已向数据库 {id:03d} 录入 {count} 个图标。{detail}",
                    "Added {count} icon(s) to DB {id:03d}.{detail}"),
    "import.detail": ("\n\n按你的选择跳过了 {count} 个：\n{lines}{more}",
                      "\n\nSkipped {count} by your choice:\n{lines}{more}"),
    "import.kept": ("  保留 {id} {name}", "  kept {id} {name}"),
    "import.skipped_nothing": ("  已跳过（数据库中没有相似的）",
                               "  skipped (nothing similar stored)"),

    # ----------------------------------------------------------- clipboard
    "clip.no_image_title": ("剪贴板里没有图片", "No image on the clipboard"),
    "clip.read_failed": ("读不到剪贴板：{error}", "could not read the clipboard: {error}"),
    "clip.files_no_image": ("剪贴板里是文件，但其中没有一个是图片。",
                            "the clipboard holds files, but none of them is an image"),
    "clip.no_image": ("剪贴板里没有图片。", "the clipboard does not contain an image"),

    # ------------------------------------------------------------ database
    "db.exists": ("数据库 {id} 已经存在：{path}", "database {id} already exists at {path}"),
    "db.not_found": ("{root} 下没有编号为 {id} 的数据库", "no database {id} under {root}"),

    # ----------------------------------------------------------------- CLI
    "cli.desc": ("命令行版本：用图片文件代替剪贴板。\n\n"
                 "    python -m iconmatch.cli list\n"
                 "    python -m iconmatch.cli match --db 1 shot.png\n"
                 "    python -m iconmatch.cli add   --db 1 shot.png --name 小火猴\n"
                 "    python -m iconmatch.cli add   --db 1 grid.png     # 自动切分网格\n"
                 "    python -m iconmatch.cli remove --db 1 0003",
                 "Headless companion to the GUI: work with image files instead of "
                 "the clipboard.\n\n"
                 "    python -m iconmatch.cli list\n"
                 "    python -m iconmatch.cli match --db 1 shot.png\n"
                 "    python -m iconmatch.cli add   --db 1 shot.png --name Pikachu\n"
                 "    python -m iconmatch.cli add   --db 1 grid.png   # split automatically\n"
                 "    python -m iconmatch.cli remove --db 1 0003"),
    "cli.help.root": ("数据库所在的文件夹", "database root folder"),
    "cli.help.lang": ("界面语言：zh（简体中文）或 en（English）",
                      "interface language: zh (Simplified Chinese) or en (English)"),
    "cli.help.list": ("列出所有数据库", "list databases"),
    "cli.help.match": ("用数据库查询图片文件", "match image files against a database"),
    "cli.help.add": ("把图片文件录入数据库", "add image files to a database"),
    "cli.help.scan": ("对一张截图跑一遍自动比对流程：切成一只只、逐只给结论"
                      "（和监视时用的是同一套代码）",
                      "run the automatic compare on a screenshot file: split it into "
                      "single icons and give a verdict per icon (the same code the "
                      "watcher runs)"),
    "cli.help.fight": ("把第几只当作“要打这只”存进数据库（从 1 开始，逗号分隔，"
                       "例如 --fight 1,3）",
                       "1-based indexes to store as \"about to fight\", comma "
                       "separated, e.g. --fight 1,3"),
    "cli.help.remove": ("按编号删除一个图标", "remove an icon by id"),
    "cli.help.name": ("只在单个文件时有意义", "only meaningful with a single file"),
    "cli.help.create": ("数据库不存在时自动新建", "create the database if missing"),
    "cli.help.force": ("即使已有相似图标也照样录入", "add even if a similar icon exists"),
    "cli.help.no_split": ("把每个文件都当成单个图标，不自动切分网格",
                          "treat each file as one icon instead of auto-splitting a grid"),
    "cli.no_dbs": ("{root} 下没有数据库", "no databases under {root}"),
    "cli.db_row": ("数据库 {id:03d}  {count} 个图标", "DB {id:03d}  {count} icon(s)"),
    "cli.no_db": ("{root} 下没有编号为 {id} 的数据库（加 --create 可以新建）",
                  "no database {id} under {root} (use --create)"),
    "cli.match_empty": ("{file}: N（数据库是空的）", "{file}: N (database is empty)"),
    "cli.match_row": ("{file}: {verdict}  最接近={id} {name} 相似度={sim:.3f} "
                      "突出度={rel:.3f}   {extra}",
                      "{file}: {verdict}  best={id} {name} sim={sim:.3f} "
                      "standout={rel:.3f}   {extra}"),
    "cli.grid": ("{file}: 网格，共 {count} 个图标", "{file}: grid of {count} icons"),
    "cli.skipped": ("  {name}: 已跳过 - 与 {id} {best} 太相似"
                    "（相似度={sim:.3f} 突出度={rel:.3f}）；要照样录入就加 --force",
                    "  {name}: SKIPPED - too similar to {id} {best} "
                    "(sim={sim:.3f} standout={rel:.3f}); use --force to add anyway"),
    "cli.added": ("  {name}: 已录入为 {id} {stored}", "  {name}: added as {id} {stored}"),
    "cli.removed": ("已删除 {id}", "removed {id}"),
    "cli.scan_empty": ("{file}: 这一屏不是选精灵界面，没什么可比的",
                       "{file}: not the pick-a-spirit screen - nothing to compare"),
    "cli.scan_head": ("{file}: 画面里有 {total} 只，其中 {new} 只没遇到过",
                      "{file}: {total} icon(s), {new} not seen before"),
    "cli.scan_row": ("  {index}. {state}   {detail}", "  {index}. {state}   {detail}"),
    "cli.fought": ("  -> 第 {index} 只已登记为 {id} {name}",
                   "  -> stored #{index} as {id} {name}"),
    "cli.fight_bad": ("--fight 只认编号，看不懂 {value}", "cannot read --fight: {value}"),

    # ---------------------------------------------------------- entry point
    "main.help.root": ("存放 db_XXX 数据库文件夹的目录",
                       "folder that holds the db_XXX directories"),
}
