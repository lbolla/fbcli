from StringIO import StringIO
from itertools import takewhile, dropwhile
from subprocess import call
import contextlib
import os
import tempfile

import yaml

from fbcli import errors

EDITOR = os.environ.get('EDITOR', 'vim')
COMMENT_CHAR = '#'
FOOTER = '''# Lines starting wth "#" will be ignored.
# Leave this file empty to abort action.
'''

DEFAULT_HEADER = '\n'
YES = 1
NO = 2

FNAME = os.path.join(tempfile.gettempdir(), '.fbcli_comment')


def clear():
    if os.path.exists(FNAME):
        os.remove(FNAME)


def _get_file():
    reuse, mode = False, 'w+r'
    if os.path.exists(FNAME):
        if yes_or_no('Comment file already exists. Reuse?') == NO:
            clear()
        else:
            reuse, mode = True, 'a+r'
    return open(FNAME, mode), reuse


def _strip_comments(text):
    out = []
    for line in text.splitlines():
        if line.startswith(COMMENT_CHAR):
            continue
        out.append(line)
    return '\n'.join(out)


def _write(header=DEFAULT_HEADER):
    fid, reuse = _get_file()

    try:
        if not reuse:
            fid.write(header)
            fid.write(FOOTER)
            fid.flush()

        call([EDITOR, fid.name])
        fid.seek(0)
        text = fid.read()
        return Text(text)

    finally:
        fid.close()


def yes_or_no(question):
    ans = raw_input(question + ' [Y/n] ')
    if ans.lower() in ['', 'y', 'yes']:
        return YES
    return NO


def _maybe_write(question, header=DEFAULT_HEADER):
    if yes_or_no(question) == YES:
        return _write(header)


@contextlib.contextmanager
def _clearing():
    '''Do not clear comment file on errors, unless it's an Aborted.'''
    try:
        yield
    except errors.Aborted:
        clear()
        raise
    except Exception:
        raise
    else:
        clear()


@contextlib.contextmanager
def writing(header=DEFAULT_HEADER):
    with _clearing():
        yield _write(header)


@contextlib.contextmanager
def maybe_writing(question, header=DEFAULT_HEADER):
    with _clearing():
        yield _maybe_write(question, header)


def abort_if_empty(text):
    if text.is_empty():
        raise errors.Aborted()


class Text(object):

    SEP = '---'

    def __init__(self, text):
        self._header, self._raw_body = self._parse(text)

    def _parse(self, text):
        lines = {line.strip() for line in text.splitlines()}
        if self.SEP in lines:
            return self._parse_with_header(text)
        return self._parse_no_header(text)

    @staticmethod
    def _parse_no_header(text):
        return None, text

    def _parse_with_header(self, text):
        lines = (line.strip() for line in text.splitlines())
        # Take everything up to sep
        header = '\n'.join(
            takewhile(lambda line: line != self.SEP, lines))
        # drop SEP
        lines.next()
        # the rest is body
        body = '\n'.join(lines)
        return header, body

    @property
    def meta(self):
        buf = StringIO(self._header)
        return yaml.load(buf)

    @property
    def body(self):
        return _strip_comments(self._raw_body.decode('utf-8')).strip('\n')

    def is_empty(self):
        return not self.body
