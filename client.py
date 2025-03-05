# Mastodon.py imports
from mastodon import Mastodon, StreamListener

# Base python imports
import re
import time
import datetime
import html
import pprint
import shutil
import threading
import colorsys
import os
import requests
import io
import math
import warnings

from PIL import Image
import numpy as np

# prompt_toolkit imports
from prompt_toolkit.application import Application
from prompt_toolkit.application.current import get_app
from prompt_toolkit.layout import Layout, Window, Dimension
from prompt_toolkit.layout.controls import BufferControl
from prompt_toolkit.layout.processors import Transformation, Processor, ConditionalProcessor, HighlightSearchProcessor, HighlightSelectionProcessor, AppendAutoSuggestion, DisplayMultipleCursors
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
from prompt_toolkit.key_binding.defaults import load_key_bindings
from prompt_toolkit.history import FileHistory
from prompt_toolkit.enums import DEFAULT_BUFFER, SEARCH_BUFFER
from prompt_toolkit.completion import WordCompleter, Completer, CompleteEvent
from prompt_toolkit.filters import has_focus, is_done
from prompt_toolkit.eventloop.inputhook import set_eventloop_with_inputhook
from prompt_toolkit.document import Document
from prompt_toolkit.cursor_shapes import CursorShape

# Local imports
import sys
sys.path = ["."] + sys.path
import termwrap.unserwrap as unserwrap

# Globals
quitting = False
watched = []
watched_streams = []
title_offset = 0
title_dirty = True
last_rows = 0
last_cols = 0
last = None
cli_tokens = []

# Helper function: make sure app config is set up
def ensure_app_config(url_file, client_file, user_file):
    if not os.path.isfile(url_file):
        print("No settings found.")
        base_url = input("Instance URL: ")

        if not os.path.isfile(client_file):
            Mastodon.create_app(
                'tootmage alpha',
                api_base_url = base_url,
                to_file = client_file
            )
        auth_app = Mastodon(client_id=client_file, api_base_url=base_url)

        print(auth_app.auth_request_url())

        # open the URL in the browser and paste the code you get
        auth_app.log_in(
            code=input("Enter the OAuth authorization code: "),
            to_file=user_file
        )

        try:
            if auth_app.account_verify_credentials() is not None:
                with open(url_file, "w") as f:
                    f.write(base_url)
            else:
                print("Whoops, that went wrong - try again.")
                sys.exit(0)
        except:
            print("Whoops, that went wrong - try again.")
            sys.exit(0)

# ANSI escape and other output convenience functions
def ansi_rgb(r, g, b):
    r = int(round(r * 255.0))
    g = int(round(g * 255.0))
    b = int(round(b * 255.0))
    if theme_col_mode == "rgb":
        return "\33[38;2;{};{};{}m".format(str(r), str(g), str(b))
    return ""

def ansi_clear():
    return "\33[2J"

def ansi_reset():
    return "\33[m"

def cursor_save():
    sys.stdout.write('\0337')

def cursor_restore():
    sys.stdout.write('\0338')

def cursor_reset():
    sys.stdout.write("\033[" + str(shutil.get_terminal_size()[1]) + ";0H")

def cursor_to(x, y):
    sys.stdout.write("\033[" + str(y) + ";" + str(x) + "H")

def clear_line(clear_len = 0):
    if clear_len == 0:
        sys.stdout.write("\033[0K")
    else:
        sys.stdout.write(" " * clear_len)
        sys.stdout.write("\033[" + str(clear_len) + "D")

def clear_screen():
    sys.stdout.write('\033[2J')

def draw_line(style, line_len):
    sys.stdout.write(style + (glyphs["line"] * line_len))

# Avatar tools
avatar_cache = {}
def get_avatar_cols(avatar_url):
    avatar_resp = requests.get(avatar_url)
    avatar_image = Image.open(io.BytesIO(avatar_resp.content))
    avatar_image = avatar_image.resize((60, 60))
    avatar_image = avatar_image.convert('RGBA').convert('RGB').convert('HSV')
    avatar = avatar_image.load()

    hue_bins = list(map(lambda x: [], range(1 + 255 // 10)))
    hue_weights = [0.0] * (1 + 255 // 10)
    center_x = avatar_image.size[0] / 2
    center_y = avatar_image.size[1] / 2
    for y in range(avatar_image.size[1]):
        for x in range(avatar_image.size[0]):
            x_dev = (x - center_x) / avatar_image.size[0]
            y_dev = (y - center_y) / avatar_image.size[1]
            center_dist = math.sqrt(math.pow(x_dev, 2.0) + math.pow(y_dev, 2.0))
            col = avatar[x, y]
            hue_bin = col[0] // 10
            hue_bins[hue_bin].append(col)
            hue_weights[hue_bin] += 0.5 + (col[1] / 255.0) * 0.5 + center_dist * 0.1 + abs(col[2] / 255.0 - 0.5) * 0.25

    hues_sorted = [x for _, x in sorted(zip(hue_weights, hue_bins))]
    primary_cols = []
    all_most_common_cols = []
    for hue in reversed(hues_sorted[-4:]):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            try:
                most_common_cols = list(reversed(sorted(set(hue), key=hue.count)))
                all_most_common_cols = most_common_cols + all_most_common_cols
                found_col = False
                for test_col in np.array(all_most_common_cols):
                    worst_difference = 100.0
                    if len(primary_cols) > 0:
                        for col in primary_cols:
                            worst_difference = min(
                                np.linalg.norm(col - np.array(colorsys.hsv_to_rgb(*test_col / 255.0))),
                                worst_difference
                            )
                    else:
                        worst_difference = 100.0
                    if worst_difference > 0.2:
                        found_col = True
                        primary_cols.append(list(np.array(colorsys.hsv_to_rgb(*(test_col / 255.0)))))
                        break
                if not found_col:
                    median_col = np.median(hue, axis=0)
                    primary_cols.append(list(np.array(colorsys.hsv_to_rgb(*(median_col / 255.0)))))
            except:
                primary_cols.append(primary_cols[0])
    return primary_cols

def get_avatar(avatar_url):
    if avatar_url in avatar_cache:
        return avatar_cache[avatar_url]
    else:
        try:
            avatar_cols = get_avatar_cols(avatar_url)
            avatar = ""
            for col in avatar_cols:
                avatar = avatar + ansi_rgb(*col) + glyphs["avatar"]
        except:
            avatar = ansi_rgb(0, 0, 0) + (glyphs["avatar"] * 4)  # fallback
        avatar_cache[avatar_url] = avatar
        return avatar

# Mastodon API dict pretty printers
def clean_text(text, style_names, style_text):
    content_clean = re.sub(r'<a [^>]*href="([^"]+)">[^<]*</a>', r'\1', text)
    content_clean = content_clean.replace('<span class="h-card">', style_names)
    content_clean = content_clean.replace('</span><span class="ellipsis">', "")
    content_clean = content_clean.replace('</span><span class="invisible">', "")
    content_clean = re.sub(r'</span><span class="[^"]*">', '', content_clean)
    content_clean = content_clean.replace('</span>', style_text)
    content_clean = content_clean.replace("</p>", "\n")
    content_clean = re.sub(r"<br[^>]*>", "\n", content_clean)
    content_clean = html.unescape(str(re.compile(r'<.*?>').sub("", content_clean).strip()))

    content_split = []
    for line in content_clean.split("\n"):
        content_split.append(style_text + line)
    return "\n".join(content_split)

def number_urls(text, status, style_url_nums, style_text):
    urls = re.findall(
        r'http[s]?://(?:[a-zA-Z0-9$-_@.&+!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',
        text
    )
    url_num = 0
    replaced_urls = []

    # URLs in text
    for url in urls:
        if url not in replaced_urls:
            text = text.replace(url, style_url_nums + "(" + str(url_num) + ")" + style_text + " " + url)
            replaced_urls.append(url)
            url_num += 1

    # Attachments
    if not status is None:
        for attachment in status["media_attachments"]:
            if attachment["type"] in ["image", "video", "gifv", "audio"]:
                text = text + " " + style_url_nums + "(" + str(url_num) + ")" + style_text + " " + glyphs[attachment["type"]]
                url_num += 1
    return text, replaced_urls


def image_to_ansi_blocky(image, width=80):
    image = image.convert("RGB")

    # Resize
    orig_w, orig_h = image.size
    aspect_ratio = orig_h / orig_w
    new_height = int(math.ceil(width * aspect_ratio))
    new_height = max(new_height, 1)
    resized = image.resize((width, new_height), Image.LANCZOS)

    # Build ANSI output
    lines = []
    for y in range(0, new_height, 2):
        row_chars = []
        y_next = y + 1
        for x in range(width):
            r_top, g_top, b_top = resized.getpixel((x, y))
            if y_next < new_height:
                r_bot, g_bot, b_bot = resized.getpixel((x, y_next))
            else:
                r_bot, g_bot, b_bot = (0, 0, 0)
            row_chars.append(
                f"\033[38;2;{r_top};{g_top};{b_top}m"
                f"\033[48;2;{r_bot};{g_bot};{b_bot}m▀"
            )
        row_chars.append("\033[0m")
        lines.append("".join(row_chars))
    return lines

def pprint_status(result_prefix, result, scrollback, cw=False, images=False):
    content_clean = ""
    if result.spoiler_text is not None and len(result.spoiler_text) > 0:
        content_clean = theme["cw"] + "[CW: " + result.spoiler_text + "] "
    if not cw or result.spoiler_text is None or len(result.spoiler_text) == 0:
        content_clean += clean_text(result["content"], theme["names_inline"], theme["text"])
    content_clean, result["__urls"] = number_urls(content_clean, result, theme["url_nums"], theme["text"])

    time_formatted = datetime.datetime.strftime(result["created_at"], '%H:%M:%S')
    status_icon = glyphs[result["visibility"]]

    avatar = get_avatar(result["account"]["avatar_static"])

    scrollback.print(
        theme["ids"] + result_prefix + theme["names"] + result["account"]["acct"]
        + theme["dates"] + " @ " + time_formatted,
        theme["visibility"] + status_icon
    )
    scrollback.print(avatar + " " + content_clean + " ")

    if images:
        if "media_attachments" in result:
            for attachment in result["media_attachments"]:
                if attachment["type"] == "image":
                    try:
                        image_url = attachment["url"]
                        image_resp = requests.get(image_url)
                        image = Image.open(io.BytesIO(image_resp.content))
                        scrollback.print(image)
                    except:
                        scrollback.print("Error loading image\n")

    scrollback.print("")
    return

def pprint_reblog(result_prefix, result, scrollback, cw=False, images=False):
    content_clean = ""
    if result.reblog.spoiler_text is not None and len(result.reblog.spoiler_text) > 0:
        content_clean = theme["cw"] + "[CW: " + result.reblog.spoiler_text + "] "
    if not cw or result.reblog.spoiler_text is None or len(result.reblog.spoiler_text) == 0:
        content_clean += clean_text(result.reblog["content"], theme["names_inline"], theme["text"])
    content_clean, result["__urls"] = number_urls(content_clean, result.reblog, theme["url_nums"], theme["text"])

    time_formatted = datetime.datetime.strftime(result["created_at"], '%H:%M:%S')

    avatar = get_avatar(result["account"]["avatar_static"])
    avatar_orig = get_avatar(result["reblog"]["account"]["avatar_static"])

    scrollback.print(theme["ids"] + result_prefix + theme["names"] + result["account"]["acct"]
                     + theme["dates"] + " @ " + time_formatted)
    scrollback.print(avatar + " " + theme["reblog"] + glyphs["reblog"] + " " + avatar_orig
                     + " " + theme["names"] + result["reblog"]["account"]["acct"])
    scrollback.print(content_clean)
    if images:
        if "media_attachments" in result.reblog:
            for attachment in result.reblog["media_attachments"]:
                if attachment["type"] == "image":
                    try:
                        image_url = attachment["url"]
                        image_resp = requests.get(image_url)
                        image = Image.open(io.BytesIO(image_resp.content))
                        scrollback.print(image)
                    except:
                        scrollback.print("Error loading image\n")

    scrollback.print("")
    return

def pprint_notif(result_prefix, result, scrollback, cw=False):
    content_clean = ""
    if result.status.spoiler_text is not None and len(result.status.spoiler_text) > 0:
        content_clean = theme["cw_notif"] + "[CW: " + result.status.spoiler_text + "] "
    if not cw or result.status.spoiler_text is None or len(result.status.spoiler_text) == 0:
        content_clean += clean_text(result["status"]["content"], theme["names_notif"], theme["text_notif"])
    content_clean, result["__urls"] = number_urls(content_clean, None, theme["url_nums"], theme["text_notif"])

    time_formatted = datetime.datetime.strftime(result["created_at"], '%H:%M:%S')

    avatar = get_avatar(result["account"]["avatar_static"])

    scrollback.print(theme["ids"] + result_prefix + theme["names"] + result["account"]["acct"]
                     + theme["dates"] + " @ " + time_formatted)
    scrollback.print(avatar + " " + theme[result["type"]] + glyphs[result["type"]] + " " + content_clean)
    scrollback.print("")
    return

def pprint_follow(result_prefix, result, scrollback):
    time_formatted = datetime.datetime.strftime(result["created_at"], '%H:%M:%S')

    avatar = get_avatar(result["account"]["avatar_static"])

    scrollback.print(
        theme["ids"] + result_prefix + " " + avatar + " " + theme["follow"]
        + glyphs["follow"] + " " + theme["names"] + result["account"]["acct"]
        + theme["dates"] + " @ " + time_formatted
    )
    scrollback.print("")
    return

def pprint_account(result_prefix, result, scrollback, cw=False):
    content_clean = clean_text(result["note"], theme["names_inline"], theme["text"])
    content_clean, result["__urls"] = number_urls(content_clean, None, theme["url_nums"], theme["text"])

    time_formatted = datetime.datetime.strftime(result["created_at"], '%H:%M:%S %d %b %Y')
    avatar = get_avatar(result["avatar_static"])

    scrollback.print(theme["ids"] + result_prefix + theme["names"] + result["acct"] + " | "
                     + result["display_name"] + " " + avatar)
    scrollback.print(content_clean)
    scrollback.print(theme["text"] + "* Known since " + theme["dates"] + time_formatted)
    scrollback.print(
        theme["text"] + "* Loc. statuses: " + theme["names_inline"] + str(result["statuses_count"])
        + theme["text"] + ", Loc. followers: " + theme["names_inline"] + str(result["followers_count"])
        + theme["text"] + ". Loc. following: " + theme["names_inline"] + str(result["following_count"])
    )
    scrollback.print("")
    return

def pprint_result(result, scrollback, result_prefix="", not_pretty=False, cw=False, expand_using=None, expand_unknown=False, images=False):
    retval = None
    if expand_using is not None:
        to_expand = result
        if "content" not in to_expand:
            to_expand = to_expand.status
        context = expand_using.status_context(to_expand)
        result = list(reversed(context.ancestors + [to_expand] + context.descendants))
        retval = result

    if isinstance(result, list):
        for num, sub_result in enumerate(reversed(result)):
            sub_result_prefix = str(len(result) - num - 1)
            pprint_result(sub_result, scrollback, sub_result_prefix, not_pretty, cw=cw, expand_unknown=expand_unknown, images=images)
        return retval

    if result_prefix != "":
        result_prefix = "#" + result_prefix.ljust(4)

    if isinstance(result, dict):
        if "content" in result:
            if "reblog" in result and result["reblog"] is not None:
                pprint_reblog(result_prefix, result, scrollback, cw=cw, images=images)
            else:
                pprint_status(result_prefix, result, scrollback, cw=cw, images=images)
            return

        if "type" in result:
            if result["type"] == "mention":
                pprint_status(result_prefix, result["status"], scrollback, cw=cw)
                return

            if result["type"] in ["reblog", "favourite"]:
                pprint_notif(result_prefix, result, scrollback, cw=cw)
                return

            if result["type"] == "follow":
                pprint_follow(result_prefix, result, scrollback)
                return

        if "acct" in result:
            pprint_account(result_prefix, result, scrollback)
            return

    if expand_unknown:
        scrollback.print(theme["text"] + pprint.pformat(result))
    else:
        scrollback.print(theme["text"] + "(Unknown object)")

# Helper: combines two strings, aligning one left and one right, and does wrapping
def align(left_part, right_part, width):
    max_spaces = max(width - (unserwrap.ansilen_unicode(left_part) + unserwrap.ansilen_unicode(right_part) - 1), 0)
    for i in reversed(range(max_spaces)):
        aligned = left_part + (" " * i) + right_part
        result = unserwrap.wrap(aligned, width)
        if len(result) == 1:
            return result
    return unserwrap.wrap(left_part + " " + right_part, width)

# Scrollback column with internal "result history" buffer
class Scrollback:
    def __init__(self, title, offset, width, expand_unknown=False):
        self.scrollback = []
        self.dirty = True
        self.pos = 0
        self.added = False
        self.title = title
        self.offset = offset + 1
        self.width = width
        self.active = False
        self.result_history = []
        self.result_counter = -1
        self.full_redraw = True
        self.wrapped_cache = []
        self.expand_unknown = expand_unknown

    def needs_redraw(self):
        return self.full_redraw or self.dirty

    def set_active(self, active):
        self.active = active
        self.full_redraw = True

    def add_result(self, result):
        self.result_counter = (self.result_counter + 1) % 1000
        if len(self.result_history) > self.result_counter:
            self.result_history[self.result_counter] = result
        else:
            self.result_history.append(result)
        pprint_result(result, self, str(self.result_counter), cw=True, expand_unknown = self.expand_unknown)

    def print(self, x, right_side=None):
        if isinstance(x, Image.Image):
            self.scrollback.append((x, None))
        elif isinstance(x, str):
            new_lines = x.split("\n")
            right_side_lines = [right_side] * len(new_lines)
            self.scrollback.extend(zip(new_lines, right_side_lines))
        if len(self.scrollback) > 3000:
            self.scrollback = self.scrollback[len(self.scrollback)-3000:]
            self.wrapped_cache = self.wrapped_cache[len(new_lines):]
        self.dirty = True
        self.added = True

    def scroll(self, how_far):
        self.pos = self.pos + how_far
        self.dirty = True

    def draw(self, print_height, max_width):
        print_width = min(self.width, max_width - self.offset + 1)
        if print_width < 0:
            return

        if self.full_redraw:
            self.wrapped_cache = []
            cursor_to(self.offset + 1, 1)
            if self.active:
                sys.stdout.write(theme["active"] + self.title + " #")
            else:
                sys.stdout.write(theme["titles"] + self.title + "  ")

            cursor_to(self.offset, 2)
            line_style = theme["lines"]
            if self.active:
                line_style = theme["active"]
            draw_line(line_style, print_width)
            self.full_redraw = False
            self.dirty = True

        if self.dirty == False:
            return
        self.dirty = False

        text_width = max(print_width - 2, 0)
        if text_width == 0:
            return

        wrapped_lines = []
        for counter, (line, right_side) in enumerate(self.scrollback):
            if counter >= len(self.wrapped_cache):
                if isinstance(line, str):
                    if right_side is not None:
                        new_lines = align(line, right_side, text_width)
                    else:
                        new_lines = unserwrap.wrap(line, text_width)
                    if len(new_lines) == 0:
                        new_lines = [""]
                elif isinstance(line, Image.Image):
                    new_lines = image_to_ansi_blocky(line, text_width) + [""]
                wrapped_lines.extend(new_lines)
                self.wrapped_cache.append(new_lines)
            else:
                wrapped_lines.extend(self.wrapped_cache[counter])

        self.pos = max(self.pos, print_height)
        self.pos = min(self.pos, len(wrapped_lines))

        if self.added:
            self.pos = len(wrapped_lines)
        self.added = False

        print_end = min(self.pos, len(wrapped_lines))
        print_start = max(print_end - print_height, 0)
        print_lines = wrapped_lines[print_start:print_end]

        for line_pos, line in enumerate(print_lines):
            cursor_to(self.offset, line_pos + 3)
            clear_line(print_width + 1)
            cursor_to(self.offset + 1, line_pos + 3)
            sys.stdout.write(line)


# Return app title, possibly animated
def get_title():
    title_str = ""
    for index, character in enumerate("tootmage"):
        r, g, b = colorsys.hsv_to_rgb((index * 1.5 + title_offset) / 30.0, 0.8, 1.0)
        title_str += ansi_rgb(r, g, b) + character
    return title_str

def screen_update_once():
    global title_dirty    
    global last_rows
    global last_cols

    need_redraw = False
    for sc in buffers:
        if sc.needs_redraw():
            need_redraw = True

    if title_dirty:
        need_redraw = True
        title_dirty = False

    cols, rows = shutil.get_terminal_size()
    if rows != last_rows or cols != last_cols:
        sys.stdout.write(ansi_clear())
        for sc in buffers:
            sc.full_redraw = True
        last_rows = rows
        last_cols = cols
        need_redraw = True

    if not need_redraw:
        return

    cursor_save()
    cursor_to(cols - len("tootmage") + 1, 0)
    sys.stdout.write(get_title() + "")
    print_height = rows - 4
    for sc in buffers:
        sc.draw(print_height, cols)
    draw_prompt_separator()
    cursor_restore()

def draw_prompt_separator():
    cols, rows = shutil.get_terminal_size()
    cursor_to(0, rows - 1)
    draw_line(theme["lines"], cols)

def move_cursor(new, xoff):
    cursor_to(new.x + xoff, new.y)

# Token capturing processor for v3
class StoreTokens(Processor):
    def apply_transformation(self, transformation_input):
        global cli_tokens
        cli_tokens = transformation_input.fragments
        return Transformation(transformation_input.fragments)

def app_update(context):
    """
    This function is used as an inputhook in the event loop.
    It is called repeatedly while prompt_toolkit is idle,
    so we can do background UI updates, watchers, etc.
    """
    if quitting:
        return

    global title_offset
    global title_dirty
    global watched

    # We do a small idle loop: poll watchers, streams, etc.
    while True:
        # If there's typed input waiting, break so prompt_toolkit can proceed.
        if context.input_is_ready():
            break

        # Animate the title if there's a command runner thread
        thread_names = [t.name for t in threading.enumerate()]
        if "command_runner" in thread_names:
            title_offset += 2.0
            title_dirty = True

        # Run watchers
        for watched_expr in watched:
            funct, last_exec, exec_every, scrollback = watched_expr
            if time.time() - last_exec > exec_every:
                watched_expr[1] = time.time()
                eval_command_thread("", funct, scrollback, interactive=False)

        # Check watchers for streams
        for i in range(len(watched_streams)):
            if not watched_streams[i][0].is_alive():
                try:
                    watched_streams[i][0].close()
                except:
                    pass
                handle, function, collector = watched_streams[i]
                new_stream = function(collector, run_async=True)
                watched_streams[i] = (new_stream, function, collector)

        # Redraw main UI
        screen_update_once()

        # Manually draw the CLI content
        cols, rows = (last_cols, last_rows)
        cursor_to(0, rows)
        sys.stdout.write(theme["prompt"] + ">>> ")

        # Render any “fragments” we captured:
        for (style_str, text) in cli_tokens:
            # look up a style or fallback
            token_style = style_str if style_str in theme["prompt_toolkit_tokens"] else "Default"
            if token_style not in theme["prompt_toolkit_tokens"]:
                sys.stdout.write(theme["prompt"] + text)
            else:
                sys.stdout.write(theme["prompt_toolkit_tokens"][token_style] + text)

        # Set cursor to correct position
        cursor_to(get_app().layout.current_window.content.buffer.document.cursor_position_col + 5, rows)
        sys.stdout.flush()        

        time.sleep(0.01)

# Run a command and put the result in scrollback
def eval_command(orig_command, command, scrollback, interactive=True, expand_using=None):
    global last
    global buffers
    if interactive:
        scrollback.print("")
        scrollback.print(theme["text"] + "> " + orig_command)
    try:
        result_ns = {}
        print_result = None

        if callable(command):
            print_result = command()
        else:
            command_code = compile(command, '<string>', 'exec')
            exec(command_code, globals(), result_ns)

        if interactive:
            for var_name in result_ns.keys():
                globals()[var_name] = result_ns[var_name]
            if "__thread_res" in result_ns:
                last = result_ns["__thread_res"]
                print_result = last
        else:
            if "__thread_res" in result_ns:
                print_result = result_ns["__thread_res"]

        if not isinstance(print_result, list) and expand_using is None:
            print_result = [print_result]
            last = [last]

        pprint_retval = pprint_result(print_result, scrollback, cw=not interactive, expand_using=expand_using, expand_unknown=True, images=True)
        if pprint_retval is not None:
            last = pprint_retval
        buffers[-1].result_history = last

    except Exception as e:
        scrollback.print(str(command) + " -> " + str(e))

# Run a command, in a thread
def eval_command_thread(orig_command, command, scrollback, interactive=True, expand_using=None):
    thread_name = "command_runner"
    if not interactive:
        thread_name += "_bg"

    def run():
        eval_command(orig_command, command, scrollback, interactive, expand_using)

    exec_thread = threading.Thread(target=run, daemon=True, name=thread_name)
    exec_thread.start()

# Set up keybinds for prompt toolkit
key_bindings = KeyBindings()

@key_bindings.add("tab")
def generate_completions(event):
    buff = event.app.current_buffer
    if buff.complete_state:
        buff.complete_next()
    else:
        buff.start_completion(select_first=True)
        buff.complete_next()

@key_bindings.add("enter")
def accept_line(event):
    # Get text and clear buffer
    text = event.app.current_buffer.text
    event.app.current_buffer.reset()

    # store to history
    global history
    if history is not None:
        history.append_string(text)

    # Set the return value
    event.app.exit(result=text)

@key_bindings.add("c-l")
def clear_screen_key(event):
    sys.stdout.write(ansi_clear())
    for sc in buffers:
        sc.full_redraw = True

@key_bindings.add("pageup")
def page_up(event):
    buffers[buffer_active].scroll(-2)

@key_bindings.add("pagedown")
def page_down(event):
    buffers[buffer_active].scroll(2)

@key_bindings.add("escape", "down")
@key_bindings.add("c-right")
def next_buffer_event(event):
    global buffer_active
    buffer_new = buffer_active + 1
    if buffer_new >= len(buffers):
        buffer_new = 0
    buffers[buffer_active].set_active(False)
    buffers[buffer_new].set_active(True)
    buffer_active = buffer_new

@key_bindings.add("escape", "up")
@key_bindings.add("c-left")
def prev_buffer_event(event):
    global buffer_active
    buffer_new = buffer_active - 1
    if buffer_new < 0:
        buffer_new = len(buffers) - 1
    buffers[buffer_active].set_active(False)
    buffers[buffer_new].set_active(True)
    buffer_active = buffer_new

def watch(function, scrollback, every_s):
    watched.append([function, 0, every_s, scrollback])

class EventCollector(StreamListener):
    def __init__(self, event_handler=None, notification_event_handler=None):
        super(EventCollector, self).__init__()
        self.event_handler = event_handler
        self.notification_event_handler = notification_event_handler

    def on_update(self, status):
        if self.event_handler is not None:
            self.event_handler(status)

    def on_notification(self, notification):
        # Pop up notification
        user = "@" + notification.account.acct
        if notification.type == "mention":
            user += " mentioned you:"
        if notification.type == "reblog":
            user += " boosted:"
        if notification.type == "favourite":
            user += " favourited:"
        if notification.type == "follow":
            user += " followed you."

        text = ""
        if "status" in notification and notification.status is not None:
            text = clean_text(notification.status.content, "", "")

        notify_command(user, text)

        if self.notification_event_handler is not None:
            self.notification_event_handler(notification)

def watch_stream(function, scrollback=None, scrollback_notifications=None,
                 initial_fill=None, initial_fill_notifications=None):
    def watch_stream_internal():
        event_handler = None
        if scrollback is not None:
            event_handler = scrollback.add_result
            if initial_fill is not None:
                initial_data = initial_fill()
                for result in reversed(initial_data):
                    event_handler(result)

        notification_event_handler = None
        if scrollback_notifications is not None:
            notification_event_handler = scrollback_notifications.add_result
            if initial_fill_notifications is not None:
                initial_data_notif = initial_fill_notifications()
                for result in reversed(initial_data_notif):
                    notification_event_handler(result)

        collector = EventCollector(event_handler, notification_event_handler)
        handle = function(collector, run_async=True)
        watched_streams.append((handle, function, collector))

    watch_start_thread = threading.Thread(target=watch_stream_internal, daemon=True, name="start_watch")
    watch_start_thread.start()

class MastodonFuncCompleter(Completer):
    """
    Completer that completes commands and also Mastodon usernames.
    """
    def __init__(self, api):
        self.base_completer = WordCompleter(MastodonFuncCompleter.get_func_names(), ignore_case = True, match_middle = True)
        self.cached_usernames = {}
        self.complete_names_with = api

    # Sorting... is complicated and phenomenological.
    @staticmethod
    def prefix_val(name):
            val = 0
            if not '_' in name:
                val -= 100000
            
            if name.startswith('toot'):
                val -= 11000
            
            if name.startswith('reply'):
                val -= 15000
            
            if name.startswith('status'):
                val -= 10000
            
            if name.startswith('account'):
                val -= 9000
            
            if name.startswith('media'):
                val -= 8000
            
            if name.startswith('timeline'):
                val -= 7000
            
            if name.startswith('notifications'):
                val -= 6000
            
            if name.startswith('follow'):
                val -= 5000
            
            if name.startswith('domain'):
                val -= 4000
            
            val = val + len(name)
            return val

    @staticmethod
    def suffix_key(name):
        if "_" in name:
            return name[name.rfind("_") + 1:]
        return name

    @staticmethod
    def overrride_key(name):
        if name.endswith('reply'):
            return 0
        if name.endswith('boost'):
            return 0
        if name.endswith('expand'):
            return 0
        if name.endswith('toot'):
            return 0
        if name.endswith('view'):
            return 0
        if name.endswith('quit'):
            return 0
        return 1

    @staticmethod
    def combined_key(name):
        return(MastodonFuncCompleter.overrride_key(name.text), MastodonFuncCompleter.suffix_key(name.text), MastodonFuncCompleter.prefix_val(name.text))

    @staticmethod
    def get_func_names():
        funcs = dir(Mastodon)
        funcs = list(filter(lambda x: not x.startswith("_"), funcs))
        funcs = list(filter(lambda x: not x.endswith("_version"), funcs))    
        funcs = list(filter(lambda x: not "stream_" in x, funcs))
        funcs = list(filter(lambda x: not "fetch_" in x, funcs))
        funcs = list(filter(lambda x: not "create_app" in x, funcs))
        funcs = list(filter(lambda x: not "create_app" in x, funcs))
        funcs = list(filter(lambda x: not "auth_request_url" in x, funcs))
        funcs = ["quit", "status_reply", "status_expand", "status_boost", "status_view"] + funcs + ["help"]
        
        return sorted(funcs, key = MastodonFuncCompleter.prefix_val)

    def get_completions(self, document, complete_event):
        completion_text = document.text.replace("-", "_")
        match_text = document.get_word_before_cursor(WORD=True)
        
        if match_text.startswith("@"):
            if not match_text in self.cached_usernames:
                name_matches = self.complete_names_with.account_search(match_text[1:])
                self.cached_usernames[match_text] = list(map(lambda x: "@" + x.acct, name_matches))
            name_completer = WordCompleter(self.cached_usernames[match_text], ignore_case = True, match_middle = True, WORD=True)
            yield from name_completer.get_completions(document, complete_event)
        
        base_completions = list(self.base_completer.get_completions(document, complete_event))
        base_completions = sorted(base_completions, key = MastodonFuncCompleter.combined_key)
        
        best_matches = []
        good_matches = []
        for match in base_completions:
            if MastodonFuncCompleter.suffix_key(match.text).startswith(match_text):
                best_matches.append(match)
            else:
                good_matches.append(match)
        for match in best_matches:
            yield match
        for match in good_matches:
            yield match

# Read settings
exec(open("./settings.py", 'rb').read().decode("utf-8"))

# Don't want to use prompt_toolkits layouting, lets make it so we can draw
# all the tokens ourselves!
def create_bottom_repl_application(completer = None,  history = None,):
    input_processors = [
        ConditionalProcessor(
            HighlightSearchProcessor(),
             has_focus(SEARCH_BUFFER)
        ),
        HighlightSelectionProcessor(),
        ConditionalProcessor(
            AppendAutoSuggestion(), 
            has_focus(DEFAULT_BUFFER) & ~is_done
        ),
        DisplayMultipleCursors(),
        # Special "processor" that just stores the tokens so we can paint them ourselves
        StoreTokens()
    ]
    
    buff = Buffer(
        history = history,
        completer = completer,
        multiline = False,
    )
    layout = Layout(Window(
        BufferControl(
            input_processors = input_processors,
            preview_search = True,
            buffer = buff,
        ),
        height=Dimension.exact(1),
        wrap_lines = False,
    ))
    default_key_bindings = load_key_bindings()
    merged_key_bindings = merge_key_bindings([
        default_key_bindings,
        key_bindings
    ])
    app = Application(
        layout = layout,
        key_bindings = merged_key_bindings,
        enable_page_navigation_bindings = True,
        erase_when_done = True,
        cursor = CursorShape.BLOCK,
    )
    set_eventloop_with_inputhook(app_update)
    return app

# Example run_app function:
def run_app():
    global history
    history = FileHistory(".tootmage_history")
    completer = MastodonFuncCompleter(m)

    app = create_bottom_repl_application(
        completer = completer,
        history = history
    )
    
    while True:
        # The app.run() will block until user hits Enter or we exit.
        user_input = app.run()

        # user_input is what they typed.
        orig_command = user_input
        command = user_input

        if len(command.strip()) == 0:
            continue

        if command[0] == ";":
            command = command[1:]
            py_direct = True
            expand_using = None
        else:
            py_direct = False
            expand_using = None

        command = orig_command
        
        if len(command.strip()) == 0:
            continue
        
        # Starts with semicolon -> python command
        py_direct = False
        expand_using = None
        if command[0] == ";":
            command = command[1:]
            py_direct = True
        else:
            # Starts with # or . -> buffer ref
            if command[0] in "#.":
                pass
            else:
                # Direct command -> autocomplete
                command_parts = command.split(" ")
                potential_commands = list(MastodonFuncCompleter(m).get_completions(
                    Document(command_parts[0]),
                    CompleteEvent(False, True)
                ))
                if len(potential_commands) > 0:
                    command_parts[0] = potential_commands[0].text
                
                # Dotify command part if unambiguously needed
                if command_parts[0].startswith("status_"):
                    if len(command_parts) >= 2 and not (command_parts[1].startswith(".") or command_parts[1].startswith("#")):
                        command_parts[1] = "." + command_parts[1]
                
                # Special handling for boost, reply, expand commands
                if command_parts[0] == "status_reply" and len(command_parts) >= 2:
                    command_parts_new = []
                    command_parts_new.append("status_post")
                    
                    in_reply_to = command_parts[1]
                    in_reply_to = re.sub(r'#([0-9]+)', r'buffers[' + str(buffer_active) + r'].result_history[\1]', in_reply_to)
                    in_reply_to = re.sub(r'#', r'buffers[' + str(buffer_active) + '].result_history', in_reply_to)
                    in_reply_to = re.sub(r'\.([0-9]+)\.([0-9]+)', r'buffers[\1].result_history[\2]', in_reply_to)
                    
                    try:
                        in_reply_to_obj = eval(in_reply_to)
                        if "mentions" not in in_reply_to_obj:
                            command_parts[1] = command_parts[1] + ".status"
                    except:
                        pass
                    
                    toot_text = " ".join(command_parts[2:])
                    toot_text = toot_text.replace("\"", "\\\"")
                    toot_text = "\"" + toot_text + "\""
                    toot_text = '"".join(map(lambda x: ("@" + x.acct + " ") if x.acct != m._acct else "", [' + \
                        command_parts[1] + '.account] + ' + command_parts[1] + '.mentions)) + ' + toot_text
                    command_parts_new.append(toot_text)
                    
                    command_parts_new.append(", in_reply_to_id=" + command_parts[1])
                    command_parts_new.append(", sensitive=" + command_parts[1] + ".sensitive")
                    command_parts_new.append(", spoiler_text=" + command_parts[1] + ".spoiler_text")
                    
                    command_parts = command_parts_new
                
                if command_parts[0] == "status_boost":
                    command_parts[0] = "status_reblog"
                
                if command_parts[0] == "status_expand":
                    command_parts = [command_parts[1]]
                    expand_using = m
                
                if command_parts[0] == "toot":
                    toot_text = " ".join(command_parts[1:])
                    toot_text = toot_text.replace("\"", "\\\"")
                    toot_text = "\"" + toot_text + "\""
                    command_parts = [command_parts[0], toot_text]
                    
                if command_parts[0] == "status_view":
                    if len(command_parts) <= 2:
                        url_str = command_parts[1] + ".reblog.url if ('reblog' in " + command_parts[1] + " and " + command_parts[1] + ".reblog != None) else (" + \
                            command_parts[1] + ".status.url if 'status' in " + command_parts[1] + " else " + \
                            command_parts[1] + ".url)"
                    else:
                        url_str = command_parts[1] + '["__urls"][' +  command_parts[2] + ']'
                    command = "view_command(" + url_str + ")"
                    py_direct = True
                
                if command_parts[0] == "quit":
                    print("Quitting...")
                    for thread in watched_streams:
                        thread[0].close()
                    sys.exit(0)
                
                if command_parts[0] == "help":
                    help_text = """Base commands:
    status_view <status> [<url_num>] - View status or URL or attachment in browser. Alias: v
    status_expand <status> - Expand conversation. Alias: x
    status_boost <status> - Boost status: Alias: b
    status_reply <status> <text> - Reply to status: Alias: r
    toot <text> - Post a toot: Alias: t
    quit - Quit tootmage
    help - Show this help

Refering to results:
    The following are automatically expanded everywhere:
        .<buffer_num>.<result_num> - Result in specified buffer
        #<result_num> - Result in currently active buffer
    If specified on its own, the referred to status is displayed in the scratch buffer with expanded CW and images.
                                                            
Keyboard controls:
    Enter - Execute command
    Tab - Autocomplete
    up/down - Browse command history                                      
    PageUp/PageDown - Scroll currently active buffer
    Ctrl+Left/Ctrl+Right - Switch to previous/next buffer
    Ctrl+L - Repaint screen
                                      
Advanced commands:
    <any Mastodon.py function> - Execute Mastodon.py function
    ;<python code> - Execute python code directly
"""
                    for line in help_text.split("\n"):
                        buffers[-1].print(theme["text"] + line)
                    continue

                # Build actual command
                if  py_direct == False:
                    if expand_using == None:
                        command = command_parts[0] + "(" + " ".join(command_parts[1:]) + ")"
                        command = "m." + command
                    else:
                        command = command_parts[0]
                    
        command = re.sub(r'#([0-9]+)', r'buffers[' + str(buffer_active) + r'].result_history[\1]', command)
        command = re.sub(r'#', r'buffers[' + str(buffer_active) + '].result_history', command)
        command = re.sub(r'\.([0-9]+)\.([0-9]+)', r'buffers[\1].result_history[\2]', command)
        
        if command.find("=") == -1 or not py_direct:
            command = "__thread_res = (" + command + ")"
        
        eval_command_thread(orig_command, command, buffers[-1], expand_using = expand_using)

if __name__ == "__main__":
    run_app()
