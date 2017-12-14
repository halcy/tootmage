import sys
sys.path = ["."] + sys.path

from mastodon import Mastodon, StreamListener

import re
import time
import datetime
import html
import pprint
import shutil
import termwrap
import prompt_toolkit
import prompt_toolkit.contrib
import prompt_toolkit.contrib.completers
import threading
import colorsys
import os
import tty
import termios
import atexit
import requests
from PIL import Image
import io
import numpy as np
import math

# Patch prompt-toolkit a bit
prompt_toolkit.keys.Keys.ControlPageUp = prompt_toolkit.keys.Key("<C-PageUp>")
prompt_toolkit.keys.Keys.ControlPageDown = prompt_toolkit.keys.Key("<C-PageDown>")
prompt_toolkit.terminal.vt100_input.ANSI_SEQUENCES['\x1b[5;5~'] = prompt_toolkit.keys.Keys.ControlPageUp
prompt_toolkit.terminal.vt100_input.ANSI_SEQUENCES['\x1b[6;5~'] = prompt_toolkit.keys.Keys.ControlPageDown

# ANSI escape and other output convenience functions
def ansi_rgb(r, g, b):
    r = int(round(r * 255.0))
    g = int(round(g * 255.0))
    b = int(round(b * 255.0))
    return "\33[38;2;{};{};{}m".format(str(r), str(g), str(b))

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
    sys.stdout.write(style + ("═" * line_len))
    
# Avatar tools
avatar_cache = {}
def get_avatar_cols(avatar_url):
    avatar_resp = requests.get(avatar_url)
    avatar_image = Image.open(io.BytesIO(avatar_resp.content)).convert('RGBA').convert('HSV')
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
    for hue in reversed(hues_sorted[-4:]):
        try:
            most_common_col = np.array(max(set(hue), key=hue.count))
            median_col = np.median(hue, axis = 0)

            sameyness = 0.0
            if len(primary_cols) > 0:
                for col in primary_cols:
                    sameyness += np.linalg.norm(np.array(col) / 255.0 - np.array(most_common_col) / 255.0)
                sameyness = min(sameyness / len(primary_cols), 1.0)
            weighted_col = (sameyness * median_col + (1.0 - sameyness) * most_common_col) / 255.0
            primary_cols.append(list(np.array(colorsys.hsv_to_rgb(*weighted_col))))
        except:
            primary_cols.append(primary_cols[0])
    return primary_cols

def get_avatar(avatar_url, avatar_char = "█"):
    if avatar_url in avatar_cache:
        return avatar_cache[avatar_url]
    else:
        try:
            avatar_cols = get_avatar_cols(avatar_url)
            avatar = ""
            for col in avatar_cols:
                avatar = avatar + ansi_rgb(*col) + avatar_char
        except:
            avatar = ansi_rgb(0, 0, 0) + (avatar_char * 4) # TODO use handle hash avatar instead
        avatar_cache[avatar_url] = avatar
        return avatar

# Set the terminal to cbreak mode because 1) input is prompt-toolkit only anyways 2) less UI murdering
term_attrs = termios.tcgetattr(sys.stdin.fileno())
atexit.register(lambda: termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, term_attrs))
tty.setcbreak(sys.stdin.fileno())

prompt_app = None
prompt_cli = None
history = None

# Mastodon API dict pretty printers
def pprint_status(result_prefix, result, scrollback):
    content_clean = re.sub(r'<a [^>]*href="([^"]+)">[^<]*</a>', '\g<1>', result["content"])
    content_clean = html.unescape(str(re.compile(r'<.*?>').sub("", content_clean).strip()))
    
    time_formatted = datetime.datetime.strftime(result["created_at"], '%H:%M:%S')
    status_icon = glyphs[result["visibility"]]
    
    avatar = get_avatar(result["account"]["avatar_static"])

    scrollback.print(theme["ids"] + result_prefix + theme["names"] + result["account"]["acct"]  + theme["dates"] + " @ " + time_formatted, theme["visibility"] + status_icon) 
    scrollback.print(avatar + " " + theme["text"] + content_clean + " ")
    scrollback.print("")
    return

def pprint_reblog(result_prefix, result, scrollback):
    content_clean = re.sub(r'<a [^>]*href="([^"]+)">[^<]*</a>', '\g<1>', result["content"])
    content_clean = html.unescape(str(re.compile(r'<.*?>').sub("", content_clean).strip()))
    
    time_formatted = datetime.datetime.strftime(result["created_at"], '%H:%M:%S')

    avatar = get_avatar(result["account"]["avatar_static"])
    avatar_orig = get_avatar(result["reblog"]["account"]["avatar_static"])
    
    scrollback.print(theme["ids"] + result_prefix + theme["names"] + result["account"]["acct"]  + theme["dates"] + " @ " + time_formatted)
    scrollback.print(avatar + " " + theme["reblog"] + glyphs["reblog"] + " " + avatar_orig + " " + theme["names"] + result["reblog"]["account"]["acct"])  
    scrollback.print(theme["text"] + content_clean)
    scrollback.print("")
    return

def pprint_notif(result_prefix, result, scrollback):
    content_clean = re.sub(r'<a [^>]*href="([^"]+)">[^<]*</a>', '\g<1>', result["status"]["content"])
    content_clean = html.unescape(str(re.compile(r'<.*?>').sub("", content_clean).strip()))

    time_formatted = datetime.datetime.strftime(result["created_at"], '%H:%M:%S')

    avatar = get_avatar(result["account"]["avatar_static"])

    scrollback.print(theme["ids"] + result_prefix + theme["names"] + result["account"]["acct"]  + theme["dates"] + " @ " + time_formatted)
    scrollback.print(avatar + " " + theme[result["type"]] + glyphs[result["type"]] + " " + theme["text_notif"] + content_clean)
    scrollback.print("")
    return

def pprint_follow(result_prefix, result, scrollback):
    time_formatted = datetime.datetime.strftime(result["created_at"], '%H:%M:%S')

    avatar = get_avatar(result["account"]["avatar_static"])

    scrollback.print(theme["ids"] + result_prefix + " " + avatar + " " + theme["follow"] + glyphs["follow"] + " " + theme["names"] + result["account"]["acct"]  + theme["dates"] + " @ " + time_formatted)
    scrollback.print("")
    return

def pprint_result(result, scrollback, result_prefix = "", not_pretty = False):
    if isinstance(result, list):
        for num, sub_result in enumerate(reversed(result)):
            sub_result_prefix = str(len(result) - num - 1)
            pprint_result(sub_result, scrollback, sub_result_prefix, not_pretty)
        return
        
    if result_prefix != "":
        result_prefix = "#" + result_prefix.ljust(4)
        
    if isinstance(result, dict):
        if "content" in result:
            if "reblog" in result and result["reblog"] != None:
                pprint_reblog(result_prefix, result, scrollback)
            else:
                pprint_status(result_prefix, result, scrollback)
            return
        
        if "type" in result:
            if result["type"] == "mention":
                pprint_status(result_prefix, result["status"], scrollback)
                return
            
            if result["type"] in ["reblog", "favourite"]:
                pprint_notif(result_prefix, result, scrollback)
                return
            
            if result["type"] == "follow":
                pprint_follow(result_prefix, result, scrollback)
                return
            
    scrollback.print(theme["text"] + pprint.pformat(result))

# Combines two strings, trying to align one left and the other right,
# while wrapping
def align(left_part, right_part, width):
    max_spaces = max(width - (termwrap.ansilen_unicode(left_part) + termwrap.ansilen_unicode(right_part) - 1), 0)
    for i in reversed(range(max_spaces)):
        aligned = left_part + (" " * i) + right_part
        result = termwrap.wrap(aligned, width)
        if len(result) == 1:
            return result
    return termwrap.wrap(left_part + " " + right_part, width)

# Scrollback column with internal "result history" buffer
class Scrollback:
    def __init__(self, title, offset, width):
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
    
    # Do I need any redrawing?
    def needs_redraw(self):
        return self.full_redraw or self.dirty
    
    # Set buffer active or no
    def set_active(self, active):
        self.active = active
        self.full_redraw = True
        
    # Append to result history and print
    def add_result(self, result):
        self.result_counter = (self.result_counter + 1) % 1000
        if len(self.result_history) > self.result_counter:
            self.result_history[self.result_counter] = result
        else:
            self.result_history.append(result)
        pprint_result(result, self, str(self.result_counter))
        
    # Print to scrollback
    def print(self, x, right_side = None):
        new_lines = x.split("\n")
        right_side_lines = [right_side] * len(new_lines)
        self.scrollback.extend(zip(new_lines, right_side_lines))
        if len(self.scrollback) > 3000:
            self.scrollback = self.scrollback[len(self.scrollback)-3000:]
            self.wrapped_cache = self.wrapped_cache[len(new_lines):]
        self.dirty = True
        self.added = True

    # Scroll up/down
    def scroll(self, how_far):
        self.pos = self.pos + how_far
        self.dirty = True
      
    # Draw column
    def draw(self, print_height, max_width):
        # Figure out width
        print_width = min(self.width, max_width - self.offset + 1)
        if print_width < 0:
            return
        
        if self.full_redraw:
            # Invalidate the wrapping cache
            self.wrapped_cache = []
            
            # Move to start and draw header
            cursor_to(self.offset + 1, 1)
            title_style = theme["titles"]
            if self.active:
                title_style = theme["active"]
            sys.stdout.write(title_style + self.title)
            
            cursor_to(self.offset, 2)
            line_style = theme["lines"]
            if self.active:
                line_style = theme["active"]
            draw_line(line_style, print_width)
            self.full_redraw = False
            self.dirty = True
            
        # Do we need to update the actual scrollback area?
        if self.dirty == False:
            return
        self.dirty = False
        
        # If so, figure out contents
        text_width = max(print_width - 2, 0)
        if text_width == 0:
            return
        
        wrapped_lines = []
        for counter, (line, right_side) in enumerate(self.scrollback):
            if counter >= len(self.wrapped_cache):
                new_lines = []
                if right_side != None:
                    new_lines = align(line, right_side, text_width)
                else:
                    new_lines = termwrap.wrap(line, text_width)
                if len(new_lines) == 0:
                    new_lines = [""]
                wrapped_lines.extend(new_lines)
                self.wrapped_cache.append(new_lines)
            else:
                wrapped_lines.extend(self.wrapped_cache[counter])
            
        # Update scrollback position, in case it needs updating
        self.pos = max(self.pos, print_height)
        self.pos = min(self.pos, len(wrapped_lines))
        
        if self.added:
            self.pos = len(wrapped_lines)
        self.added = False
        
        # Figure out which parts to draw
        print_end = min(self.pos, len(wrapped_lines))
        print_start = max(print_end - print_height, 0)
        print_lines = wrapped_lines[print_start:print_end]
        
        # Draw scrollback area
        for line_pos, line in enumerate(print_lines):
            cursor_to(self.offset, line_pos + 3)
            clear_line(print_width + 1)
            cursor_to(self.offset + 1, line_pos + 3)            
            sys.stdout.write(line)
    
buffers = [
    Scrollback("0: home", 0, 50),
    Scrollback("1: notifications", 51, 50),
    Scrollback("2: local", 102, 50),
    Scrollback("3: scratch", 153, 5000),
]
buffer_active = len(buffers) - 1
buffers[buffer_active].set_active(True)

watched = [
]

watched_streams = [
]

# Return app title, possibly animated
title_offset = 0
title_dirty = True
def get_title():
    title_str = ""
    for index, character in enumerate("tootmage"):
        r, g, b = colorsys.hsv_to_rgb((index * 1.5 + title_offset) / 30.0, 0.8, 1.0)
        title_str = title_str + ansi_rgb(r, g, b) + character
    return title_str
    
# Update application (other than prompt line, that's prompt-toolkits job)
last_rows = 0
last_cols = 0
def screen_update_once():
    global last_rows
    global last_cols
    global title_dirty
    
    # Grab size of screen
    cols, rows = shutil.get_terminal_size()
    
    # Do we need a full redisplay? Initiate that, if so.
    if rows != last_rows or cols != last_cols:
        sys.stdout.write(ansi_clear())
        draw_prompt_separator()
        for scrollback in buffers:
            scrollback.full_redraw = True
        last_rows = rows
        last_cols = cols
    
    # Check if we have anything to draw
    need_redraw = False
    for scrollback in buffers:
        if scrollback.needs_redraw():
            need_redraw = True
    if title_dirty:
        need_redraw = True
        title_dirty = False
        
    if need_redraw:
        # Store cursor and print header
        cursor_save()
        
        # Draw title
        cursor_to(cols - len("tootmage") + 1, 0)
        sys.stdout.write(get_title() + "")
        
        # Draw buffers
        print_height = rows - 4
        for scrollback in buffers:
            scrollback.draw(print_height, cols)
        
        cursor_restore()

# Draw the little line above the prompt
def draw_prompt_separator():
    cols, rows = shutil.get_terminal_size()
    cursor_to(0, rows - 1)
    draw_line(theme["lines"], cols)

def move_cursor(new, xoff):
    cursor_to(new.x + xoff, new.y)

# Token saver
cli_tokens = None
class StoreTokens(prompt_toolkit.layout.processors.Processor):
    def apply_transformation(self, cli, document, lineno, source_to_display, tokens):
        global cli_tokens
        cli_tokens = tokens
        return prompt_toolkit.layout.processors.Transformation(tokens)
    
def app_update(context):
    global title_offset
    global title_dirty
    global watched
    while not context.input_is_ready():
        thread_names = map(lambda x: x.name, threading.enumerate())
        if "command_runner" in thread_names:
            title_offset += 2.0
            title_dirty = True
            
        for watched_expr in watched:
            funct, last_exec, exec_every, scrollback = watched_expr
            if time.time() - last_exec > exec_every:
                watched_expr[1] = time.time()
                eval_command_thread("", funct, scrollback, False)
        
        # Redraw main UI
        screen_update_once()
        
        # Redraw CLI
        if prompt_cli != None:
            # Don't want the CLI to actually draw anything
    
            # Run through the render routines so we have the tokens
            prompt_cli.renderer.reset()
            prompt_cli.renderer.render(prompt_cli, prompt_cli.layout)
            
            # Draw the tokens, manually
            cols, rows = shutil.get_terminal_size()
            
            cursor_to(0, rows)
            clear_line()
            
            cursor_to(0, rows)
            sys.stdout.write(theme["prompt"] + ">>> ")
            for token in cli_tokens:
                token_type = token[0]
                
                # Some very basic styling
                if len(token_type) > 1:
                    token_type = "Token." + ".".join(token_type[1:])                    
                token_type = str(token_type)
                    
                if not token_type in theme["prompt_toolkit_tokens"]:
                    token_type = "Default"                
                sys.stdout.write(theme["prompt_toolkit_tokens"][token_type] + token[1])
            
            # Prompt separator
            draw_prompt_separator()
            
            # Set cursor position
            cursor_to(prompt_cli.current_buffer.cursor_position + 5, rows) # TODO i-search has a broken cursor
        sys.stdout.flush()
        
        # No updating the UI outside of this function
        #sys.stdout.write = no_op_2
        
        time.sleep(0.02)

# Don't want to use prompt_toolkits layouting, lets make it so we can draw
# all the tokens ourselves!
def create_bottom_repl_application(
        completer = None, 
        history = None,
        key_bindings_registry = None,
        on_abort = prompt_toolkit.interface.AbortAction.RETRY,
        on_exit = prompt_toolkit.interface.AbortAction.RAISE_EXCEPTION,
        accept_action = prompt_toolkit.interface.AcceptAction.RETURN_DOCUMENT):

    # Create list of input processors that we need
    input_processors = [
        prompt_toolkit.layout.processors.ConditionalProcessor(
            prompt_toolkit.layout.processors.HighlightSearchProcessor(preview_search = True),
            prompt_toolkit.filters.HasFocus(prompt_toolkit.enums.SEARCH_BUFFER)
        ),
        prompt_toolkit.layout.processors.HighlightSelectionProcessor(),
        prompt_toolkit.layout.processors.ConditionalProcessor(
            prompt_toolkit.layout.processors.AppendAutoSuggestion(), 
            prompt_toolkit.filters.HasFocus(prompt_toolkit.enums.DEFAULT_BUFFER) & ~prompt_toolkit.filters.IsDone()
        ),
        prompt_toolkit.layout.prompt.DefaultPrompt(lambda cli: []),
        StoreTokens()
    ]
    
    # Create layout (essentially a dummy - we draw tokens ourselves)
    layout = prompt_toolkit.layout.Window(
        prompt_toolkit.layout.BufferControl(
            input_processors = input_processors,
            preview_search = True
        ),
        get_height= lambda cli: prompt_toolkit.layout.dimension.LayoutDimension.exact(1),
        wrap_lines = False,
    )
    
    # Create application
    return prompt_toolkit.Application(
        layout = layout,
        buffer = prompt_toolkit.buffer.Buffer(
            history = history,
            completer = completer,
            accept_action = accept_action,
            initial_document = prompt_toolkit.document.Document(''),
        ),
        key_bindings_registry = key_bindings_registry,
        on_abort = on_abort,
        on_exit = on_exit
    )

# Print prompt and read a single line
def read_line(history, key_registry):
    global prompt_app
    global prompt_cli
    cols, rows = shutil.get_terminal_size()
    cursor_to(0, rows)
    completer = MastodonFuncCompleter()     
    prompt_app = create_bottom_repl_application(
        history = history,
        key_bindings_registry = key_registry,
        completer = completer
    )
    eventloop = prompt_toolkit.shortcuts.create_eventloop(inputhook = app_update)
    prompt_cli = prompt_toolkit.CommandLineInterface(application=prompt_app, eventloop=eventloop)
    input_line = prompt_cli.run().text
    for scrollback in buffers:
        scrollback.full_redraw = True
    return(input_line)

# Command evaluator thread
last = None
def eval_command(orig_command, command, scrollback, interactive = True):
    global last
    
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
        pprint_result(print_result, scrollback)
        
    except Exception as e:
        scrollback.print(str(e))

def eval_command_thread(orig_command, command, scrollback, interactive = True):
    thread_name = "command_runner"
    if interactive == False:
        thread_name = thread_name + "_bg"
        
    exec_thread = threading.Thread(target = eval_command, name = thread_name, args = (orig_command, command, scrollback, interactive))
    exec_thread.start()

# Set up keybindings
key_registry = prompt_toolkit.key_binding.defaults.load_key_bindings_for_prompt()

# Instant tab completion
@key_registry.add_binding(prompt_toolkit.keys.Keys.ControlI)
def generate_completions(event):
    b = event.current_buffer
    if b.complete_state:
        b.complete_next()
    else:
        event.cli.start_completion(insert_common_part=True, select_first=True)
        b.complete_next()

# Accept, but without newline echo
@key_registry.add_binding(prompt_toolkit.keys.Keys.Enter)
def read_line_accept(args):
    cursor_save()
    cursor_to(0, 0)
    prompt_cli._set_return_callable(lambda: prompt_app.buffer.document)
    cursor_restore()
    history.append(prompt_app.buffer.document.text)
    tty.setcbreak(sys.stdin.fileno()) # Be paranoid about STAYING in cbreak mode
    
# Clear Ctrl-L (clear-screen)
@key_registry.add_binding(prompt_toolkit.keys.Keys.ControlL)
def do_nothing(args):
    pass

# Increase scrollback position
@key_registry.add_binding(prompt_toolkit.keys.Keys.PageDown)
def scroll_up(args, how_far = 2):
    buffers[buffer_active].scroll(2)
    

# Reduce scrollback position
@key_registry.add_binding(prompt_toolkit.keys.Keys.PageUp)
def scroll_down(args, how_far = 2):
    buffers[buffer_active].scroll(-2)

# Next buffer
@key_registry.add_binding(prompt_toolkit.keys.Keys.Escape, prompt_toolkit.keys.Keys.Down)
@key_registry.add_binding(prompt_toolkit.keys.Keys.ControlPageDown)
@key_registry.add_binding(prompt_toolkit.keys.Keys.ControlRight)
def next_buffer(args):
    global buffer_active
    buffer_new = buffer_active + 1
    if buffer_new >= len(buffers):
        buffer_new -= len(buffers)
    buffers[buffer_active].set_active(False)
    buffers[buffer_new].set_active(True)        
    buffer_active = buffer_new

# Previous buffer
@key_registry.add_binding(prompt_toolkit.keys.Keys.Escape, prompt_toolkit.keys.Keys.Up)
@key_registry.add_binding(prompt_toolkit.keys.Keys.ControlPageUp)
@key_registry.add_binding(prompt_toolkit.keys.Keys.ControlLeft)
def next_buffer(args):
    global buffer_active
    buffer_new = buffer_active - 1
    if buffer_new < 0:
        buffer_new += len(buffers)
    buffers[buffer_active].set_active(False)
    buffers[buffer_new].set_active(True)
    buffer_active = buffer_new

# Function that adds a watcher
def watch(function, scrollback, every_s):
    watched.append([function, 0, every_s, scrollback])

# Class that just calls a callback for stream events
class EventCollector(StreamListener):
    def __init__(self, event_handler = None, notification_event_handler = None):
        super(EventCollector, self).__init__()
        self.event_handler = event_handler
        self.notification_event_handler = notification_event_handler
        
    def on_update(self, status):
        if self.event_handler != None:
            self.event_handler(status)
            
    def on_notification(self, notification):
        if self.notification_event_handler != None:
            self.notification_event_handler(notification)
        
# Watcher that watches a stream
def watch_stream(function, scrollback = None, scrollback_notifications = None, initial_fill = None, initial_fill_notifications = None):
    def watch_stream_internal(function, scrollback = None, scrollback_notifications = None, initial_fill = None, initial_fill_notifications = None):
        event_handler = None
        if scrollback != None:
            event_handler = scrollback.add_result
            if initial_fill != None:
                initial_data = initial_fill()
                for result in initial_data:
                    event_handler(result)
                
        notification_event_handler = None
        if scrollback_notifications != None:
            notification_event_handler = scrollback_notifications.add_result
            if initial_fill != None:
                initial_data = initial_fill_notifications()
                for result in initial_data:
                    notification_event_handler(result)
                
        result_collector = EventCollector(event_handler, notification_event_handler)
        watched_streams.append(function(result_collector, async = True))
        
    watch_start_thread = threading.Thread(target = watch_stream_internal, name = "start_watch", args = (function, scrollback, scrollback_notifications, initial_fill, initial_fill_notifications))
    watch_start_thread.start()
    
# Preamble: Create mastodon object
MASTODON_BASE_URL = "https://icosahedron.website"
m = Mastodon(client_id = 'halcy_client.secret', access_token = 'halcy_user.secret', api_base_url = MASTODON_BASE_URL)

def prefix_val(name):
        val = 0
        if not '_' in name:
            val -= 100000
        
        if name.startswith('toot'):
            val -= 10000
        
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

def suffix_key(name):
    if "_" in name:
        return name[name.rfind("_") + 1:]
    return name

def combined_key(name):
    return(suffix_key(name.text), prefix_val(name.text))

def get_func_names():
    funcs = dir(Mastodon)
    funcs = list(filter(lambda x: not x.startswith("_"), funcs))
    funcs = list(filter(lambda x: not x.endswith("_version"), funcs))    
    funcs = list(filter(lambda x: not "stream_" in x, funcs))
    funcs = list(filter(lambda x: not "fetch_" in x, funcs))
    funcs = list(filter(lambda x: not "create_app" in x, funcs))
    funcs = list(filter(lambda x: not "create_app" in x, funcs))
    funcs = list(filter(lambda x: not "auth_request_url" in x, funcs)) 
    return sorted(funcs, key = prefix_val)

class MastodonFuncCompleter(prompt_toolkit.completion.Completer):
    def __init__(self):
        self.base_completer = prompt_toolkit.contrib.completers.WordCompleter(get_func_names(), ignore_case = True, match_middle = True)
    
    def get_completions(self, document, complete_event):
        base_completions = list(self.base_completer.get_completions(document, complete_event))
        base_completions = sorted(base_completions, key = combined_key)
        
        best_matches = []
        good_matches = []
        match_text = document.get_word_before_cursor(WORD=False)
        for match in base_completions:
            if suffix_key(match.text).startswith(match_text):
                best_matches.append(match)
            else:
                good_matches.append(match)
        return(best_matches + good_matches)

# Column contents
#watch(m.timeline, buffers[0]], 60)
#watch(m.notifications, buffers[1], 60)
#watch(m.timeline_local, buffers[2], 60)
watch_stream(m.stream_user, buffers[0], buffers[1], m.timeline, m.notifications)
watch_stream(m.stream_local, buffers[2], initial_fill = m.timeline_local)
    
theme = {
    "text": ansi_reset() + ansi_rgb(1.0, 1.0, 1.0),
    "text_notif": ansi_reset() + ansi_rgb(0.5, 0.5, 0.5),
    "ids": ansi_rgb(255.0 / 255.0, 0.0 / 255.0, 128.0 / 255.0),
    "dates": ansi_rgb(0.0 / 255.0, 255.0 / 255.0, 255.0 / 255.0),
    "names": ansi_rgb(1.0, 1.0, 0.5),
    "lines": ansi_rgb(255.0 / 255.0, 0.0 / 255.0, 128.0 / 255.0),
    "titles": ansi_rgb(1.0, 1.0, 1.0),
    "prompt": ansi_rgb(0.0 / 255.0, 255.0 / 255.0, 255.0 / 255.0),
    "prompt_toolkit_tokens": {
        "Default": ansi_rgb(1.0, 1.0, 1.0),
        "Token.Search": ansi_rgb(1.0, 1.0, 0.5),
        "Token.Search.Text": ansi_rgb(255.0 / 255.0, 0.0 / 255.0, 128.0 / 255.0),
        "Token.SearchMatch.Current": ansi_rgb(255.0 / 255.0, 0.0 / 255.0, 128.0 / 255.0),
        "Token.AutoSuggestion": ansi_rgb(255.0 / 255.0, 0.0 / 255.0, 128.0 / 255.0),
    },
    "active": ansi_rgb(0.0 / 255.0, 255.0 / 255.0, 255.0 / 255.0),
    "reblog": ansi_rgb(128.0 / 255.0, 255.0 / 255.0, 0.0 / 255.0),
    "follow": ansi_rgb(128.0 / 255.0, 128.0 / 255.0, 255.0 / 255.0),
    "favourite": ansi_rgb(128.0 / 255.0, 255.0 / 255.0, 128.0 / 255.0),
    "visibility": ansi_rgb(128.0 / 255.0, 255.0 / 255.0, 0.0 / 255.0),
}

glyphs = {
    'reblog': '\U0000267a', # recycling symbol
    'favourite': '\U00002605', # star
    'follow': '➜', # arrow
    'public': '\U0001f30e', # globe
    'unlisted': '\U0001f47b', # ghost
    'private': '\U0001f512', # lock
    'direct': '\U0001f4e7', # envelope
}

# Start up and run REPL
def run_app():    
    # Set stuff up
    clear_screen()
    cols, rows = shutil.get_terminal_size()
    
    global history
    history = prompt_toolkit.history.FileHistory(".tootmage_history")
    
    # REPL
    while True:
        orig_command = read_line(history, key_registry)
        command = orig_command
        
        if len(command.strip()) == 0:
            continue
        
        # Starts with semicolon -> python command
        if command[0] == ";":
            command = command[1:]
        else:
            # Starts with # or . -> buffer ref
            if not command[0] in "#.": # TODO make these configurable
                command = "m." + command
            else:
                pass
                #dot_position = command.find(".")
                #if dot_position != -1: # TODO make this good
                #    command = "m" + command[dot_position:] + "(" + command[:dot_position] + ")"
                
        command = re.sub(r'#([0-9]+)', r'last[\1]', command)
        command = re.sub(r'#', r'last', command)
        command = re.sub(r'\.([0-9]+).([0-9]+)', r'buffers[\1].result_history[\2]', command)
        
        if command.find("=") == -1:
            command = "__thread_res = (" + command + ")"
        
        eval_command_thread(orig_command, command, buffers[-1])

run_app()
