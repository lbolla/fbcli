from collections import OrderedDict
from itertools import takewhile, dropwhile
from subprocess import call
import contextlib
import os
import tempfile

from six.moves import input

import yaml

from fbcli import errors

EDITOR = os.environ.get('EDITOR', 'vi')
COMMENT_CHAR = '#'
FOOTER = '''# Lines starting wth "#" will be ignored.
# Leave this file empty to abort action.
# It's possible to add metadata in the format of a header.
# Use "---" as separator between the header and the body.
# E.g. To upload files use:
#    Files:
#      - path_to_file_1
#      - path_to_file_2
'''

DEFAULT_HEADER = '\n'
YES = 1
NO = 2

FNAME = os.path.join(tempfile.gettempdir(), '.fbcli_comment')


def clear():
    if os.path.exists(FNAME):
        os.remove(FNAME)


def _get_file():
    reuse, mode = False, 'w+'
    if os.path.exists(FNAME):
        if yes_or_no('Comment file already exists. Reuse?') == NO:
            clear()
        else:
            reuse, mode = True, 'a+'
    return open(FNAME, mode), reuse


def _strip_comments(text):
    lines = dropwhile(
        lambda line: line.startswith(COMMENT_CHAR),
        reversed(text.splitlines()))
    return '\n'.join(reversed(list(lines)))


def _write(header=DEFAULT_HEADER):
    fid, reuse = _get_file()

    try:
        if not reuse:
            fid.write(header)
            fid.write(FOOTER)
            fid.flush()

        if EDITOR:
            call(EDITOR.split() + [fid.name])
        fid.seek(0)
        text = fid.read()
        return Text(text)

    finally:
        fid.close()


def yes_or_no(question):
    ans = input(question + ' [Y/n] ')
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
        # the rest is body
        body = '\n'.join(lines)
        return header, body

    @property
    def meta(self):
        if self._header is None:
            return {}
        return yaml.load(self._header)

    @property
    def body(self):
        return _strip_comments(self._raw_body).strip('\n')

    @property
    def nfiles(self):
        return len(self.meta.get('Files', []))

    @property
    def files(self):
        fs = OrderedDict()
        for fname_ in self.meta.get('Files', []):
            # Handle paths like ~/README.txt
            fname = os.path.expanduser(fname_)
            bname = _encode_for_upload(os.path.basename(fname))
            fs[bname] = open(fname, 'rb')
        return fs

    def is_empty(self):
        return not self.body and not self.meta

    def validate_for_new(self):
        assert 'Title' in self.meta, 'Missing title'
        assert self.meta['Title'] is not None, 'Missing title'
        assert self.meta['Title'] != '<title>', 'Specify a valid title'

    def get_params_for_new(self):
        self.validate_for_new()
        meta = self.meta
        params = dict(
            sTitle=meta.get('Title'),
            sPersonAssignedTo=meta.get('Assign to'),
            sProject=meta.get('Project'),
            sArea=meta.get('Area'),
            sPriority=meta.get('Priority'),
            sFixFor=meta.get('Milestone'),
            sTags=','.join(meta.get('Tags', [])),
            ixBugParent=meta.get('Parent'),
            sEvent=self.body,
        )
        if self.nfiles > 0:
            params['Files'] = self.files
        return params

    def get_params_for_comment(self):
        params = dict(
            sEvent=self.body,
            sTags=','.join(self.meta.get('Tags', [])),
        )
        if self.nfiles > 0:
            params['Files'] = self.files
        return params

    def get_params_for_amend(self):
        params = self.get_params_for_comment()
        assert 'Files' not in params, 'Attachments not supported with amend'
        return params


def _encode_for_upload(s):
    '''Remove unsafe characters that seem to break uploads.'''
    return s.replace(':', '_')
