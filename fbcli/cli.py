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
from lazy_property import LazyProperty as property

from tornado.template import Template
from tornado.options import parse_command_line
import yaml

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
URL_RE = re.compile(r'\bhttp[s]?://[^\b \n\r\(\)\[\]\{\},]*')

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
        call(
            'xdg-open {} 1> /dev/null 2> /dev/null'.format(re.escape(what)),
            shell=True)


def xclip(what):
    retval = call('which xclip > /dev/null', shell=True)
    if retval != 0:
        logging.warning('Cannot clip: No xclip available')
    else:
        call(
            'echo "{}" | xclip -selection c'.format(what),
            shell=True)


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

    def to_string(self, tmpl=None):
        if tmpl is None:
            tmpl = self.TMPL
        return tmpl.generate(
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

    @staticmethod
    def _soup(html):
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, 'lxml')


class FBStatus(FBObj):

    TMPL = Template('''{% raw obj.name %}''')
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

    @classmethod
    def get_by_category_id(cls, category_id):
        if not cls.CACHE:
            cls.get_all()
        ss = list()
        for s in cls.CACHE:
            if category_id == s.category_id:
                ss.append(s)
        return ss

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

    @property
    def category_id(self):
        return int(self._status.ixCategory.get_text(strip=True))


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
    def get_by_guess(cls, what):
        what = what.strip()
        try:
            return cls.get_by_id(int(what))
        except ValueError:
            pass

        if '@' in what or what == what.lower():
            return cls.get_by_email(what)

        return cls.get_by_fullname(what)

    @classmethod
    def get_by_email(cls, email):
        for p in cls.CACHE:
            if p.email == email:
                return p
        return cls._get(sEmail=email)

    @classmethod
    def get_by_fullname(cls, fullname):
        for p in cls.CACHE:
            if p.fullname == fullname:
                return p
        return cls._get(sFullname=fullname)

    @classmethod
    def get_by_id(cls, person_id):
        for p in cls.CACHE:
            if p.id == person_id:
                return p
        return cls._get(ixPerson=person_id)

    @staticmethod
    def get_all():
        result = FB.listPeople()
        return sorted(
            [FBPerson(a) for a in result.findAll('person')],
            key=lambda p: (p.fullname.lower(), p.email.lower()))

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

    TMPL_HEADER_TEXT = '''
{{ ui.hl1 }}
{% raw ui.caseid(obj.id) %} ({% raw obj.project %}/{% raw obj.area %}) \
{% raw ui.title(obj.title) %} \
{% for tag in obj.tags %}{{ ui.tag(tag) }}{% end %}
{% raw obj.category %} | \
{% raw ui.status(obj.status) %} | \
{% raw ui.priority(obj.priority) %} | \
{% raw ui.darkgray(obj.milestone) %} | \
Opened by {% raw ui.yellow(obj.opened_by.fullname) %} \
on {% raw obj.dtopened %} | \
Assigned to {% raw ui.red(obj.assigned_to) %}
{% if obj.parent_id %}Parent {% raw ui.caseid(obj.parent_id) %} {% end %}\
{% if obj.children_ids %}Children \
{% raw ' '.join(ui.caseid(c) for c in  obj.children_ids) %} {% end %}\
{% if obj.duplicate_of_id %}Duplicate of \
{% raw ui.caseid(obj.duplicate_of_id) %} {% end %}\
{% if obj.related_ids %}See also \
{% raw ' '.join(ui.caseid(c) for c in  obj.related_ids) %} {% end %}
{% raw ui.boldwhite(obj.permalink) %}
{{ ui.hl1}}
'''
    TMPL_EVENTS_TEXT = '''{% for event in obj.events %}
{{ ui.hl2 }}
{% raw event %}{% end %}
'''

    TMPL = Template(TMPL_HEADER_TEXT + TMPL_EVENTS_TEXT)
    TMPL_HEADER = Template(TMPL_HEADER_TEXT)

    def __init__(self, case):
        self._case = case
        set_current_case(self)

    @classmethod
    def get_by_id(cls, ixBug):
        raw = FBCase._get_raw(ixBug)
        return cls(raw)

    @classmethod
    def get_by_id_or_current(cls, ixBug):
        if ixBug is None:
            assert_current()
            return CURRENT_CASE
        return FBCase.get_by_id(int(ixBug))

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
            'ixCategory',
            'sCategory',
            'ixPersonOpenedBy',
            'ixBugParent',
            'ixBugChildren',
            'ixBugOriginal',
            'ixRelatedBugs',
            'dtOpened',
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
    def dtopened(self):
        return self._case.dtOpened.get_text(strip=True)[:10]

    @property
    def milestone(self):
        return self._case.sFixFor.get_text(strip=True)

    @property
    def parent_id(self):
        return int(self._case.ixBugParent.get_text(strip=True))

    @property
    def category_id(self):
        return int(self._case.ixCategory.get_text(strip=True))

    @property
    def category(self):
        return self._case.sCategory.get_text(strip=True)

    @property
    def available_statuses(self):
        return FBStatus.get_by_category_id(self.category_id)

    @property
    def duplicate_of_id(self):
        id_ = self._case.ixBugOriginal.get_text(strip=True)
        if id_:
            return int(id_)

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
        return [FBBugEvent(self, event) for event in self._case.events]

    @property
    def last_event(self):
        return self.events[-1]

    @property
    def last_event_with_comment(self):
        for event in reversed(self.events):
            if event.raw_comment:
                return event

    def get_event(self, event_id):
        for event in self.events:
            if event.id == int(event_id):
                return event

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
            for pos, url in event.urls:
                link = FBLink(ilink, event, url, pos)
                links.append(link)
                ilink += 1
            for text, url in event.inline_urls:
                link = FBInlineLink(ilink, event, url, text)
                ilink += 1
                links.append(link)
        return links

    @property
    def tags(self):
        return list(
            filter(None, self._case.tags.get_text(strip=True).split(',')))

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

    @property
    def checkins(self):
        checkins = []
        data = FB.checkins(self.id)
        for i, v in enumerate(six.itervalues(data.get('changesets', {}))):
            checkin = FBCheckin(i, v)
            checkins.append(checkin)
        checkins.sort(key=lambda c: c.dtUTC)
        return checkins

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
        if not kwargs:
            return
        self.assert_operation('edit')
        FB.edit(
            ixBug=self.id, ixPersonEditedBy=CURRENT_USER.id,
            **self._clean_kwargs(kwargs))

    def resolve(self, **kwargs):
        self.assert_operation('resolve')
        FB.resolve(
            ixBug=self.id, ixPersonEditedBy=CURRENT_USER.id,
            **self._clean_kwargs(kwargs))

    def reopen(self, **kwargs):
        self.assert_operation('reopen')
        FB.reopen(
            ixBug=self.id, ixPersonEditedBy=CURRENT_USER.id,
            **self._clean_kwargs(kwargs))

    def reactivate(self, **kwargs):
        self.assert_operation('reactivate')
        FB.reactivate(
            ixBug=self.id, ixPersonEditedBy=CURRENT_USER.id,
            **self._clean_kwargs(kwargs))

    def assign(self, person, **kwargs):
        self.assert_operation('assign')
        FB.assign(
            ixBug=self.id, ixPersonEditedBy=CURRENT_USER.id,
            sPersonAssignedTo=person.fullname,
            **self._clean_kwargs(kwargs))

    def notify(self, persons, **kwargs):
        person_ids = [p.id for p in persons]
        FB.notify(CURRENT_CASE.id, CURRENT_CASE.last_event.id, person_ids)
        self.edit(**kwargs)

    def amend(self, event, **kwargs):
        FB.amend(self.id, event.id, self._clean_kwargs(kwargs))

    def close(self, **kwargs):
        self.assert_operation('close')
        FB.close(
            ixBug=self.id, ixPersonEditedBy=CURRENT_USER.id,
            **self._clean_kwargs(kwargs))

    def browse(self):
        xdg_open(self.permalink)
        xclip(self.permalink)

    def mark_as_viewed(self):
        FB.view(ixBug=self.id)

    def header(self):
        return self.to_string(self.TMPL_HEADER)

    @classmethod
    def new(cls, **kwargs):
        rs = FB.new(**kwargs)
        ixbug = rs.find('case')['ixBug']
        return cls.get_by_id(ixbug)


class FBBaseLink(FBObj):

    TMPL = Template(
        '''{{ ui.linkid(obj.id) }} {% raw ui.magenta(obj.url) %}''')

    def __init__(self, id_, event, url):
        self.id = id_
        self.event = event
        self.url = url

    def browse(self):
        xdg_open(self.url)
        xclip(self.url)

    def rewrite(self, text):
        raise NotImplementedError()


class FBLink(FBBaseLink):

    TMPL = Template(
        '''{{ ui.linkid(obj.id) }} {% raw ui.magenta(obj.url) %}''')

    def __init__(self, id_, event, url, pos):
        super(FBLink, self).__init__(id_, event, url)
        self.id = id_
        self.event = event
        self.url = url
        self.pos = pos

    def rewrite(self, text):
        return text[:self.pos] + text[self.pos:].replace(
            self.url, self.to_string(), 1)


class FBInlineLink(FBBaseLink):

    TMPL_TEXT = Template(
        '''{{ ui.linkid(obj.id) }} {% raw ui.magenta(obj.text) %}''')

    def __init__(self, id_, event, url, text):
        super(FBInlineLink, self).__init__(id_, event, url)
        self.text = text

    def rewrite(self, text):
        return text.replace(self.text, self.to_string(self.TMPL_TEXT), 1)


class FBAttachment(FBObj):

    TMPL = Template(
        '''{{ ui.attachmentid(obj.id) }} {{ ui.lightgreen(obj.filename) }} '''
        '''{{ ui.darkgray(obj.url) }}''')

    INVALID_CHARS_RE = re.compile(r'[\/*?|]')

    logger = logging.getLogger('fb.attachment')

    def __init__(self, attachment):
        self._attachment = attachment
        self._parse_url()

    def _parse_url(self):
        url = urllib.parse.urlparse(self.url)
        q = urllib.parse.parse_qs(url.query)
        self._internal = 'ixAttachment' in q
        return q

    @property
    def id(self):
        if self._internal:
            q = self._parse_url()
            return int(q['ixAttachment'][0])
        else:
            return hash(self.url) % 10000

    @property
    def filename(self):
        return self._attachment.sFileName.get_text(strip=True)

    @property
    def url(self):
        url = self._attachment.sURL.get_text(strip=True).replace('&amp;', '&')
        return FB.full_url(url)

    @property
    def safe_filename(self):
        return self.INVALID_CHARS_RE.sub('_', self.filename)

    @property
    def _local_filename(self):
        fname = '{}_{}'.format(self.id, self.safe_filename)
        return os.path.join(tempfile.gettempdir(), fname)

    def download(self):
        url = self.url
        if self._internal:
            url += '&token={}'.format(FB.current_token)

        self.logger.debug('Fetching %s', url)
        r = urllib.request.urlopen(url)
        assert r.getcode() == 200, 'Failed to download {}'.format(url)

        with open(self._local_filename, 'wb') as fid:
            fid.write(r.read())
        print('Saved to', self._local_filename)

    def view(self):
        if os.path.exists(self._local_filename):
            print('Found local file.')
        else:
            self.download()
        xdg_open(self._local_filename)


class FBInlineImg(FBAttachment):

    TMPL = Template(
        '''{{ ui.attachmentid(obj.id) }} {{ ui.green(obj.filename) }} '''
        '''{{ ui.darkgray(obj.url) }}''')

    def __init__(self, url):  # pylint: disable=super-init-not-called
        self._url = url
        url = urllib.parse.urlparse(self.url)
        data = dict(urllib.parse.parse_qsl(url.query))
        if 'sFileName' in data:
            self._internal = True
            self._filename = data['sFileName']
        else:
            self._internal = False
            self._filename = os.path.basename(url.path)

    @property
    def filename(self):
        return self._filename

    @property
    def url(self):
        return FB.full_url(self._url)


class FBBugEvent(FBObj):

    TMPL = Template(
        '''{{ ui.eventid(obj.id) }} {{ obj.dt }} - {{ obj.person }}
{% raw ui.boldwhite(ui.html_unescape(obj.desc)) %} \
{% for change in obj.changes %}
{% raw ui.darkgray(' - ' + change) %}{% end %}
{% raw obj.comment %}{% if obj.attachments %}{% for a in obj.attachments %}
{% raw a %}{% end %}{% end %}
''')

    def __init__(self, fbcase, event):
        self._event = event
        self._fbcase = fbcase

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
        return list(filter(None, [
            c.strip()
            for c in self._event.sChanges.get_text(strip=True).splitlines()
        ]))

    @property
    def raw_comment(self):
        return self._event.s.get_text(strip=True)

    @property
    def comment(self):
        return self._linkify(self.raw_comment)

    def _linkify(self, text):
        for link in self.links:
            text = link.rewrite(text)
        return text

    @property
    def urls(self):
        return [
            (m.start(), m.group())
            for m in URL_RE.finditer(self.raw_comment)
            ]

    @property
    def _attachments(self):
        return [
            FBAttachment(a) for a in self._event.findAll('attachment')
        ]

    @property
    def attachments(self):
        all_attachments = {
            a.id: a for a in self._attachments + self.inline_imgs
        }
        return sorted(all_attachments.values(), key=lambda a: a.id)

    @property
    def links(self):
        return [
            link for link in self._fbcase.links
            if link.event.id == self.id]

    @property
    def inline_imgs(self):
        imgs = []
        if not self._event.sHtml:
            return imgs
        html = self._event.sHtml.get_text(strip=True)
        soup = self._soup(html)
        for img in soup.findAll('img'):
            if 'src' in img.attrs:
                src = img.attrs['src'].strip()
                # Only support http links
                if src.startswith('http'):
                    imgs.append(FBInlineImg(src))
        return imgs

    @property
    def inline_urls(self):
        urls = []
        if not self._event.sHtml:
            return urls
        html = self._event.sHtml.get_text(strip=True)
        soup = self._soup(html)
        for url in soup.findAll('a'):
            href = url.attrs.get('href')
            t = url.text.strip()
            if t and href and t != href:
                urls.append((t, href))
        return urls


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
    def _parse_cases(cls, resp):
        cases = {}
        if resp.cases is not None:
            for case in resp.cases.findAll('case'):
                cobj = FBShortCase.from_xml(case)
                cases[cobj.id] = cobj
        return cls(cases.values())

    @classmethod
    def search(cls, q):
        cls.logger.debug('Searching for %r', q)
        resp = FB.search(
            q=q, cols="ixBug,sTitle,sStatus,sProject,sPriority,ixPriority")
        return cls._parse_cases(resp)

    @classmethod
    def top(cls, n):
        cls.logger.debug('Getting top %d cases', n)
        resp = FB.listCases(
            cols="ixBug,sTitle,sStatus,sProject,sPriority,ixPriority", max=n)
        return cls._parse_cases(resp)


class FBFavoriteCase(FBObj):

    # {
    #     "__type__": "DocumentListItem",
    #     "sType": "Bug",
    #     "sTitle": "Barchart export issueing too many queries",
    #     "ixDiscussGroup": 0,
    #     "ixItem": 45744,
    #     "viewed": true
    # },

    TMPL = Template(
        '''{% raw ui.caseid(obj.id, rjust=8) %} \
{% raw ui.title(obj.title) %}''')

    def __init__(self, data):
        self._data = data

    @property
    def id(self):
        return self._data['ixItem']

    @property
    def title(self):
        return self._data['sTitle']


class FBRecentCase(FBFavoriteCase):
    pass


class FBCaseFavorites(FBObj):

    def __init__(self):
        self._data = FB.favorites()

    @property
    def favorites(self):
        return sorted([
            FBFavoriteCase(data)
            for data in self._data['data']['favorites']
        ], key=lambda c: c.id)

    @property
    def recent(self):
        return [
            FBRecentCase(data)
            for data in self._data['data']['recent']
        ]


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

    @property
    def url(self):
        return self._data.get('sUrl', 'n/a').strip()

    @property
    def author(self):
        html = self._data.get('sAuthor') or 'n/a'
        return self._soup(html).text.strip()

    @property
    def dtUTC(self):
        return self._data.get('dtUTC') or 'n/a'

    @property
    def date(self):
        html = self._data.get('sDate') or 'n/a'
        return self._soup(html).text.strip()

    @property
    def desc(self):
        html = self._data.get('sDesc') or self._data.get('sDescShort') or 'n/a'
        return self._soup(html).text.strip()

    def browse(self):
        xdg_open(self.url)
        xclip(self.url)


def get_prompt():
    p = ui.cyan('>>> ', readline_safe=True)
    if CURRENT_CASE is not None:
        p = ui.caseid(CURRENT_CASE.id, readline_safe=True) + ' ' + p
    return p


def refresh():
    assert_current()
    FBCase.get_by_id_or_current(CURRENT_CASE.id)


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
    FB.logout()
    return set_current_user(None)


@command('help')
def help_(*args):
    '''Show help.

    Example:
    >>> help
    >>> help logon
    '''

    if len(args) == 0:

        width = max(
            len(n) for n in list(COMMANDS.keys()) + list(ALIASES.keys()))
        print()
        print('Available commands:')
        for name, cmd in sorted(COMMANDS.items()):
            print('{} - {}'.format(name.rjust(width), cmd.desc()))
        print()
        print('Aliases:')
        for name, cmd in sorted(ALIASES.items()):
            print('{} - {}'.format(name.rjust(width), cmd.desc()))
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
    case = FBCase.get_by_id_or_current(ixBug)
    print(case)
    if ixBug is not None:
        case.mark_as_viewed()


@command('header')
def header(ixBug=None):
    '''Show the header of the current ticket.

    Example:
    >>> header  # shows the current ticket's header
    >>> header 123  # shows ticket 123's header
    '''
    case = FBCase.get_by_id_or_current(ixBug)
    print(case.header())


@command('parent')
def parent():
    '''Show parent ticket.

    Example:
    >>> parent
    '''
    assert_current()
    if CURRENT_CASE.parent_id > 0:
        show(CURRENT_CASE.parent_id)
    else:
        print('No parent case.')


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
        refresh()


@command('reactivate')
def reactivate():
    '''Reactivate the current ticket.'''
    assert_operation('reactivate')
    with editor.maybe_writing('Add a comment?') as text:
        params = text.get_params_for_comment() if text else {}
        CURRENT_CASE.reactivate(**params)
        refresh()


@command('resolve')
def resolve(*args):
    '''Resolve the current ticket.

    Optionally provide a resolution status. See `statuses` for options.

    Example:
    >>> resolve
    >>> resolve Resolved (Won't Fix)
    '''
    assert_operation('resolve')
    with editor.maybe_writing('Add a comment?') as text:
        params = text.get_params_for_comment() if text else {}
        if args and not params.get('sStatus'):
            params['sStatus'] = ' '.join(args)
        CURRENT_CASE.resolve(**params)
        refresh()


@command('reopen')
def reopen():
    '''Reopen the current ticket.'''
    assert_operation('reopen')
    with editor.maybe_writing('Add a comment?') as text:
        params = text.get_params_for_comment() if text else {}
        CURRENT_CASE.reopen(**params)
        refresh()


@command('duplicate')
def duplicate():
    '''Resolve the current ticket as duplicate.

    Example:
    >>> duplicate 1234
    '''
    assert_operation('resolve')
    # ixdup = int(args[0])
    with editor.maybe_writing('Add a comment?') as text:
        params = text.get_params_for_comment() if text else {}
        params['sStatus'] = 'Resolved (Duplicate)'
        CURRENT_CASE.resolve(**params)
        refresh()
        # TODO not working
        # FB.duplicate(CURRENT_CASE.id, ixdup)


@command('statuses')
def statuses():
    '''Show the possible statuses of the current ticket.'''
    assert_current()
    for s in CURRENT_CASE.available_statuses:
        print(s)


@command('assign')
def assign(*args):
    '''Assign the current ticket to someone.

    Note: `person` must be the person's full name. See command
    `people` for a list of persons.

    Example:
    >>> assign <person>
    >>> assign Lorenzo Bolla
    >>> assign me@example.com
    >>> assign 1234
    '''
    assert_operation('assign')
    assert args, 'No assignee'
    person = FBPerson.get_by_guess(' '.join(args))
    with editor.maybe_writing('Add a comment?') as text:
        params = text.get_params_for_comment() if text else {}
        CURRENT_CASE.assign(person, **params)
        refresh()


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
        refresh()


@command('reply')
def reply(ixBugEvent=None):
    '''Reply to comment.

    Call $EDITOR to write the comment and add the past comment, quoted.

    Example:
    >>> reply  # reply to latest
    >>> reply 1234  # reply to specific comment
    '''
    assert_current()

    if not ixBugEvent:
        event = CURRENT_CASE.last_event_with_comment
    else:
        event = CURRENT_CASE.get_event(ixBugEvent)

    assert event and event.raw_comment, 'Empty event'

    header = 'On {} {} said:\n'.format(event.dt, event.person)
    header += '\n'.join(
        '> {}'.format(line)
        for line in event.raw_comment.splitlines()
    ) + '\n\n'
    with editor.writing(header) as text:
        editor.abort_if_empty(text)
        params = text.get_params_for_comment()
        CURRENT_CASE.edit(**params)
        refresh()


@command('search')
def search(*args):
    '''Search for cases.

    Example:
    >>> search carmax

    You can use '=' to separate keywords:
    >>> search assignedTo=Lorenzo Bolla status=Active
    >>> search tag=answexd

    or ':', but make sure to quote args if necessary:
    >>> search assignedTo:me project:brandindex
    >>> search assignedTo:"Lorenzo Bolla" status:Active

    Using ':' syntax allows to have non-keyword arguments, too:
    >>> search assignedTo:me carmax
    '''

    def kwargs_to_q(kwargs):
        return ' '.join('{}:"{}"'.format(k, v) for k, v in kwargs.items())

    q = ' '.join(args)
    if '=' in q:
        kwargs = _parse_kwargs(args, sep='=')
        q = kwargs_to_q(kwargs)
    rs = FBCaseSearch.search(q)
    print(rs)


@command('top')
def top(n=None):
    '''Show the top n cases (default 10).'''
    if n is None:
        n = 10
    rs = FBCaseSearch.top(n)
    print(rs)


@command('browse')
def browse():
    '''Browse current case in default browser.

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
def people(*args):
    '''List people.

    Example:
    >>> people
    >>> people Albert  # filter
    '''
    q = args[0] if len(args) > 0 else None

    print()
    for person in FBPerson.get_all():
        if q is None or q in person.fullname.lower():
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
    '''View attachment id.

    Example:
    >>> attachment 1234  # download and view attachment 1234
    '''
    assert_current()
    for a in CURRENT_CASE.attachments:
        if a.id == int(attachment_id):
            a.view()
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


def _parse_kwargs(args_, sep='='):
    kwargs = {}
    if not args_:
        return kwargs
    line = ' '.join(args_)
    matches = list(re.finditer(r'\w+' + sep, line))
    if not matches:
        return kwargs

    m0 = matches[0]
    for m1 in matches[1:]:
        k = m0.group().replace(sep, '')
        _s0, e0 = m0.span()
        s1, _e1 = m1.span()
        v = line[e0: s1]
        kwargs[k.strip()] = v.strip()
        m0 = m1

    # Last token
    k = m0.group().replace(sep, '')
    _s0, e0 = m0.span()
    s1 = len(line)
    v = line[e0: s1]
    kwargs[k.strip()] = v.strip()

    return kwargs


def _to_api_kwargs(kwargs):
    translate = {
        'area': 'sArea',
        'fixfor': 'sFixFor',
        'parent': 'ixBugParent',
        'priority': 'sPriority',
        'project': 'sProject',
        'status': 'sStatus',
        'tags': 'sTags',
        'tag': 'sTags',
        'title': 'sTitle',
    }
    return {
        translate.get(k.lower(), k): v for k, v in kwargs.items()
    }


def _api_kwargs(args_):
    return _to_api_kwargs(_parse_kwargs(args_))


@command('edit')
def edit(*args):
    '''Generic edit of current case.

    Example:
    >>> edit sFixFor=ASAP
    >>> edit fixfor=ASAP
    >>> edit ixBugParent=1234
    >>> edit parent=1234
    >>> edit sTags=my tag sStatus=testing
    >>> edit tag=some tag
'''
    assert_operation('edit')
    kwargs = _api_kwargs(args)
    CURRENT_CASE.edit(**kwargs)
    refresh()


@command('raw')
def raw(*args):
    '''Execute a command on FB API and return raw result.

    Example:
    >>> raw search q=1  # executes FB.search(q="1")
    >>> raw search q=1 cols=events  # executes FB.search(q="1", cols="events")

    Mostly used for debugging.'''
    cmd, args_ = args[0], args[1:]
    kwargs = _api_kwargs(args_)
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
    for c in CURRENT_CASE.checkins:
        if c.id == icheckin:
            c.browse()
            return
    assert False, 'Checkin {} not found'.format(icheckin)


@command('notify')
def notify(*args):
    '''Notify people of this ticket.

    Example:
    >>> notify 123  # Search by ID
    >>> notify donald.knuth@example.com  # Search by email
    >>> notify Donald Knuth # Search by full name
    >>> notify 123, me, Somebody Else  # notify many people
    '''
    assert_current()

    names = ' '.join(args)
    persons = [
        FBPerson.get_by_guess(name)
        for name in names.split(',')
    ]
    persons = {
        p.id: p
        for p in persons
        if p.id != CURRENT_USER.id
    }
    assert persons, 'No persons to notify'
    with editor.maybe_writing('Add a comment?') as text:
        params = text.get_params_for_comment() if text else {}
        CURRENT_CASE.notify(persons.values(), **params)
        refresh()


@command('amend')
def amend(ixBugEvent=None):
    '''Amend comment (last by default).

    Example:
    >>> amend  # amend last comment
    >>> amend 1234  # amend specific bug event
'''
    assert_current()

    if not ixBugEvent:
        event = CURRENT_CASE.last_event_with_comment
    else:
        event = CURRENT_CASE.get_event(ixBugEvent)

    body = event.raw_comment + '\n\n'
    with editor.writing(header=body) as text:
        editor.abort_if_empty(text)
        params = text.get_params_for_amend()
        CURRENT_CASE.amend(event, **params)
        refresh()


@command('favorites')
def favorites():
    '''Get favorite cases.'''

    fs = FBCaseFavorites()
    if not fs.favorites:
        print('No favorite cases.')
        return
    print()
    for case in fs.favorites:
        print(case)
    print()


@command('favorite')
def favorite(ixBug=None):
    '''Favorite case.'''

    case = FBCase.get_by_id_or_current(ixBug)
    FB.favorite(case.id, case.category)
    print('OK')


@command('unfavorite')
def unfavorite(ixBug=None):
    '''Unfavorite case.'''

    case = FBCase.get_by_id_or_current(ixBug)
    FB.unfavorite(case.id, case.category)
    print('OK')


@command('recent')
def recent(n=10):
    '''Get recent `n` cases.'''

    fs = FBCaseFavorites()
    if not fs.recent:
        print('No recent cases.')
        return
    print()
    for case in fs.recent[:int(n)]:
        print(case)
    print()


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
    alias('sh', 'header')
    alias('star', 'favorite')
    alias('starred', 'favorites')
    alias('unstar', 'unfavorite')

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
