import os
import subprocess

# Load theme
exec(open("./themes/datawitch.py").read())
#exec(open("./themes/helvetica_standard.py").read())

# Create mastodon object
ensure_app_config("tootmage_url.secret", "tootmage_client.secret", "tootmage_user.secret")
MASTODON_BASE_URL = ""
with open("tootmage_url.secret", "r") as f:
    MASTODON_BASE_URL = f.read()
m = Mastodon(client_id = 'tootmage_client.secret', access_token = 'tootmage_user.secret', api_base_url = MASTODON_BASE_URL)
m._acct = m.account_verify_credentials()["acct"]

# Columns
buffers = [
    Scrollback("0: home", 0, 50),
    Scrollback("1: notifications", 51, 50),
    Scrollback("2: local", 102, 50),
    Scrollback("3: scratch", 153, 5000),
]
buffer_active = len(buffers) - 1
buffers[buffer_active].set_active(True)

# Column contents
watch_stream(m.stream_user, buffers[0], buffers[1], m.timeline, m.notifications)
watch_stream(m.stream_local, buffers[2], initial_fill = m.timeline_local)

# Viewing and notifications
def open_browser(url):
    subprocess.call(["firefox", url])

def dbus_notify(user, text):
    subprocess.call([os.path.dirname(os.path.realpath(__file__)) + "/notify.sh", user, text])
    
view_command = open_browser
notify_command = dbus_notify