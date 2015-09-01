from subprocess import call
import os
import tempfile

EDITOR = os.environ.get('EDITOR', 'vim')
COMMENT_CHAR = '#'
FOOTER = '''# Lines starting wth "#" will be ignored.
# Leave this file empty to abort action.
'''

YES = 1
NO = 2

FNAME = os.path.join(tempfile.gettempdir(), '.fbcli_comment')


def clear():
    if os.path.exists(FNAME):
        os.remove(FNAME)


def get_file():
    reuse, mode = False, 'w+r'
    if os.path.exists(FNAME):
        if yes_or_no('Comment file already exists. Reuse?') == NO:
            clear()
        else:
            reuse, mode = True, 'a+r'
    return open(FNAME, mode), reuse


def strip_comments(text):
    out = []
    for line in text.splitlines():
        if line.startswith(COMMENT_CHAR):
            continue
        out.append(line)
    return '\n'.join(out)


def write(header='\n'):
    fid, reuse = get_file()

    try:
        if not reuse:
            fid.write(header)
            fid.write(FOOTER)
            fid.flush()

        call([EDITOR, fid.name])
        fid.seek(0)
        text = fid.read()
        return strip_comments(text)

    finally:
        fid.close()


def yes_or_no(question):
    ans = raw_input(question + ' [Y/n] ')
    if ans.lower() in ['', 'y', 'yes']:
        return YES
    return NO


def ask_and_maybe_write(question, header='\n'):
    if yes_or_no(question) == YES:
        return write(header)
