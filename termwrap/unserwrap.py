# From the python core library, modified to handle ANSI escapes and double width characters
# correctly

# Copyright (C) 1999-2001 Gregory P. Ward.
# Copyright (C) 2002, 2003 Python Software Foundation.
# Written by Greg Ward <gward@python.net>
# Inlcuded here so we can patch the len function

import re

__all__ = ['TextWrapper', 'wrap', 'fill', 'dedent', 'indent', 'shorten']

# Hardcode the recognized whitespace characters to the US-ASCII
# whitespace characters.  The main reason for doing this is that
# some Unicode spaces (like \u00a0) are non-breaking whitespaces.
_whitespace = '\t\n\x0b\x0c\r '
import wcwidth
import unicodedata
from .ansistate import ANSIState

ANSIRE = re.compile('\x1b\\[(K|.*?m)')

def ansilen_unicode(s):
    s_without_ansi = unicodedata.normalize('NFC', ANSIRE.sub('', s))
    s_without_ansi = s_without_ansi.replace("\n", "_")
    return wcwidth.wcswidth(s_without_ansi)

class OurTextWrapper:
    """
    Object for wrapping/filling text.  The public interface consists of
    the wrap() and fill() methods; the other methods are just there for
    subclasses to override in order to tweak the default behaviour.
    If you want to completely replace the main wrapping algorithm,
    you'll probably have to override _wrap_chunks().

    Several instance attributes control various aspects of wrapping:
      width (default: 70)
        the maximum width of wrapped lines (unless break_long_words
        is false)
      initial_indent (default: "")
        string that will be prepended to the first line of wrapped
        output.  Counts towards the line's width.
      subsequent_indent (default: "")
        string that will be prepended to all lines save the first
        of wrapped output; also counts towards each line's width.
      expand_tabs (default: true)
        Expand tabs in input text to spaces before further processing.
        Each tab will become 0 .. 'tabsize' spaces, depending on its position
        in its line.  If false, each tab is treated as a single character.
      tabsize (default: 8)
        Expand tabs in input text to 0 .. 'tabsize' spaces, unless
        'expand_tabs' is false.
      replace_whitespace (default: true)
        Replace all whitespace characters in the input text by spaces
        after tab expansion.  Note that if expand_tabs is false and
        replace_whitespace is true, every tab will be converted to a
        single space!
      fix_sentence_endings (default: false)
        Ensure that sentence-ending punctuation is always followed
        by two spaces.  Off by default because the algorithm is
        (unavoidably) imperfect.
      break_long_words (default: true)
        Break words longer than 'width'.  If false, those words will not
        be broken, and some lines might be longer than 'width'.
      break_on_hyphens (default: true)
        Allow breaking hyphenated words. If true, wrapping will occur
        preferably on whitespaces and right after hyphens part of
        compound words.
      drop_whitespace (default: true)
        Drop leading and trailing whitespace from lines.
      max_lines (default: None)
        Truncate wrapped lines.
      placeholder (default: ' [...]')
        Append to the last line of truncated text.
    """

    unicode_whitespace_trans = dict.fromkeys(map(ord, _whitespace), ord(' '))

    # This funky little regex is just the trick for splitting
    # text up into word-wrappable chunks.  E.g.
    #   "Hello there -- you goof-ball, use the -b option!"
    # splits into
    #   Hello/ /there/ /--/ /you/ /goof-/ball,/ /use/ /the/ /-b/ /option!
    # (after stripping out empty strings).
    word_punct = r'[\w!"\'&.,?]'
    letter = r'[^\d\W]'
    whitespace = r'[%s]' % re.escape(_whitespace)
    nowhitespace = '[^' + whitespace[1:]
    wordsep_re = re.compile(r'''
        ( # any whitespace
          %(ws)s+
        | # em-dash between words
          (?<=%(wp)s) -{2,} (?=\w)
        | # word, possibly hyphenated
          %(nws)s+? (?:
            # hyphenated word
              -(?: (?<=%(lt)s{2}-) | (?<=%(lt)s-%(lt)s-))
              (?= %(lt)s -? %(lt)s)
            | # end of word
              (?=%(ws)s|\Z)
            | # em-dash
              (?<=%(wp)s) (?=-{2,}\w)
            )
        )''' % {'wp': word_punct, 'lt': letter,
                'ws': whitespace, 'nws': nowhitespace},
        re.VERBOSE)
    del word_punct, letter, nowhitespace

    # This less funky little regex just split on recognized spaces. E.g.
    #   "Hello there -- you goof-ball, use the -b option!"
    # splits into
    #   Hello/ /there/ /--/ /you/ /goof-ball,/ /use/ /the/ /-b/ /option!/
    wordsep_simple_re = re.compile(r'(%s+)' % whitespace)
    del whitespace

    # XXX this is not locale- or charset-aware -- string.lowercase
    # is US-ASCII only (and therefore English-only)
    sentence_end_re = re.compile(r'[a-z]'             # lowercase letter
                                 r'[\.\!\?]'          # sentence-ending punct.
                                 r'[\"\']?'           # optional end-of-quote
                                 r'\Z')               # end of chunk

    def __init__(self,
                 width=70,
                 initial_indent="",
                 subsequent_indent="",
                 expand_tabs=True,
                 replace_whitespace=True,
                 fix_sentence_endings=False,
                 break_long_words=True,
                 drop_whitespace=True,
                 break_on_hyphens=True,
                 tabsize=8,
                 *,
                 max_lines=None,
                 placeholder=' [...]'):
        self.width = width
        self.initial_indent = initial_indent
        self.subsequent_indent = subsequent_indent
        self.expand_tabs = expand_tabs
        self.replace_whitespace = replace_whitespace
        self.fix_sentence_endings = fix_sentence_endings
        self.break_long_words = break_long_words
        self.drop_whitespace = drop_whitespace
        self.break_on_hyphens = break_on_hyphens
        self.tabsize = tabsize
        self.max_lines = max_lines
        self.placeholder = placeholder


    # -- Private methods -----------------------------------------------
    # (possibly useful for subclasses to override)

    def _munge_whitespace(self, text):
        """_munge_whitespace(text : string) -> string

        Munge whitespace in text: expand tabs and convert all other
        whitespace characters to spaces.  Eg. " foo\\tbar\\n\\nbaz"
        becomes " foo    bar  baz".
        """
        if self.expand_tabs:
            text = text.expandtabs(self.tabsize)
        if self.replace_whitespace:
            text = text.translate(self.unicode_whitespace_trans)
        return text


    def _split(self, text):
        """_split(text : string) -> [string]

        Split the text to wrap into indivisible chunks.  Chunks are
        not quite the same as words; see _wrap_chunks() for full
        details.  As an example, the text
          Look, goof-ball -- use the -b option!
        breaks into the following chunks:
          'Look,', ' ', 'goof-', 'ball', ' ', '--', ' ',
          'use', ' ', 'the', ' ', '-b', ' ', 'option!'
        if break_on_hyphens is True, or in:
          'Look,', ' ', 'goof-ball', ' ', '--', ' ',
          'use', ' ', 'the', ' ', '-b', ' ', option!'
        otherwise.
        """
        if self.break_on_hyphens is True:
            chunks = self.wordsep_re.split(text)
        else:
            chunks = self.wordsep_simple_re.split(text)
        chunks = [c for c in chunks if c]
        return chunks

    def _fix_sentence_endings(self, chunks):
        """_fix_sentence_endings(chunks : [string])

        Correct for sentence endings buried in 'chunks'.  Eg. when the
        original text contains "... foo.\\nBar ...", munge_whitespace()
        and split() will convert that to [..., "foo.", " ", "Bar", ...]
        which has one too few spaces; this method simply changes the one
        space to two.
        """
        i = 0
        patsearch = self.sentence_end_re.search
        while i < len(chunks)-1:
            if chunks[i+1] == " " and patsearch(chunks[i]):
                chunks[i+1] = "  "
                i += 2
            else:
                i += 1

    def _handle_long_word(self, reversed_chunks, cur_line, cur_len, width):
        """_handle_long_word(chunks : [string],
                             cur_line : [string],
                             cur_len : int, width : int)

        Handle a chunk of text (most likely a word, not whitespace) that
        is too long to fit in any line.
        """
        # Figure out when indent is larger than the specified width, and make
        # sure at least one character is stripped off on every pass
        if width < 1:
            space_left = 1
        else:
            space_left = width - cur_len

        # If we're allowed to break long words, then do so: put as much
        # of the next chunk onto the current line as will fit.
        if self.break_long_words:
            end = space_left
            chunk = reversed_chunks[-1]
            if self.break_on_hyphens and ansilen_unicode(chunk) > space_left:
                # break after last hyphen, but only if there are
                # non-hyphens before it
                hyphen = chunk.rfind('-', 0, space_left)
                if hyphen > 0 and any(c != '-' for c in chunk[:hyphen]):
                    end = hyphen + 1
            # This is incorrect for double width characters, we need to use ansilen_unicode
            # cur_line.append(chunk[:end])
            # reversed_chunks[-1] = chunk[end:]

            # iterative version with ansilen_unicode
            left_part = ""
            right_part = chunk
            for c in chunk:
                if ansilen_unicode(left_part + c) > space_left:
                    break
                left_part += c
                right_part = right_part[1:]
            cur_line.append(left_part)
            reversed_chunks[-1] = right_part

        # Otherwise, we have to preserve the long word intact.  Only add
        # it to the current line if there's nothing already there --
        # that minimizes how much we violate the width constraint.
        elif not cur_line:
            cur_line.append(reversed_chunks.pop())

        # If we're not allowed to break long words, and there's already
        # text on the current line, do nothing.  Next time through the
        # main loop of _wrap_chunks(), we'll wind up here again, but
        # cur_len will be zero, so the next line will be entirely
        # devoted to the long word that we can't handle right now.

    def _wrap_chunks(self, chunks):
        """_wrap_chunks(chunks : [string]) -> [string]

        Wrap a sequence of text chunks and return a list of lines of
        length 'self.width' or less.  (If 'break_long_words' is false,
        some lines may be longer than this.)  Chunks correspond roughly
        to words and the whitespace between them: each chunk is
        indivisible (modulo 'break_long_words'), but a line break can
        come between any two chunks.  Chunks should not have internal
        whitespace; ie. a chunk is either all whitespace or a "word".
        Whitespace chunks will be removed from the beginning and end of
        lines, but apart from that whitespace is preserved.
        """
        lines = []
        if self.width <= 0:
            raise ValueError("invalid width %r (must be > 0)" % self.width)
        if self.max_lines is not None:
            if self.max_lines > 1:
                indent = self.subsequent_indent
            else:
                indent = self.initial_indent
            if ansilen_unicode(indent) + ansilen_unicode(self.placeholder.lstrip()) > self.width:
                raise ValueError("placeholder too large for max width")

        # Arrange in reverse order so items can be efficiently popped
        # from a stack of chucks.
        chunks.reverse()

        while chunks:

            # Start the list of chunks that will make up the current line.
            # cur_len is just the length of all the chunks in cur_line.
            cur_line = []
            cur_len = 0

            # Figure out which static string will prefix this line.
            if lines:
                indent = self.subsequent_indent
            else:
                indent = self.initial_indent

            # Maximum width for this line.
            width = self.width - ansilen_unicode(indent)

            # First chunk on line is whitespace -- drop it, unless this
            # is the very beginning of the text (ie. no lines started yet).
            if self.drop_whitespace and chunks[-1].strip() == '' and lines:
                del chunks[-1]

            while chunks:
                l = ansilen_unicode(chunks[-1])

                # Can at least squeeze this chunk onto the current line.
                if cur_len + l <= width:
                    cur_line.append(chunks.pop())
                    cur_len += l

                # Nope, this line is full.
                else:
                    break

            # The current line is full, and the next chunk is too big to
            # fit on *any* line (not just this one).
            if chunks and ansilen_unicode(chunks[-1]) > width:
                self._handle_long_word(chunks, cur_line, cur_len, width)
                cur_len = sum(map(ansilen_unicode, cur_line))

            # If the last chunk on this line is all whitespace, drop it.
            if self.drop_whitespace and cur_line and cur_line[-1].strip() == '':
                cur_len -= ansilen_unicode(cur_line[-1])
                del cur_line[-1]

            if cur_line:
                if (self.max_lines is None or
                    len(lines) + 1 < self.max_lines or
                    (not chunks or
                     self.drop_whitespace and
                     len(chunks) == 1 and
                     not chunks[0].strip()) and cur_len <= width):
                    # Convert current line back to a string and store it in
                    # list of all lines (return value).
                    lines.append(indent + ''.join(cur_line))
                else:
                    while cur_line:
                        if (cur_line[-1].strip() and
                            cur_len + ansilen_unicode(self.placeholder) <= width):
                            cur_line.append(self.placeholder)
                            lines.append(indent + ''.join(cur_line))
                            break
                        cur_len -= ansilen_unicode(cur_line[-1])
                        del cur_line[-1]
                    else:
                        if lines:
                            prev_line = lines[-1].rstrip()
                            if (ansilen_unicode(prev_line) + ansilen_unicode(self.placeholder) <=
                                    self.width):
                                lines[-1] = prev_line + self.placeholder
                                break
                        lines.append(indent + self.placeholder.lstrip())
                    break

        return lines

    def _split_chunks(self, text):
        text = self._munge_whitespace(text)
        return self._split(text)

    # -- Public interface ----------------------------------------------

    def wrap(self, text):
        """wrap(text : string) -> [string]

        Reformat the single paragraph in 'text' so it fits in lines of
        no more than 'self.width' columns, and return a list of wrapped
        lines.  Tabs in 'text' are expanded with string.expandtabs(),
        and all other whitespace characters (including newline) are
        converted to space.
        """
        chunks = self._split_chunks(text)
        if self.fix_sentence_endings:
            self._fix_sentence_endings(chunks)
        return self._wrap_chunks(chunks)

    def fill(self, text):
        """fill(text : string) -> string

        Reformat the single paragraph in 'text' to fit in lines of no
        more than 'self.width' columns, and return a new string
        containing the entire wrapped paragraph.
        """
        return "\n".join(self.wrap(text))

def ansi_terminate_lines(lines):
    """
    Walk through lines of text, terminating any outstanding color spans at
    the end of each line, and if one needed to be terminated, starting it on
    starting the color at the beginning of the next line.
    """
    state = ANSIState()
    term_lines = []
    end_code = None
    for line in lines:
        codes = ANSIRE.findall(line)
        for c in codes:
            state.consume(c)
        if end_code:          # from prior line
            line = end_code + line
        end_code = state.code()
        if end_code:          # from this line
            line = line + '\x1b[0m'

        term_lines.append(line)

    return term_lines

def _unified_indent(kwargs):
    """
    Private helper. If kwargs has an `indent` parameter, that is
    made into the the value of both the `initial_indent` and the
    `subsequent_indent` parameters in the returned dictionary.
    """
    indent = kwargs.get('indent')
    if indent is None:
        return kwargs
    unifed = kwargs.copy()
    del unifed['indent']
    str_or_int = lambda val: ' ' * val if isinstance(val, int) else val
    if isinstance(indent, tuple):
        initial, subsequent = indent
    else:
        initial, subsequent = (indent, indent)

    initial, subsequent = indent if isinstance(indent, tuple) else (indent, indent)
    unifed['initial_indent'] = str_or_int(initial)
    unifed['subsequent_indent'] = str_or_int(subsequent)
    return unifed

def wrap(s, width=70, **kwargs):
    """
    Wrap a single paragraph of text, returning a list of wrapped lines.

    Designed to work exactly as `textwrap.wrap`, with two exceptions:
    1. Wraps text containing ANSI control code sequences without considering
    the length of those (hidden, logically zero-length) sequences.
    2. Accepts a unified `indent` parameter that, if present, sets the
    `initial_indent` and `subsequent_indent` parameters at the same time.
    """
    kwargs = _unified_indent(kwargs)
    wrapper = OurTextWrapper(width=width, **kwargs)
    wrapped = wrapper.wrap(s)
    return ansi_terminate_lines(wrapped)

"""
# Testing

# Basic text
print(ansilen_unicode("Test"), "should be 4")
print(ansilen_unicode("Test\x1b[31m"), "should be 4")
print(ansilen_unicode("Test\x1b[31mTest"), "should be 8")

# JP text (double wide chars)
print(ansilen_unicode("テスト"), "should be 6")
print(ansilen_unicode("テスト\x1b[31m"), "should be 6")
print(ansilen_unicode("テスト\x1b[31mテスト"), "should be 12")

# Mixed JP and EN text
print(ansilen_unicode("テストTest"), "should be 10")
print(ansilen_unicode("テスト\x1b[31mTest"), "should be 10")
print(ansilen_unicode("テスト\x1b[31mTestテスト"), "should be 16")

# Emoji
print(ansilen_unicode("👍"), "should be 2")

# Long input text that contains en, jp and emoji, no ANSI escapes
test_text = "The テスト quick テスト brown テスト fox👍 テスト jumps👍 テスト 👍 over テスト 👍 the テスト lazy テスト dog. 👍 👍 👍 👍 👍 👍 👍 👍 👍 👍 👍 👍 👍 👍 👍  test test test test test test test test test test test test test test test test test test test テスト テストト テスト テスト テスト テスト テスト テスト テスト テスト テスト テストテストテストテストテストテストテストテストテストテストテストテストテストテストテスト👍👍👍👍👍👍👍👍👍👍👍👍👍👍👍👍👍👍👍👍👍👍👍👍👍aiueoaiueoaiueoaiueoaiueoaiueoaiueoaiueoaiueoaiueo"
wrapped = wrap(test_text, 20)
for line in wrapped:
    #print(ansilen_unicode(line))
    print(ansilen_unicode(line), line)

# Now add some ANSI escapes at random points:
# Bold face
# basic colour
# RGB colour
# basic colour and background
# RGB colour and background
# RGB with background + bold
escapes = [
    "\x1b[1m",
    "\x1b[31m",
    "\x1b[38;2;255;0;0m",
    "\x1b[41m",
    "\x1b[48;2;255;0;0m",
    "\x1b[48;2;255;0;0;1m"
]

# Add the ANSI escapes to the text. Just cycle them and add one every 16 characters, followed by a reset 8 characters later
test_text_with_escapes = ""
for i, c in enumerate(test_text):
    test_text_with_escapes += c
    if i % 16 == 0:
        test_text_with_escapes += escapes[i % len(escapes)]
    if i % 16 == 8:
        test_text_with_escapes += "\x1b[0m"

print("Base text:", test_text_with_escapes)
wrapped = wrap(test_text_with_escapes, 20)
for line in wrapped:
    print(ansilen_unicode(line), "\x1b[0m" + line)
print("\x1b[0m")
"""