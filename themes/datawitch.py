# datawitch theme for tootmage. uses rgb ansi as well as unicode icons.
theme_col_mode = "rgb"

theme = {
    "text": ansi_reset() + ansi_rgb(1.0, 1.0, 1.0),
    "text_notif": ansi_reset() + ansi_rgb(0.5, 0.5, 0.5),
    "ids": ansi_rgb(255.0 / 255.0, 0.0 / 255.0, 128.0 / 255.0),
    "dates": ansi_rgb(0.0 / 255.0, 255.0 / 255.0, 255.0 / 255.0),
    "names": ansi_rgb(1.0, 1.0, 0.5),
    "url_nums": ansi_rgb(0.7, 0.3, 0.7),
    "names_inline": ansi_rgb(0.7, 1.0, 0.7),
    "names_notif": ansi_rgb(0.4, 0.5, 0.4), 
    "cw": ansi_rgb(0.5, 1.0, 0.5),
    "cw_notif": ansi_rgb(0.4, 0.5, 0.4),
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
    'line': "═",
    'avatar': "█",
    'image': '\U0001f5bc',
    'video': '\U0001f3a5',
    'audio': '\U0001f3b5',
    'gifv': '\U0001f3a5',
}