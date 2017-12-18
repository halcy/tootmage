# Load theme
exec(open("./themes/datawitch.py").read())

# Create mastodon object
MASTODON_BASE_URL = "https://icosahedron.website"
m = Mastodon(client_id = 'halcy_client.secret', access_token = 'halcy_user.secret', api_base_url = MASTODON_BASE_URL)
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
#watch(m.timeline, buffers[0]], 60)
#watch(m.notifications, buffers[1], 60)
#watch(m.timeline_local, buffers[2], 60)
watch_stream(m.stream_user, buffers[0], buffers[1], m.timeline, m.notifications)
watch_stream(m.stream_local, buffers[2], initial_fill = m.timeline_local)

# Viewing
view_command = ["firefox", "{}"]
view_command_media = ["firefox", "{}"]