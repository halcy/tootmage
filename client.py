from mastodon import Mastodon, StreamListener

import re
import time
import datetime
import html
import pprint
import sys
import shutil
import ansiwrap
import prompt_toolkit
import threading
import colorsys

# Mastodon API dict pretty printers
def pprint_status(result_prefix, result, scrollback):
    content_clean = re.sub(r'<a [^>]*href="([^"]+)">[^<]*</a>', '\g<1>', result["content"])
    content_clean = html.unescape(str(re.compile(r'<.*?>').sub("", content_clean).strip()))
    
    time_formatted = datetime.datetime.strftime(result["created_at"], '%H:%M:%S')
    status_icon = glyphs[result["visibility"]]
    
    scrollback.print(theme["ids"] + result_prefix + theme["names"] + result["account"]["acct"]  + theme["dates"] + " @ " + time_formatted)  
    scrollback.print("<#RIGHT#>" + theme["visibility"] + status_icon)    
    scrollback.print(theme["text"] + content_clean + " ")
    scrollback.print("<#NEW_LINE#>")
    return

def pprint_reblog(result_prefix, result, scrollback):
    content_clean = re.sub(r'<a [^>]*href="([^"]+)">[^<]*</a>', '\g<1>', result["content"])
    content_clean = html.unescape(str(re.compile(r'<.*?>').sub("", content_clean).strip()))
    
    time_formatted = datetime.datetime.strftime(result["created_at"], '%H:%M:%S')

    scrollback.print(theme["ids"] + result_prefix + theme["names"] + result["account"]["acct"]  + theme["dates"] + " @ " + time_formatted)
    scrollback.print("   " + theme["reblog"] + glyphs["reblog"] + " " + theme["names"] + result["reblog"]["account"]["acct"])  
    scrollback.print(theme["text"] + content_clean)
    scrollback.print("<#NEW_LINE#>")
    return

def pprint_notif(result_prefix, result, scrollback):
    content_clean = re.sub(r'<a [^>]*href="([^"]+)">[^<]*</a>', '\g<1>', result["status"]["content"])
    content_clean = html.unescape(str(re.compile(r'<.*?>').sub("", content_clean).strip()))

    time_formatted = datetime.datetime.strftime(result["created_at"], '%H:%M:%S')

    scrollback.print(theme["ids"] + result_prefix + theme["names"] + result["account"]["acct"]  + theme["dates"] + " @ " + time_formatted)
    scrollback.print("   " + theme[result["type"]] + glyphs[result["type"]] + " " + theme["text"] + content_clean)
    scrollback.print("<#NEW_LINE#>")
    return

def pprint_follow(result_prefix, result, scrollback):
    time_formatted = datetime.datetime.strftime(result["created_at"], '%H:%M:%S')

    scrollback.print(theme["ids"] + result_prefix + theme["follow"] + glyphs["follow"] + " " + theme["names"] + result["account"]["acct"]  + theme["dates"] + " @ " + time_formatted)
    scrollback.print("<#NEW_LINE#>")
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
    for i in reversed(range(width)):
        aligned = left_part + (" " * i) + right_part
        result = ansiwrap.wrap(aligned, width)
        if len(result) == 1:
            return result
    return ansiwrap.wrap(left_part + " " + right_part)

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
        
    # Append to result history and print
    def add_result(self, result):
        self.result_counter = (self.result_counter + 1) % 1000
        if len(self.result_history) > self.result_counter:
            self.result_history[self.result_counter] = result
        else:
            self.result_history.append(result)
        pprint_result(result, self, str(self.result_counter))
        
    # Print to scrollback
    def print(self, x):
        self.scrollback.extend(x.split("\n"))
        if len(self.scrollback) > 3000:
            self.scrollback = self.scrollback[len(self.scrollback)-3000:]
        self.dirty = True
        self.added = True

    # Scroll up/down
    def scroll(self, how_far):
        self.pos = self.pos + how_far
        self.dirty = True
      
    # Draw column
    def draw(self, print_height, max_width):
        # Figure out width
        print_width = min(self.width, max_width - self.offset)
        if print_width < 0:
            return
        
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
        if print_width < self.width:
            draw_line(line_style, print_width + 1)
        else:
            draw_line(line_style, print_width)
            
        # Do we need to update the actual scrollback area?
        if self.dirty == False:
            return
        self.dirty = False
        
        # If so, figure out contents
        text_width = max(print_width - 2, 0)
        if text_width == 0:
            return
        
        wrapped_lines = []
        for line in self.scrollback:
            if line.startswith("<#RIGHT#>"):
                line = line[9:]
                left_part = wrapped_lines.pop()
                wrapped_lines.extend(align(left_part, line, text_width))
            else:
                lines = ansiwrap.wrap(line, text_width)
                wrapped_lines.extend(lines)
        
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
            clear_line(print_width)
            cursor_to(self.offset + 1, line_pos + 3)
            if line == "<#NEW_LINE#>":
                sys.stdout.write("")
            else:
                sys.stdout.write(line)

buffers = [
    Scrollback("home", 0, 50),
    Scrollback("notifications", 51, 50),
    Scrollback("local", 102, 50),
    Scrollback("scratch", 153, 10000),
]
buffers[2].active = True

watched = [
]

watched_streams = [
]

# Return app title, possibly animated
title_offset = 0
def get_title():
    title_str = ""
    for index, character in enumerate("tootmage"):
        r, g, b = colorsys.hsv_to_rgb((index + title_offset) / 30.0, 1.0, 1.0)
        title_str = title_str + ansi_rgb(r, g, b) + character
    return title_str

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
    sys.stdout.flush()

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
    
# Update application (other than prompt line, that's prompt-toolkits job)
last_rows = 0
last_cols = 0
def screen_update_once():
    global last_rows
    global last_cols
    
    # Grab size of screen
    cols, rows = shutil.get_terminal_size()
    
    # Store cursor and print header
    cursor_save()
    
    # Do we need a full redisplay? Initiate that, if so.
    if rows != last_rows or cols != last_cols:
        sys.stdout.write(ansi_clear())
        draw_prompt_separator()
        for scrollback in buffers:
            scrollback.dirty = True
        last_rows = rows
        last_cols = cols
        
    # Draw title
    cursor_to(cols - len("tootmage") + 1, 0)
    sys.stdout.write(get_title() + "\n")
    
    # Draw buffers
    print_height = rows - 4
    for scrollback in buffers:
        scrollback.draw(print_height, cols)
    
    cursor_restore()
    sys.stdout.flush()

# Draw the little line above the prompt
def draw_prompt_separator():
    cols, rows = shutil.get_terminal_size()
    cursor_to(0, rows - 1)
    draw_line(theme["lines"], cols)
    cursor_to(0, rows)
    clear_line()

# Draw/Update loop
def app_update(context):
    global title_offset
    global watched
    while not context.input_is_ready():
        thread_names = map(lambda x: x.name, threading.enumerate())
        if "command_runner" in thread_names:
            title_offset += 0.3
        
        for watched_expr in watched:
            funct, last_exec, exec_every, scrollback = watched_expr
            if time.time() - last_exec > exec_every:
                watched_expr[1] = time.time()
                eval_command_thread("", funct, scrollback, False)
                
        screen_update_once()        
        time.sleep(0.01)

# Print prompt and read a single line
def read_line(history, key_registry):
    cursor_reset()
    draw_prompt_separator()
    sys.stdout.write(theme["prompt"]) # TODO FIXME
    input_line = prompt_toolkit.prompt(
        ">>> ", 
        wrap_lines = False,
        eventloop = prompt_toolkit.shortcuts.create_eventloop(inputhook = app_update),
        history = history,
        key_bindings_registry = key_registry,
        true_color=True
    )
    sys.stdout.write('\033[1T')
    screen_update_once()
    sys.stdout.flush()
    return(input_line)

# Command evaluator thread
last = None
def eval_command(orig_command, command, scrollback, interactive = True):
    global last
    
    if interactive:
        scrollback.print("<#NEW_LINE#>")
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

# Clear Ctrl-L (clear-screen)
@key_registry.add_binding(prompt_toolkit.keys.Keys.ControlL)
def do_nothing(args):
    pass

# Increase scrollback position
@key_registry.add_binding(prompt_toolkit.keys.Keys.PageDown)
def scroll_up(args, how_far = 2):
    buffers[-1].scroll(2)
    

# Reduce scrollback position
@key_registry.add_binding(prompt_toolkit.keys.Keys.PageUp)
def scroll_down(args, how_far = 2):
    buffers[-1].scroll(-2)


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
def watch_stream(function, scrollback = None, scrollback_notifications = None): # TODO call this in a thread
    def watch_stream_internal(function, scrollback = None, scrollback_notifications = None):
        event_handler = None
        if scrollback != None:
            event_handler = scrollback.add_result
        
        notification_event_handler = None
        if scrollback_notifications != None:
            notification_event_handler = scrollback_notifications.add_result
            
        result_collector = EventCollector(event_handler, notification_event_handler)
        watched_streams.append(function(result_collector, async = True))
        
    watch_start_thread = threading.Thread(target = watch_stream_internal, name = "start_watch", args = (function, scrollback, scrollback_notifications))
    watch_start_thread.start()
    
# Preamble: Create mastodon object
MASTODON_BASE_URL = "https://icosahedron.website"
m = Mastodon(client_id = 'halcy_client.secret', access_token = 'halcy_user.secret', api_base_url = MASTODON_BASE_URL)

# Column contents
#watch(m.timeline, buffers[0]], 60)
#watch(m.notifications, buffers[1], 60)
#watch(m.timeline_local, buffers[2], 60)
watch_stream(m.stream_user, buffers[0], buffers[1])
watch_stream(m.stream_local, buffers[2])
    
theme = {
    "text": ansi_reset() + ansi_rgb(1.0, 1.0, 1.0),
    "ids": ansi_rgb(255.0 / 255.0, 0.0 / 255.0, 128.0 / 255.0),
    "dates": ansi_rgb(0.0 / 255.0, 255.0 / 255.0, 255.0 / 255.0),
    "names": ansi_rgb(1.0, 1.0, 0.5),
    "lines": ansi_rgb(255.0 / 255.0, 0.0 / 255.0, 128.0 / 255.0),
    "titles": ansi_rgb(1.0, 1.0, 1.0),
    "prompt": ansi_rgb(0.0 / 255.0, 255.0 / 255.0, 255.0 / 255.0),
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
clear_screen()
cols, rows = shutil.get_terminal_size()
cursor_to(0, rows)
history = prompt_toolkit.history.FileHistory(".tootmage_history")

while True:
    orig_command = read_line(history, key_registry)
    command = orig_command
    
    if len(command.strip()) == 0:
        continue
    
    if command[0] == "#":
        dot_position = command.find(".")
        if dot_position != -1:
            command = "m" + command[dot_position:] + "(" + command[:dot_position] + ")"
    else:
        if command[0] == ".":
            command = command[1:]
        else:
            command = "m." + command
            
    command = re.sub(r'#([0-9]+)', r'last[\1]', command)
    command = re.sub(r'#', r'last', command)
    
    if command.find("=") == -1:
        command = "__thread_res = (" + command + ")"
    
    eval_command_thread(orig_command, command, buffers[-1])