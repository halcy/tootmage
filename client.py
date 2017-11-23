from mastodon import Mastodon
from colored import fg, bg, attr

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

# Mastodon API dict pretty printer
def pprint_result(result, scrollback, result_prefix = ""):
    if isinstance(result, list):
        for num, sub_result in enumerate(reversed(result)):
            
            sub_result_prefix = result_prefix
            if result_prefix != "":
                sub_result_prefix += "-"
            sub_result_prefix += str(len(result) - num - 1)
            
            pprint_result(sub_result, scrollback, sub_result_prefix)
        return
        
        
    if result_prefix != "":
        result_prefix = "#" + result_prefix.ljust(4)
        
    if isinstance(result, dict):
        if "content" in result:
            content_clean = re.sub(r'<a [^>]*href="([^"]+)">[^<]*</a>', '\g<1>', result["content"])
            content_clean = html.unescape(str(re.compile(r'<.*?>').sub("", content_clean).strip()))
            
            time_formatted = datetime.datetime.strftime(result["created_at"], '%H:%M:%S')

            scrollback.print(fg('green') + result_prefix + fg('yellow') + result["account"]["acct"]  + " @ " + fg('red') + time_formatted)
            scrollback.print(content_clean)
            scrollback.print("<#NEW_LINE#>")
            return
        
    scrollback.print(pprint.pformat(result))

# Scrollback column
class Scrollback:
    def __init__(self, title, offset, width):
        self.scrollback = []
        self.dirty = True
        self.pos = 0
        self.added = False
        self.title = title
        self.offset = offset + 1
        self.width = width

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
        sys.stdout.write(self.title)
        
        cursor_to(self.offset, 2)
        if print_width < self.width:
            draw_line(print_width + 1)
        else:
            draw_line(print_width)
            
        # Do we need to update the actual scrollback area?
        if self.dirty == False:
            return
        self.dirty = False
        
        # If so, figure out contents
        wrapped_lines = []
        for line in self.scrollback:
            lines = ansiwrap.wrap(line, print_width)
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

watched = [
]

# Return app title, possibly animated
title_offset = 0
def get_title():
    title_str = ""
    for index, character in enumerate("tootmage"):
        r, g, b = colorsys.hsv_to_rgb((index + title_offset) / 30.0, 1.0, 1.0)
        title_str = title_str + rgb(r, g, b) + character
    return title_str + attr('reset')

# ANSI escape and other output convenience functions
def rgb(r, g, b):
    r = int(round(r * 255.0))
    g = int(round(g * 255.0))
    b = int(round(b * 255.0))
    return "\33[38;2;{};{};{}m".format(str(r), str(g), str(b))

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

def draw_line(line_len):
    sys.stdout.write("═" * line_len)
    
# Update application (other than prompt line, that's prompt-toolkits job)
def screen_update_once():
    # Grab size of screen
    cols, rows = shutil.get_terminal_size()
    
    # Store cursor and print header
    cursor_save()
    cursor_to(cols - len("tootmage") + 1, 0)
    sys.stdout.write(get_title() + "\n")
    
    print_height = rows - 4
    for scrollback in buffers:
        scrollback.draw(print_height, cols)
    
    cursor_restore()
    sys.stdout.flush()

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
    
    cols, rows = shutil.get_terminal_size()
    cursor_to(0, rows - 1)
    draw_line(cols)
    cursor_to(0, rows)
    clear_line()
    input_line = prompt_toolkit.prompt(
        ">>> ", 
        wrap_lines = False,
        eventloop = prompt_toolkit.shortcuts.create_eventloop(inputhook = app_update),
        history = history,
        key_bindings_registry = key_registry
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
        scrollback.print("> " + orig_command)
        
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


# Preamble: Create mastodon object
MASTODON_BASE_URL = "https://icosahedron.website"
m = Mastodon(client_id = 'halcy_client.secret', access_token = 'halcy_user.secret', api_base_url = MASTODON_BASE_URL)

# Column contents
watched.append([m.timeline, 0, 20, buffers[0]])
watched.append([m.notifications, 0, 20, buffers[1]])
watched.append([m.timeline_local, 0, 20, buffers[2]])

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
