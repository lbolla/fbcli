from functools import partial, wraps
import atexit
import fcntl
import HTMLParser
import os
import readline
import struct
import sys
import termios


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
    if not isinstance(s, basestring):
        s = unicode(s)
    return color_open + s.encode('utf-8') + color_close


def _supports_color(stream):

    try:
        import curses
    except ImportError:
        curses = None

    color = False
    if curses and hasattr(stream, 'isatty') and stream.isatty():
        try:
            curses.setupterm()
            if curses.tigetnum("colors") > 0:
                color = True
        except Exception:
            pass
    return color


# http://www.tldp.org/HOWTO/Bash-Prompt-HOWTO/x329.html
black = partial(colorize, '0;30')
red = partial(colorize, '0;31')
green = partial(colorize, '0;32')
brown = partial(colorize, '0;33')
blue = partial(colorize, '0;34')
purple = partial(colorize, '0;35')
cyan = partial(colorize, '0;36')
gray = partial(colorize, '0;37')
darkgray = partial(colorize, '1;30')
lightred = partial(colorize, '1;31')
lightgreen = partial(colorize, '1;32')
yellow = partial(colorize, '1;33')
lightpurple = partial(colorize, '1;35')
lightcyan = partial(colorize, '1;36')
white = partial(colorize, '1;37')


def status(s):
    color_map = {
        'active': green,
        'testing': yellow,
        'needs additional': purple,
        'resolved': gray,
        'closed': darkgray,
    }
    s_ = s.strip().lower()

    for st, color in color_map.iteritems():
        if st in s_:
            return color(s)
    return s


def priority(s):
    color_map = {
        'blocker': lightred,
        'critical': lightred,
        'high priority': red,
        'need to fix soon': red,
        'need to fix': gray,
        'fix if time': gray,
        'for consideration': darkgray,
    }
    s_ = s.strip().lower()

    for st, color in color_map.iteritems():
        if st == s_:
            return color(s)
    return s


def _id(color, s, ljust=None, rjust=None):
    id_ = '[{}]'.format(s)
    if ljust is not None:
        id_ = id_.ljust(ljust)
    if rjust is not None:
        id_ = id_.rjust(rjust)
    return color(id_)


caseid = partial(_id, lightcyan)
linkid = partial(_id, lightpurple)
attachmentid = partial(_id, lightpurple)


def title(s):
    return blue(s)


def _get_hw():
    try:
        return struct.unpack(
            'hh', fcntl.ioctl(sys.stdout, termios.TIOCGWINSZ, '1234'))
    except Exception:
        return (25, 80)


HEIGHT, WIDTH = _get_hw()
hl1 = yellow('=' * WIDTH)
hl2 = brown('-' * WIDTH)


def rtrunc(s, n):
    return s[:n].rjust(n)


def ltrunc(s, n):
    return s[:n].ljust(n)


def completer(text, state):
    from fbcli.cli import COMMANDS, LAST_SEARCH, FBShortCase, FBPerson

    all_options = COMMANDS.keys()
    all_options += [str(case.id) for case in FBShortCase.HISTORY]
    all_options += [person.fullname for person in FBPerson.CACHE]
    if LAST_SEARCH:
        all_options += [str(case.id) for case in LAST_SEARCH.shortcases]

    options = [x for x in all_options if x.startswith(text)]
    try:
        return options[state]
    except IndexError:
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
    readline.set_completer_delims(' \t\n')
    readline.parse_and_bind('tab: complete')
    histfile = os.path.join(os.path.expanduser("~"), ".fbcli_history")
    ignoring_IOerror(readline.read_history_file)(histfile)
    atexit.register(ignoring_IOerror(readline.write_history_file), histfile)
    del histfile


def html_unescape(s):
    return HTMLParser.HTMLParser().unescape(s)
