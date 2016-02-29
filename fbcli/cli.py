# pylint: disable=too-many-lines,redefined-builtin,global-statement
# pylint: disable=too-many-public-methods,redefined-outer-name

from __future__ import print_function

from functools import wraps
from subprocess import call
import contextlib
import logging
import os
import re
import sys
import tempfile

import six
from six.moves import input, urllib, configparser

from tornado.template import Template
from tornado.options import parse_command_line
import yaml

from fbcli import browser
from fbcli import errors
from fbcli import fb
from fbcli import editor
from fbcli import ui

FB = fb.FBClient()
CURRENT_CASE = None
CURRENT_USER = None
LAST_SEARCH = None

COMMANDS = {}
ALIASES = {}


# Poor man HTML link regex
URL_RE = re.compile(r'\bhttp[s]?://[^\b \n\r\(\)\[\]\{\}]*')

logger = logging.getLogger('fb.cli')


def set_current_case(case):
    '''Set case as current and refresh history.'''
    global CURRENT_CASE
    CURRENT_CASE = case
    FBShortCase.HISTORY.push(case)
    return case


def set_current_user(user):
    global CURRENT_USER
    CURRENT_USER = user
    return user


def set_last_search(search):
    global LAST_SEARCH
    LAST_SEARCH = search


def command(name):
    cmdlogger = logging.getLogger('fb.cmd')

    def wrapper(f):
        COMMANDS[name] = Command(f)

        @wraps(f)
        def helper(*args, **kwargs):
            cmdlogger.debug(f.__name__)
            return f(*args, **kwargs)

        return helper

    return wrapper


def alias(name, cmdline):
    ALIASES[name] = a = Alias(cmdline)
    return a


def xdg_open(what):
    retval = call('which xdg-open > /dev/null', shell=True)
    if retval != 0:
        logging.warning('Cannot open: No xdg-open available')
    else:
        call(['xdg-open', what])


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


class Alias(object):

    def __init__(self, cmdline):
        tokens = cmdline.split()
        self.cmdname = tokens[0]
        self.args = tokens[1:]

    @property
    def cmd(self):
        cmd = COMMANDS.get(self.cmdname)
        assert cmd is not None, 'Unknown command {}'.format(self.cmdname)
        return cmd

    def __call__(self, *args):
        args = self.args + list(args)
        return self.cmd(*args)

    def desc(self):
        return ' '.join([self.cmdname] + self.args)

    def help(self):
        return 'Alias for: {}\n\n{}'.format(
            ui.boldwhite(self.desc()), self.cmd.help())


class FBObj(object):

    TMPL = None

    def to_string(self):
        return self.TMPL.generate(
            obj=self,
            ui=ui,
        ).decode('utf-8')

    def __unicode__(self):
        return self.to_string()

    def __str__(self):
        # Ugly workaround to make tornado's Template play nicely with
        # py2 and py3
        u = self.__unicode__()
        if not isinstance(u, str):
            u = u.encode('utf8')
        return u


class FBStatus(FBObj):

    CACHE = set()

    def __init__(self, status):
        self._status = status
        self.CACHE.add(self)

    @classmethod
    def get_by_name(cls, name):
        if not cls.CACHE:
            cls.get_all()
        for s in cls.CACHE:
            if name == s.name:
                return s

    @staticmethod
    def get_all():
        result = FB.listStatuses()
        return [FBStatus(a) for a in result.findAll('status')]

    @property
    def id(self):
        return int(self._status.ixStatus.get_text(strip=True))

    @property
    def name(self):
        return self._status.sStatus.get_text(strip=True)


class FBPerson(FBObj):

    TMPL = Template('''{% raw obj.fullname %} <{% raw obj.email %}>''')

    # Cache persons, who don't change that often...
    CACHE = set()

    logger = logging.getLogger('fb.person')

    def __init__(self, person):
        self._person = person
        self.CACHE.add(self)

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
        return p

    @classmethod
    def get_by_id(cls, person_id):
        for p in cls.CACHE:
            if p.id == person_id:
                return p
        p = cls._get(ixPerson=person_id)
        return p

    @staticmethod
    def get_all():
        result = FB.listPeople()
        return sorted(
            [FBPerson(a) for a in result.findAll('person')],
            key=lambda p: (p.fullname, p.email))

    @property
    def id(self):
        return int(self._person.ixPerson.get_text(strip=True))

    @property
    def fullname(self):
        return self._person.sFullName.get_text(strip=True)

    @property
    def email(self):
        return self._person.sEmail.get_text(strip=True)


class History(FBObj):

    TMPL = Template('''
{% for case in obj._history %}{% raw case %}
{% end %}''')

    def __init__(self):
        self._history = []

    def push(self, case):
        '''Add new history item. Remove first if it exists.'''
        scase = FBShortCase.from_case(case)
        if scase in self._history:
            self._history.remove(scase)
        self._history.insert(0, scase)

    def __iter__(self):
        return iter(self._history)

    def back(self):
        if len(self._history) > 1:
            return self._history[1]
        return None


class FBCase(FBObj):

    TMPL = Template('''
{{ ui.hl1 }}
{% raw ui.caseid(obj.id) %} ({% raw obj.project %}/{% raw obj.area %}) \
{% raw ui.title(obj.title) %}
{% raw ui.status(obj.status) %} - \
{% raw ui.priority(obj.priority) %} - \
{% raw ui.darkgray(obj.milestone) %} - \
Opened by {% raw ui.yellow(obj.opened_by.fullname) %} - \
Assigned to {% raw ui.red(obj.assigned_to) %}
{% if obj.parent_id %}Parent {{ obj.parent_id }} {% end %}\
{% if obj.children_ids %}Children {{ obj.children_ids }} {% end %}\
{% if obj.related_ids %}See also {{ obj.related_ids }}{% end %}
{% raw ui.boldwhite(obj.permalink) %}
{{ ui.hl1}}
{% for event in obj.events %}
{{ ui.hl2 }}
{% raw event %}{% end %}
''')

    def __init__(self, case):
        self._case = case
        set_current_case(self)

    def reset(self):
        self._case = self._get_raw(self.id)
        set_current_case(self)

    @classmethod
    def get_by_id(cls, ixBug):
        raw = FBCase._get_raw(ixBug)
        return cls(raw)

    @staticmethod
    def _get_raw(ixBug):
        cols = [
            'ixBug',
            'sTitle',
            'sStatus',
            'sPersonAssignedTo',
            'sPriority',
            'sProject',
            'sArea',
            'sFixFor',
            'ixPersonOpenedBy',
            'ixBugParent',
            'ixBugChildren',
            'ixRelatedBugs',
            'tags',
            'events',
        ]
        raw = FB.search(q=int(ixBug), cols=','.join(cols))
        count = int(raw.cases.get('count'))
        assert count != 0, 'Cannot find case {}'.format(ixBug)
        assert count == 1, 'Found too many cases with ixBug=={}'.format(ixBug)
        return raw

    @property
    def id(self):
        return int(self._case.ixBug.get_text(strip=True))

    @property
    def title(self):
        return self._case.sTitle.get_text(strip=True)

    @property
    def status(self):
        return self._case.sStatus.get_text(strip=True)

    @property
    def priority(self):
        return self._case.sPriority.get_text(strip=True)

    @property
    def project(self):
        return self._case.sProject.get_text(strip=True)

    @property
    def area(self):
        return self._case.sArea.get_text(strip=True)

    @property
    def assigned_to(self):
        return self._case.sPersonAssignedTo.get_text(strip=True)

    @property
    def opened_by_id(self):
        return int(self._case.ixPersonOpenedBy.get_text(strip=True))

    @property
    def opened_by(self):
        return FBPerson.get_by_id(self.opened_by_id)

    @property
    def milestone(self):
        return self._case.sFixFor.get_text(strip=True)

    @property
    def parent_id(self):
        return int(self._case.ixBugParent.get_text(strip=True))

    @property
    def children_ids(self):
        return list(map(
            int,
            filter(None, self._case.ixBugChildren.get_text(
                strip=True).split(','))))

    @property
    def related_ids(self):
        return list(map(
            int,
            filter(None, self._case.ixRelatedBugs.get_text(
                strip=True).split(','))))

    @property
    def events(self):
        return [FBBugEvent(event) for event in self._case.events]

    @property
    def last_event(self):
        return self.events[-1]

    @property
    def attachments(self):
        attachments = []
        for event in self.events:
            attachments.extend(event.attachments)
        return attachments

    @property
    def links(self):
        ilink, links = 0, []
        for event in self.events:
            for url in event.urls:
                link = FBLink(ilink, url)
                ilink += 1
                links.append(link)
        return links

    @property
    def tags(self):
        return self._case.tags.get_text(strip=True).split(',')

    @property
    def operations(self):
        ops = self._case.case.get('operations')
        return ops.split(',') if ops else []

    @property
    def permalink(self):
        return FB.full_url('f/cases/{}'.format(self.id))

    @property
    def shortdesc(self):
        return '[{}] {}'.format(
            self.id,
            self.title)

    _checkins = None

    @property
    def checkins(self):
        if self._checkins is None:
            self._checkins = []
            data = FB.checkins(self.id)
            for i, v in enumerate(six.itervalues(data['changesets'])):
                checkin = FBCheckin(i, v)
                self._checkins.append(checkin)
        return self._checkins

    @staticmethod
    def _clean_kwargs(kwargs):
        # Empty sEvent is rendered as 'None': no need to submit
        if 'sEvent' in kwargs:
            if not kwargs['sEvent']:
                del kwargs['sEvent']
        return kwargs

    def assert_operation(self, op):
        assert op in self.operations, 'Invalid operation {}: not in {}'.format(
            op, self.operations)

    def edit(self, **kwargs):
        self.assert_operation('edit')
        FB.edit(
            ixBug=self.id, ixPersonEditedBy=CURRENT_USER.id,
            **self._clean_kwargs(kwargs))
        self.reset()

    # def amend(self, **kwargs):
    #     self.assert_operation('edit')
    #     FB.edit(
    #         ixBug=self.id, ixPersonEditedBy=CURRENT_USER.id,
    #         ixBugEvent=self.last_event.id,
    #         **self._clean_kwargs(kwargs))
    #     self.reset()

    def resolve(self, **kwargs):
        self.assert_operation('resolve')
        FB.resolve(
            ixBug=self.id, ixPersonEditedBy=CURRENT_USER.id,
            **self._clean_kwargs(kwargs))
        self.reset()

    def reopen(self, **kwargs):
        self.assert_operation('reopen')
        FB.reopen(
            ixBug=self.id, ixPersonEditedBy=CURRENT_USER.id,
            **self._clean_kwargs(kwargs))
        self.reset()

    def reactivate(self, **kwargs):
        self.assert_operation('reactivate')
        FB.reactivate(
            ixBug=self.id, ixPersonEditedBy=CURRENT_USER.id,
            **self._clean_kwargs(kwargs))
        self.reset()

    def assign(self, person, **kwargs):
        self.assert_operation('assign')
        FB.assign(
            ixBug=self.id, ixPersonEditedBy=CURRENT_USER.id,
            sPersonAssignedTo=person,
            **self._clean_kwargs(kwargs))
        self.reset()

    def close(self, **kwargs):
        self.assert_operation('close')
        FB.close(
            ixBug=self.id, ixPersonEditedBy=CURRENT_USER.id,
            **self._clean_kwargs(kwargs))
        self.reset()

    def browse(self):
        browser.browse(self.permalink)

    @classmethod
    def new(cls, **kwargs):
        rs = FB.new(**kwargs)
        ixbug = rs.find('case')['ixBug']
        return cls.get_by_id(ixbug)


class FBLink(FBObj):

    TMPL = Template(
        '''{{ ui.linkid(obj.id) }} {% raw ui.magenta(obj.url) %}''')

    def __init__(self, id_, url):
        self.id = id_
        self.url = url

    def browse(self):
        browser.browse(self.url)


class FBAttachment(FBObj):

    TMPL = Template(
        '''{{ ui.attachmentid(obj.id) }} {{ ui.magenta(obj.filename) }}''')

    def __init__(self, attachment):
        self._attachment = attachment

    @property
    def id(self):
        url = urllib.parse.urlparse(self.url)
        q = urllib.parse.parse_qs(url.query)
        return int(q['ixAttachment'][0])

    @property
    def filename(self):
        return self._attachment.sFileName.get_text(strip=True)

    @property
    def url(self):
        url = self._attachment.sURL.get_text(strip=True).replace('&amp;', '&')
        return FB.full_url(url)

    def download(self):
        url = self.url + '&token={}'.format(FB.current_token)
        r = urllib.request.urlopen(url)
        assert r.getcode() == 200, 'Failed to download {}'.format(url)

        fname = os.path.join(tempfile.gettempdir(), self.filename)
        with open(fname, 'wb') as fid:
            fid.write(r.read())
        print('Saved to', fname)
        xdg_open(fname)


class FBBugEvent(FBObj):

    TMPL = Template(
        '''{{ ui.eventid(obj.id) }} {{ obj.dt }} - {{ obj.person }}
{% raw ui.boldwhite(ui.html_unescape(obj.desc)) %} \
{% for change in obj.changes %}
{% raw ui.darkgray(' - ' + change) %}{% end %}
{% raw obj.comment %}{% if obj.attachments %}{% for a in obj.attachments %}
{% raw a %}{% end %}{% end %}
''')

    def __init__(self, event):
        self._event = event

    @property
    def id(self):
        return int(self._event.ixBugEvent.get_text(strip=True))

    @property
    def dt(self):
        return self._event.dt.get_text(strip=True)

    @property
    def person(self):
        return self._event.sPerson.get_text(strip=True)

    @property
    def desc(self):
        return self._event.evtDescription.get_text(strip=True)

    @property
    def changes(self):
        return filter(None, [
            c.strip()
            for c in self._event.sChanges.get_text(strip=True).splitlines()
        ])

    @property
    def comment(self):
        return self._event.s.get_text(strip=True)

    @property
    def urls(self):
        return URL_RE.findall(self.comment)

    @property
    def attachments(self):
        return [FBAttachment(a) for a in self._event.findAll('attachment')]


class FBShortCase(FBObj):

    TMPL = Template(
        '''{% raw ui.caseid(obj.id, rjust=8) %} \
{% raw ui.priority(ui.rtrunc(obj.priority, 20)) %} \
{% raw ui.status(ui.ltrunc(obj.status, 15)) %} \
{% raw ui.darkgray(ui.rtrunc(obj.project, 15)) %} \
{% raw ui.title(obj.title) %}''')

    # Keep a history of visited cases, in short form
    HISTORY = History()

    def __init__(self, case):
        self._case = case

    @classmethod
    def from_case(cls, case):
        return cls.from_xml(case._case)  # pylint: disable=W0212

    @classmethod
    def from_xml(cls, case):
        return cls(case)

    @property
    def id(self):
        return int(self._case.ixBug.get_text(strip=True))

    @property
    def status(self):
        return self._case.sStatus.get_text(strip=True)

    @property
    def title(self):
        return self._case.sTitle.get_text(strip=True)

    @property
    def project(self):
        return self._case.sProject.get_text(strip=True)

    @property
    def priority(self):
        return self._case.sPriority.get_text(strip=True)

    @property
    def priority_id(self):
        return int(self._case.ixPriority.get_text(strip=True))

    def __eq__(self, case):
        return self.id == case.id


class FBCaseSearch(FBObj):

    TMPL = Template('''
{% for case in obj.shortcases %}{% raw case %}
{% end %}
{{ len(obj.shortcases) }} case(s) found.
''')

    logger = logging.getLogger('fb.search')

    def __init__(self, shortcases):
        self.shortcases = sorted(
            shortcases, key=lambda p: (p.priority_id, p.project, p.id))
        set_last_search(self)

    @classmethod
    def search(cls, q):
        cls.logger.debug('Searching for %r', q)
        cases = {}
        resp = FB.search(
            q=q, cols="ixBug,sTitle,sStatus,sProject,sPriority,ixPriority")
        for case in resp.cases.findAll('case'):
            cobj = FBShortCase.from_xml(case)
            cases[cobj.id] = cobj
        return cls(cases.values())


class FBProject(FBObj):

    TMPL = Template('''{% raw ui.rtrunc(obj.name, 30) %} \
{% raw ui.darkgray(obj.owner) %}''')

    def __init__(self, project):
        self._project = project

    @classmethod
    def get_all(cls):
        result = FB.listProjects()
        return sorted(
            [cls(pxml) for pxml in result.findAll('project')],
            key=lambda p: p.name)

    @property
    def id(self):
        return int(self._project.ixProject.get_text(strip=True))

    @property
    def name(self):
        return self._project.sProject.get_text(strip=True)

    @property
    def owner(self):
        return self._project.sPersonOwner.get_text(strip=True)


class FBArea(FBObj):

    TMPL = Template('''{% raw ui.darkgray(ui.rtrunc(obj.project, 30)) %} \
{% raw ui.ltrunc(obj.name, 30) %}''')

    def __init__(self, area):
        self._area = area

    @property
    def id(self):
        return int(self._area.ixArea.get_text(strip=True))

    @property
    def name(self):
        return self._area.sArea.get_text(strip=True)

    @property
    def project(self):
        return self._area.sProject.get_text(strip=True)


class FBMilestone(FBObj):
    TMPL = Template('''{% raw ui.darkgray(ui.rtrunc(obj.project, 30)) %} \
{% raw obj.name %}''')

    def __init__(self, milestone):
        self._milestone = milestone

    @property
    def id(self):
        return int(self._milestone.ixFixFor.get_text(strip=True))

    @property
    def name(self):
        return self._milestone.sFixFor.get_text(strip=True)

    @property
    def project(self):
        return self._milestone.sProject.get_text(strip=True)


class FBCheckin(FBObj):

    TMPL = Template('''{{ ui.linkid(obj.id) }} {% raw ui.magenta(obj.url) %}
{% raw ui.cyan(obj.date) %} {% raw ui.boldwhite(obj.author) %} \
{% raw ui.white(obj.desc) %}
''')

    def __init__(self, id_, data):
        self.id = id_
        self._data = data

    @staticmethod
    def _soup(html):
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, 'lxml')

    @property
    def url(self):
        return self._data.get('sUrl', 'n/a').strip()

    @property
    def author(self):
        html = self._data.get('sAuthor') or 'n/a'
        return self._soup(html).text.strip()

    @property
    def date(self):
        html = self._data.get('sDate') or 'n/a'
        return self._soup(html).text.strip()

    @property
    def desc(self):
        html = self._data.get('sDesc') or self._data.get('sDescShort') or 'n/a'
        return self._soup(html).text.strip()

    def browse(self):
        browser.browse(self.url)


def get_prompt():
    p = ui.cyan('>>> ', readline_safe=True)
    if CURRENT_CASE is not None:
        p = ui.caseid(CURRENT_CASE.id, readline_safe=True) + ' ' + p
    return p


@command('logon')
def logon():
    '''Logon to FB API.

    Uses $FBURL, $FBUSER and $FBPASS, otherwise prompts for them.

    Example:
    >>> logon
    '''
    logger.debug('Logging on')
    FB.login()
    return set_current_user(FBPerson.get_by_email(FB.current_user))


@command('logoff')
def logoff():
    '''Logoff from FB API.

    Example:
    >>> logoff
    '''
    FB.logoff()
    return set_current_user(None)


@command('help')
def help_(*args):
    '''Show help.

    Example:
    >>> help
    >>> help logon
    '''
    if len(args) == 0:
        print()
        print('Available commands:')
        for name, cmd in sorted(COMMANDS.items()):
            print('{} - {}'.format(name.rjust(12), cmd.desc()))
        print()
        print('Aliases:')
        for name, cmd in sorted(ALIASES.items()):
            print('{} - {}'.format(name.rjust(12), cmd.desc()))
        print()
        print('Type "help <cmd>" for more.')
        print()
    else:
        name = args[0]
        if name in COMMANDS:
            print(COMMANDS[name].help())
        elif name in ALIASES:
            print(ALIASES[name].help())


@command('whoami')
def whoami():
    '''Shows the current user.

    Example:
    >>> whoami
    '''
    print(CURRENT_USER)


@command('show')
def show(ixBug=None):
    '''Show the current ticket.

    Example:
    >>> show  # shows the current ticket, without refreshing it
    >>> show 1234  # shows ticket 1234
    '''
    if ixBug is None:
        assert_current()
        print(CURRENT_CASE)
    else:
        case = FBCase.get_by_id(int(ixBug))
        print(case)


@command('reload')
def reload_():
    '''Reload current ticket.

    Example:
    >>> reload
    '''
    assert_current()
    show(CURRENT_CASE.id)


@command('close')
def close():
    '''Close the current ticket.'''
    assert_operation('close')
    with editor.maybe_writing('Add a comment?') as text:
        params = text.get_params_for_comment() if text else {}
        CURRENT_CASE.close(**params)


@command('reactivate')
def reactivate():
    '''Reactivate the current ticket.'''
    assert_operation('reactivate')
    with editor.maybe_writing('Add a comment?') as text:
        params = text.get_params_for_comment() if text else {}
        CURRENT_CASE.reactivate(**params)


@command('wontfix')
def wontfix():
    '''Resolve the current ticket as "won't fix".'''
    assert_operation('resolve')
    with editor.maybe_writing('Add a comment?') as text:
        params = text.get_params_for_comment() if text else {}
        params['ixstatus'] = FBStatus.get_by_name("Resolved (Won't Fix)").id
        CURRENT_CASE.resolve(**params)


@command('duplicate')
def duplicate():
    '''Resolve the current ticket as "duplicate".'''
    assert_operation('resolve')
    with editor.maybe_writing('Add a comment?') as text:
        params = text.get_params_for_comment() if text else {}
        params['ixstatus'] = FBStatus.get_by_name("Resolved (Duplicate)").id
        CURRENT_CASE.resolve(**params)


@command('resolve')
def resolve():
    '''Resolve the current ticket.'''
    assert_operation('resolve')
    with editor.maybe_writing('Add a comment?') as text:
        params = text.get_params_for_comment() if text else {}
        CURRENT_CASE.resolve(**params)


@command('reopen')
def reopen():
    '''Reopen the current ticket.'''
    assert_operation('reopen')
    with editor.maybe_writing('Add a comment?') as text:
        params = text.get_params_for_comment() if text else {}
        CURRENT_CASE.reopen(**params)


@command('assign')
def assign(*args):
    '''Assign the current ticket to someone.

    Note: `person` must be the person's full name. See command
    `people` for a list of persons.

    Example:
    >>> assign <person>
    >>> assign Lorenzo Bolla
    '''
    assert_operation('assign')
    assert len(args) > 0, 'No assignee'
    person = ' '.join(args)
    with editor.maybe_writing('Add a comment?') as text:
        params = text.get_params_for_comment() if text else {}
        CURRENT_CASE.assign(person, **params)


@command('comment')
def comment():
    '''Add a comment to the current ticket.

    Call $EDITOR to write the comment.

    Example:
    >>> comment
    '''
    assert_current()
    with editor.writing() as text:
        editor.abort_if_empty(text)
        params = text.get_params_for_comment()
        CURRENT_CASE.edit(**params)


@command('reply')
def reply(*args):
    '''Reply to comment.

    Call $EDITOR to write the comment and add the past comment, quoted.

    Example:
    >>> reply  # reply to latest
    >>> reply 1234  # reply to specific comment
    '''
    assert_current()

    if not args:
        event = CURRENT_CASE.events[-1]
    else:
        event_id = args[0]
        all_events = {
            e.id: e for e in CURRENT_CASE.events
        }
        event = all_events[int(event_id)]

    assert event.comment, 'Empty event'
    header = '\n'.join(
        '> {}'.format(line)
        for line in event.comment.splitlines()
    ) + '\n\n'
    with editor.writing(header) as text:
        editor.abort_if_empty(text)
        params = text.get_params_for_comment()
        CURRENT_CASE.edit(**params)


@command('search')
def search(*args):
    '''Search for cases.

    Example:
    >>> search carmax
    >>> search assignedTo:"Lorenzo Bolla" status:Active
    >>> search tag:answexd
    >>> search assignedTo:me project:brandindex
    '''
    q = ' '.join(args)
    rs = FBCaseSearch.search(q)
    print(rs)


@command('browse')
def browse():
    '''Browse current case in $BROWSER.

    Example:
    >>> browse
    >>> b
    '''
    assert_current()
    CURRENT_CASE.browse()


@command('new')
def new():
    '''Create a new ticket.

    $EDITOR will be opened and used to edit the case. The case
    template has an "header" in .yaml format. "Title", "Project",
    "Area", "Files", etc. are all available fields.
    The body of the ticket is separated by "---".

    Example:
    >>> new
    '''

    tmpl = Template('''Title: <title>
Project: <project>
# Area: <area>
# Assign to: {{ user.fullname }}
# Priority: Need to fix
# Parent: <id>
# Milestone: Infrastructure and Internal Errors
# Tags: <list>

---

<Insert description here>

''')  # noqa

    header = tmpl.generate(user=CURRENT_USER).decode('utf-8')
    with editor.writing(header=header) as text:
        editor.abort_if_empty(text)
        params = text.get_params_for_new()
        FBCase.new(**params)


@command('projects')
def projects():
    '''List projects.

    Example:
    >>> projects
    '''
    print()
    for p in FBProject.get_all():
        print(p)
    print()


@command('areas')
def areas(*args):
    '''List areas.

    Example:
    >>> areas  # List all areas
    >>> areas devops  # List areas in devops project
    '''
    result = FB.listAreas()
    areas = [FBArea(a) for a in result.findAll('area')]
    if len(args) > 0:
        project = args[0].lower()
        areas = [a for a in areas if a.project.lower() == project]

    print()
    for area in sorted(areas, key=lambda a: (a.project, a.name)):
        print(area)
    print()


@command('milestones')
def milestones(*args):
    '''List milestones.

    Example:
    >>> milestones
    >>> milestones brandindex
    '''

    result = FB.listFixFors()
    milestones = [FBMilestone(m) for m in result.findAll('fixfor')]
    if len(args) > 0:
        project = args[0].lower()
        milestones = [m for m in milestones if m.project.lower() == project]

    print()
    for milestone in sorted(milestones, key=lambda m: (m.project, m.name)):
        print(milestone)
    print()


@command('people')
def people():
    '''List people.

    Example:
    >>> people
    '''
    print()
    for person in FBPerson.get_all():
        print(person)
    print()


@command('attachments')
def attachments():
    '''List attachments in current case.

    Example:
    >>> attachments
    '''
    assert_current()
    if CURRENT_CASE.attachments:
        print()
        for a in CURRENT_CASE.attachments:
            print(a)
        print()
    else:
        print('No attachments.')


@command('attachment')
def attachment(attachment_id):
    '''Download attachment id.

    Example:
    >>> attachment 1234  # download and view attachment 1234
    '''
    assert_current()
    for a in CURRENT_CASE.attachments:
        if a.id == int(attachment_id):
            a.download()
            break
    else:
        assert False, 'Attachment not found in current case'


@command('links')
def links():
    '''Show all links in current case.'''
    assert_current()
    if len(CURRENT_CASE.links) > 0:
        print()
        for link in CURRENT_CASE.links:
            print(link)
        print()
    else:
        print('No links.')


@command('link')
def link(ilink):
    '''Browse link in current case.'''
    assert_current()
    ilink = int(ilink)
    assert ilink >= 0, 'Negative link index'
    assert ilink < len(CURRENT_CASE.links), 'No such link'
    CURRENT_CASE.links[ilink].browse()


@command('operations')
def operations():
    '''Show valid operations that can be done on current ticket.'''
    assert_current()
    print('Valid operations: {}\nNot all implemented, yet.'.format(
        ' '.join(CURRENT_CASE.operations)))


# @command('amend')
# def amend():
#     '''Amend last comment.

#     Example:
#     >>> amend
# '''
#     assert_current()
#     body = CURRENT_CASE.last_event.comment + '\n\n'
#     with editor.writing(header=body) as text:
#         editor.abort_if_empty(text)
#         params = text.get_params_for_comment()
#         CURRENT_CASE.amend(**params)


def _parse_kwargs(args_):
    kwargs = {}
    if not args_:
        return kwargs
    line = ' '.join(args_)
    for kv in line.split(','):
        k, v = kv.split('=')
        kwargs[k.strip()] = v.strip()
    return kwargs


@command('edit')
def edit(*args):
    '''Generic edit of current case.

    Example:
    >>> edit sFixFor=ASAP
    >>> edit ixBugParent=1234
    >>> edit sTags=mytag
    >>> edit sStatus=testing
'''
    assert_operation('edit')
    kwargs = _parse_kwargs(args)
    CURRENT_CASE.edit(**kwargs)


@command('raw')
def raw(*args):
    '''Execute a command on FB API and return raw result.

    Example:
    >>> raw search q=1  # executes FB.search(q="1")
    >>> raw search q=1, cols=events  # executes FB.search(q="1", cols="events")

    Mostly used for debugging.'''
    cmd, args_ = args[0], args[1:]
    kwargs = _parse_kwargs(args_)
    result = getattr(FB, cmd)(**kwargs)
    print(result.prettify())


@command('history')
def history():
    '''Show the most recently viewed cases, most recent first.'''
    print(FBShortCase.HISTORY)


@command('lastsearch')
def lastsearch():
    '''Show the last search.'''
    if LAST_SEARCH:
        print(LAST_SEARCH)


@command('back')
def previous_case():
    '''Show the previous in history.'''
    case = FBShortCase.HISTORY.back()
    if case is None:
        print("No previous case")
    else:
        show(case.id)


@command('checkins')
def checkins():
    '''Print code checkins associated with current case.'''
    assert_current()
    if len(CURRENT_CASE.checkins) > 0:
        print()
        for checkin in CURRENT_CASE.checkins:
            print(checkin)
        print()
    else:
        print('No checkins.')


@command('checkin')
def checkin(icheckin):
    '''Browse to a specific checkin.'''
    assert_current()
    icheckin = int(icheckin)
    assert icheckin >= 0, 'Negative checkin index'
    assert icheckin < len(CURRENT_CASE.checkins), 'No such checkin'
    CURRENT_CASE.checkins[icheckin].browse()


@command('ipython')
def ipython():
    '''Superpowers!

    Inside the IPython shell you have access to all the internals of
    the REPL, in particular:
        FB: is the Fogbugz client
        CURRENT_CASE: is the current case
        CURRENT_USER: is the current user
'''

    import IPython
    with ui.no_readline_ctx():
        IPython.embed()


@command('quit')
def quit_():
    '''Quit.

    Example:
    >>> quit
    '''
    print('Bye!')
    sys.exit(0)


def welcome():
    print('''
Welcome to FogBugz CLI!

Type "help" to get started.
''')


def create_aliases():
    '''Create command aliases.

    User-defined aliases are read from an ini file located in
    $HOME/.fbrc or in the current directory.

    Example of .fbrc file:

        [aliases]
        myalias = search assignedto:me status:open

    '''

    # Default aliases
    alias('?', 'help')
    alias('b', 'browse')
    alias('bye', 'quit')
    alias('c', 'comment')
    alias('exit', 'quit')
    alias('h', 'history')
    alias('login', 'logon')
    alias('logout', 'logoff')
    alias('mycases', 'search assignedTo:me status:open')
    alias('r', 'reload')
    alias('s', 'show')

    # User-defined aliases
    cp = configparser.ConfigParser()
    # Look in various places
    cp.read([
        '/etc/fbrc',
        os.path.expanduser('~/.fbrc'),
        os.getcwd(),
    ])
    if cp.has_section('aliases'):
        for name in cp.options('aliases'):
            cmdline = cp.get('aliases', name)
            alias(name, cmdline)


# Create aliases immediately
create_aliases()


def _warmup():
    logger.debug('Loading people')
    FBPerson.get_all()


def read_():
    cmdline = input(get_prompt())
    if not cmdline or cmdline.startswith(editor.COMMENT_CHAR):
        return None, None
    tokens = cmdline.split()
    cmd, args = tokens[0], tokens[1:]
    return cmd, args


def assert_current():
    assert CURRENT_CASE is not None, 'Pick a case first!'


def assert_operation(op):
    assert_current()
    CURRENT_CASE.assert_operation(op)


def exec_(cmd, args):

    if cmd.isdigit():
        show(cmd)

    elif cmd in ALIASES:
        ALIASES[cmd](*args)

    else:
        f = COMMANDS.get(cmd)
        assert f is not None, 'Unknown command {}'.format(cmd)
        return f(*args)


def _format_exception(exc):
    if isinstance(exc, errors.Aborted):
        print('Aborted.')
    elif isinstance(exc, yaml.error.YAMLError):
        logger.exception('ERROR in case header: must be valid YAML')
    else:
        logger.exception('ERROR')


@contextlib.contextmanager
def exec_ctx():
    try:
        yield
    except EOFError:
        quit_()
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # pylint: disable=broad-except
        _format_exception(exc)


def main():
    ui.init_readline()
    args = parse_command_line()

    logon()
    _warmup()
    welcome()

    if args:
        with exec_ctx():
            exec_(args[0], args[1:])

    try:
        while True:
            with exec_ctx():
                cmd, args = read_()
                if cmd is None:
                    continue
                exec_(cmd, args)
    finally:
        logoff()


if __name__ == '__main__':
    main()
