# pylint: disable=W0603

from functools import wraps
from subprocess import call
import logging
import os
import sys

from tornado.template import Template
from tornado.options import parse_command_line

from fbcli import fb
from fbcli import editor
from fbcli import ui

FB = fb.FBClient()
CURRENT_CASE = None
CURRENT_USER = None

COMMANDS = {}


def set_current_case(case):
    global CURRENT_CASE
    CURRENT_CASE = case
    return case


def set_current_user(user):
    global CURRENT_USER
    CURRENT_USER = user
    return user


def command(*names):
    logger = logging.getLogger('fb.cmd')

    def wrapper(f):

        for name in names:
            COMMANDS[name] = Command(f)

        @wraps(f)
        def helper(*args, **kwargs):
            logger.debug(f.__name__)
            return f(*args, **kwargs)

        return helper

    return wrapper


class Command(object):

    def __init__(self, f):
        self.f = f

    def __call__(self, *args, **kwargs):
        return self.f(*args, **kwargs)

    def desc(self):
        if self.f.__doc__ is None:
            return '?'
        return self.f.__doc__.splitlines()[0]

    def help(self):
        return self.f.__doc__


class FBObj(object):

    TMPL = None

    def to_string(self):
        return self.TMPL.generate(
            obj=self,
            ui=ui,
        )

    def __str__(self):
        return self.to_string()


class FBPerson(FBObj):

    TMPL = Template('''{% raw obj.fullname %} <{% raw obj.email %}>''')

    # Cache persons, who don't change that often...
    CACHE = set()

    logger = logging.getLogger('fb.person')

    def __init__(self, person):
        self._person = person

    @classmethod
    def _get(cls, **kwargs):
        cls.logger.debug('Getting person %s', kwargs)
        persons = FB.viewPerson(**kwargs)
        person = persons.find('person')
        return cls(person)

    @classmethod
    def get_by_email(cls, email):
        for p in cls.CACHE:
            if p.email == email:
                return p
        p = cls._get(sEmail=email)
        cls.CACHE.add(p)
        return p

    @classmethod
    def get_by_id(cls, person_id):
        for p in cls.CACHE:
            if p.id == person_id:
                return p
        p = cls._get(ixPerson=person_id)
        cls.CACHE.add(p)
        return p

    @property
    def id(self):
        return int(self._person.ixperson.text)

    @property
    def fullname(self):
        return self._person.sfullname.text

    @property
    def email(self):
        return self._person.semail.text


class FBCase(FBObj):

    TMPL = Template('''
{{ ui.hl1 }}
[{% raw ui.cyan(obj.id) %}] {% raw ui.blue(obj.title) %}
{% raw ui.status(obj.status) %} - \
Opened by {% raw ui.brown(obj.opened_by.fullname) %} - \
Assigned to {% raw ui.red(obj.assigned_to) %}
{% raw ui.white(obj.permalink) %}
{{ ui.hl1}}
{% for event in obj.events %}
{{ ui.hl2 }}
{% raw event %}
{% end %}
''')

    def __init__(self, ixBug):
        self.id = int(ixBug)
        self.reset()

    def reset(self):
        self._case = self._get_raw(self.id)
        return set_current_case(self)

    @staticmethod
    def _get_raw(ixBug):
        assert isinstance(ixBug, int)
        cols = [
            'sTitle',
            'sStatus',
            'sPersonAssignedTo',
            'ixPersonOpenedBy',
            'events',
        ]
        return FB.search(q=ixBug, cols=','.join(cols))

    @property
    def title(self):
        return self._case.stitle.text

    @property
    def status(self):
        return self._case.sstatus.text

    @property
    def assigned_to(self):
        return self._case.spersonassignedto.text

    @property
    def opened_by_id(self):
        return int(self._case.ixpersonopenedby.text)

    @property
    def opened_by(self):
        return FBPerson.get_by_id(self.opened_by_id)

    @property
    def events(self):
        return [FBBugEvent(event) for event in self._case.events]

    @property
    def permalink(self):
        return FB.build_url('f/cases/{}'.format(self.id))

    @property
    def shortdesc(self):
        return '{} - {}'.format(
            self.permalink,
            self.title)

    def resolve(self):
        FB.resolve(
            ixBug=self.id, ixPersonEditedBy=CURRENT_USER.id)
        self.reset()

    def reopen(self):
        FB.reopen(ixBug=self.id, ixPersonEditedBy=CURRENT_USER.id)
        self.reset()

    def close(self):
        FB.close(
            ixBug=self.id, ixPersonEditedBy=CURRENT_USER.id)
        self.reset()

    def reactivate(self):
        FB.reactivate(ixBug=self.id, ixPersonEditedBy=CURRENT_USER.id)
        self.reset()

    def assign(self, person):
        FB.assign(
            ixBug=self.id, ixPersonEditedBy=CURRENT_USER.id,
            sPersonAssignedTo=person)
        self.reset()

    def edit(self, **kwargs):
        FB.edit(
            ixBug=self.id, ixPersonEditedBy=CURRENT_USER.id,
            **kwargs)
        self.reset()

    # def email(self):
    # def remind(self):


class FBBugEvent(FBObj):

    TMPL = Template(
        '''{{ obj.dt }} - {{ obj.person }}
{% raw ui.white(obj.desc) %}
{% raw obj.comment %}''')

    def __init__(self, event):
        self._event = event

    @property
    def id(self):
        return int(self._event.ixbugevent.text)

    @property
    def dt(self):
        return self._event.dt.text

    @property
    def person(self):
        return self._event.sperson.text

    @property
    def desc(self):
        return self._event.evtdescription.text

    @property
    def comment(self):
        return self._event.s.text


class FBShortCase(FBObj):

    TMPL = Template(
        '''{% raw ui.cyan(str(obj.id).rjust(6)) %} - \
{% raw ui.status(ui.ltrunc(obj.status, 20)) %} {% raw ui.blue(obj.title) %}''')

    def __init__(self, ixBug, status, title):
        self.id = ixBug
        self.status = status
        self.title = title


class FBCaseSearch(FBObj):

    TMPL = Template('''
{% for case in obj.shortcases %}{% raw case %}
{% end %}''')

    logger = logging.getLogger('fb.search')

    def __init__(self, shortcases):
        self.shortcases = shortcases

    @classmethod
    def search(cls, q):
        cls.logger.debug('Searching for %r', q)
        cases = []
        resp = FB.search(q=q, cols="ixBug,sTitle,sStatus")
        for case in resp.cases.findAll('case'):
            cases.append(FBShortCase(
                int(case.ixbug.text), case.sstatus.text, case.stitle.text))
        return cls(cases)


def get_prompt():
    return ui.cyan('%s>>> ' % (
        '[%s] ' % CURRENT_CASE.id if CURRENT_CASE else ''))


@command('logon', 'login')
def logon():
    '''Logon to FB API.

    Uses $FBURL, $FBUSER and $FBPASS, otherwise prompts for them.

    Example:
    >>> logon
    '''
    FB.login()
    return set_current_user(FBPerson.get_by_email(FB.current_user))


@command('logoff', 'logout')
def logoff():
    '''Logoff from FB API.

    Example:
    >>> logoff
    '''
    FB.logoff()
    return set_current_user(None)


@command('help', '?')
def help_(*args):
    '''Show help.

    Example:
    >>> help
    >>> help logon
    '''
    if len(args) == 0:
        print 'Fogbugz CLI Help'
        print
        print 'Available commands:'
        for name, cmd in sorted(COMMANDS.iteritems()):
            print '{} - {}'.format(name.rjust(12), cmd.desc())
        print
        print 'Type "help <cmd>" for more.'
    else:
        name = args[0]
        print COMMANDS[name].help()


@command('whoami')
def whoami():
    '''Shows the current user.

    Example:
    >>> whoami
    '''
    print CURRENT_USER


@command('show')
def show(ixBug=None):
    '''Show the current ticket.

    Example:
    >>> show  # shows the current ticket
    >>> show 1234  # shows ticket 1234
    '''
    if ixBug is None:
        assert_current()
        print CURRENT_CASE
    else:
        case = FBCase(int(ixBug))
        print case


@command('close')
def close_current():
    '''Close the current ticket.'''
    assert_current()
    CURRENT_CASE.close()


@command('reactivate')
def reactivate_current():
    '''Reactivate the current ticket.'''
    assert_current()
    CURRENT_CASE.reactivate()


@command('resolve')
def resolve_current():
    '''Resolve the current ticket.'''
    assert_current()
    CURRENT_CASE.resolve()


@command('reopen')
def reopen_current():
    '''Reopen the current ticket.'''
    assert_current()
    CURRENT_CASE.reopen()


@command('assign')
def assign_current(*args):
    '''Assign the current ticket to person.

    Example:
    >>> assign lorenzo bolla
    '''
    assert_current()
    person = ' '.join(args)
    CURRENT_CASE.assign(person)


@command('comment')
def comment_current():
    '''Add a comment to the current ticket.

    Call $EDITOR to write the comment.

    Example:
    >>> comment
    '''
    assert_current()
    comment = editor.write()
    if comment:
        CURRENT_CASE.edit(sEvent=comment)
    else:
        print 'Aborted.'


@command('search')
def search(*args):
    '''Search for cases.

    Example:
    >>> search carmax
    >>> search assignedTo:"Lorenzo Bolla" status:Active
    '''
    q = ' '.join(args)
    rs = FBCaseSearch.search(q)
    print rs


@command('mycases')
def mycases():
    '''List the cases of the logged in user.

    Example:
    >>> mycases
    '''
    q = 'assignedto:"{}" status:Active'.format(CURRENT_USER.fullname)
    search(q)


@command('browse', 'b')
def browse():
    '''Browse current case in $BROWSER.

    Example:
    >>> browse
    >>> b
    '''
    assert_current()
    browser = os.environ.get('BROWSER')
    if browser is None:
        print 'Set $BROWSER first'
    else:
        call([browser, CURRENT_CASE.permalink])


@command('quit', 'exit', 'bye')
def quit_():
    '''Quit.

    Example:
    >>> quit
    '''
    print 'Bye!'
    sys.exit(0)


def read_():
    cmdline = raw_input(get_prompt())
    if not cmdline:
        return None, None
    tokens = cmdline.split()
    cmd, args = tokens[0], tokens[1:]
    return cmd, args


def assert_current():
    assert CURRENT_CASE is not None, 'Pick a case first!'


def exec_(cmd, args):

    if cmd.isdigit():
        show(cmd)

    else:
        f = COMMANDS.get(cmd)
        assert f is not None, 'Unknown command {}'.format(cmd)
        return f(*args)


def main():
    logger = logging.getLogger('fb.main')
    ui.init_readline()
    args = parse_command_line()

    logon()
    if args:
        exec_(args[0], args[1:])

    try:
        while True:
            try:
                cmd, args = read_()
                if cmd is None:
                    continue
                exec_(cmd, args)
            except EOFError:
                quit_()
            except KeyboardInterrupt:
                pass
            except Exception:
                logger.exception('ERROR')
    finally:
        logoff()
