from subprocess import call
import os
import tempfile

EDITOR = os.environ.get('EDITOR', 'vim')
COMMENT_CHAR = '#'
FOOTER = '''# Lines starting wth "#" will be ignored.
# Leave this file empty to abort action.
'''


def write(header='\n'):
    with tempfile.NamedTemporaryFile() as fid:
        fid.write(header)
        fid.write(FOOTER)
        fid.flush()
        call([EDITOR, fid.name])
        fid.seek(0)
        text = fid.read()
    return strip_comments(text)


def strip_comments(text):
    out = []
    for line in text.splitlines():
        if line.startswith(COMMENT_CHAR):
            continue
        out.append(line)
    return '\n'.join(out)
