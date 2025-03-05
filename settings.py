import os
import subprocess
import webbrowser

# Load theme
exec(open("./themes/datawitch.py", 'rb').read().decode("utf-8"))
# exec(open("./themes/helvetica_standard.py", 'rb').read().decode("utf-8"))

# Create mastodon object
ensure_app_config("tootmage_url.secret", "tootmage_client.secret", "tootmage_user.secret") # Logs in if necessary
MASTODON_BASE_URL = ""
with open("tootmage_url.secret", "r") as f:
    MASTODON_BASE_URL = f.read()
m = Mastodon(client_id = 'tootmage_client.secret', access_token = 'tootmage_user.secret', api_base_url = MASTODON_BASE_URL)
m._acct = m.account_verify_credentials()["acct"]

# Set up columns
buffers = [
    Scrollback("0: home", 0, 50),
    Scrollback("1: notifications", 51, 50),
    Scrollback("2: local", 102, 50),
    Scrollback("3: scratch", 153, 5000),
]
buffer_active = len(buffers) - 1
buffers[buffer_active].set_active(True)

# Set up column contents, either via watching a function every X seconds, or by watching a stream
#watch(m.timeline, buffers[0]], 60)
#watch(m.notifications, buffers[1], 60)
#watch(m.timeline_local, buffers[2], 60)
watch_stream(m.stream_user, buffers[0], buffers[1], m.timeline, m.notifications)
watch_stream(m.stream_local, buffers[2], initial_fill = m.timeline_local)

# Viewing and notifications
def open_browser(url):
    # Open a specific browser, or whatever else you like
    # subprocess.call(["firefox", url])

    # Open the default browser
    webbrowser.open(url)

# notify.sh calls dbus to send a notification and plays a beep
def dbus_notify(user, text):
    subprocess.call([os.path.dirname(os.path.realpath(__file__)) + "/notify.sh", user, text])
    
# Windows notification    
def windows_notify(user, text):
    from win10toast import ToastNotifier
    toast = ToastNotifier()
    toast.show_toast(
        user,
        text,
        duration = 5,
        threaded = True,
    )

# Just no notification
def no_notify(user, text):
    pass

view_command = open_browser
notify_command = no_notify
