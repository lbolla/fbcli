from __future__ import unicode_literals

from functools import partial, wraps
import atexit
import contextlib
import fcntl
import logging
import os
import readline
import signal
import struct
import sys
import termios

import six
from six.moves import html_parser


READLINE_HISTFILE = os.path.join(os.path.expanduser("~"), ".fbcli_history")


def _create_readline_logger():
    readline_logger = logging.getLogger('ui.readline')
    handler = logging.FileHandler('/tmp/fbcli_readline.log')
    handler.setFormatter(
        logging.Formatter('%(asctime)-15s %(levelname)s %(message)s'))
    readline_logger.addHandler(handler)
    readline_logger.propagate = False
    return readline_logger


# READLINE_LOGGER = _create_readline_logger()


def colorize(color, s, readline_safe=False):
    if _supports_color(sys.stdout):
        color_open = '\033[{}m'.format(color)
        color_close = '\033[0m'
        if readline_safe and sys.stdin.isatty():
            # \001 and \002 mark ignore boundaries for readline
            color_open = '\001' + color_open + '\002'
            color_close = '\001' + color_close + '\002'
    else:
        color_open = color_close = ''
    if not isinstance(s, six.string_types):
        s = six.text_type(s)
    return color_open + s + color_close


def _supports_color(stream):

    try:
        import curses
    except ImportError:
        curses = None

    color = False
    if curses and hasattr(stream, 'isatty') and stream.isatty():
        try:
            curses.setupterm()
            if curses.tigetnum(str("colors")) > 0:
                color = True
        except Exception:
            pass
    return color


def status(s):
    color_map = {
        'active': green,
        'testing': yellow,
        'needs additional': magenta,
        'resolved': cyan,
        'closed': darkgray,
    }
    s_ = s.strip().lower()

    for st, color in color_map.items():
        if st in s_:
            return color(s)
    return s


def priority(s):
    color_map = {
        'blocker': boldred,
        'critical': boldred,
        'high priority': lightred,
        'need to fix soon': red,
        'need to fix': white,
        'fix if time': gray,
        'for consideration': darkgray,
    }
    s_ = s.strip().lower()

    for st, color in color_map.items():
        if st == s_:
            return color(s)
    return s


def _id(color, s, ljust=None, rjust=None, **kwargs):
    if s is None:
        return
    id_ = '[{}]'.format(s)
    if ljust is not None:
        id_ = id_.ljust(ljust)
    if rjust is not None:
        id_ = id_.rjust(rjust)
    return color(id_, **kwargs)


def _tag(color, s):
    if s is None:
        return
    tag_ = '|{}|'.format(s)
    return color(tag_)


def title(s):
    return blue(s)


def _get_hw():
    try:
        return struct.unpack(
            str('hh'), fcntl.ioctl(sys.stdout, termios.TIOCGWINSZ, '1234'))
    except Exception:
        return (25, 80)


# Default values if setup_win is not called
hl1, hl2 = '=' * 80, '-' * 80


def setup_win():
    '''Setup globals that depend on window size.'''
    global hl1, hl2

    _height, width = _get_hw()
    hl1 = boldyellow('=' * width)
    hl2 = yellow('-' * width)


def sigwinch_handler(sig, stack_frame):
    '''Reset globals that depend on window sizes.'''
    setup_win()


def rtrunc(s, n):
    return s[:n].rjust(n)


def ltrunc(s, n):
    return s[:n].ljust(n)


def completer(text, state):
    from fbcli.cli import (
        COMMANDS, ALIASES, LAST_SEARCH, FBShortCase, FBPerson, CURRENT_CASE)

    # READLINE_LOGGER.info('text=%s state=%s', text, state)
    line = readline.get_line_buffer()

    cmd = line.split()[0] if line else None
    rest = line.split()[1:] if line else None
    if line and not line.endswith(' '):
        rest = rest[:-1]

    if rest:
        text = ' '.join(rest) + ' ' + text

    # READLINE_LOGGER.info(
    #     'cmd=%s line=%s rest=%s text=%s', cmd, line, rest, text)

    all_options = []
    if cmd == 'attachment' and text != 'attachment':
        if CURRENT_CASE:
            all_options += [str(a.id) for a in CURRENT_CASE.attachments]
    elif cmd in ('assign', 'notify'):
        all_options += [person.fullname for person in FBPerson.CACHE]
    else:
        all_options += list(COMMANDS.keys())
        all_options += list(ALIASES.keys())
        all_options += [str(case.id) for case in FBShortCase.HISTORY]
        if LAST_SEARCH:
            all_options += [str(case.id) for case in LAST_SEARCH.shortcases]

    # READLINE_LOGGER.info('all_options=%s', all_options)
    query = text.lower()
    options = [x for x in all_options if query in x.lower()]
    # READLINE_LOGGER.info('#options=%s', len(options))

    try:
        found = options[state]
        if rest:
            found = found[len(' '.join(rest)) + 1:]
        # READLINE_LOGGER.info('found=%s', found)
        return found + ' '
    except IndexError:
        # READLINE_LOGGER.info('No suggestions found')
        return None


def ignoring_IOerror(f):
    @wraps(f)
    def helper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except IOError:
            pass
    return helper


def init_readline():
    readline.set_completer(completer)
    readline.parse_and_bind('tab: complete')
    ignoring_IOerror(readline.read_history_file)(READLINE_HISTFILE)
    atexit.register(
        ignoring_IOerror(readline.write_history_file), READLINE_HISTFILE)


@contextlib.contextmanager
def no_readline_ctx():
    readline.write_history_file(READLINE_HISTFILE)
    try:
        yield
    finally:
        init_readline()


def html_unescape(s):
    return html_parser.HTMLParser().unescape(s)


# http://www.tldp.org/HOWTO/Bash-Prompt-HOWTO/x329.html
# http://misc.flogisoft.com/bash/tip_colors_and_formatting
black = partial(colorize, '0;30')
blue = partial(colorize, '0;34')
cyan = partial(colorize, '0;36')
darkgray = partial(colorize, '0;90')
gray = partial(colorize, '0;37')
green = partial(colorize, '0;32')
magenta = partial(colorize, '0;35')
red = partial(colorize, '0;31')
white = partial(colorize, '0;97')
yellow = partial(colorize, '0;33')

lightcyan = partial(colorize, '0;96')
lightgreen = partial(colorize, '0;92')
lightmagenta = partial(colorize, '0;95')
lightred = partial(colorize, '0;91')

boldcyan = partial(colorize, '1;36')
boldred = partial(colorize, '1;31')
boldwhite = partial(colorize, '1;37')
boldyellow = partial(colorize, '1;33')

caseid = partial(_id, boldcyan)
eventid = partial(_id, darkgray)
linkid = partial(_id, lightmagenta)
attachmentid = partial(_id, lightgreen)

tag = partial(_tag, darkgray)

setup_win()
# React on window's resizes
signal.signal(signal.SIGWINCH, sigwinch_handler)
