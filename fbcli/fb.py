from copy import deepcopy
from functools import wraps
import getpass
import json
import logging
import os
import importlib

import requests
from six.moves import input  # pylint: disable=redefined-builtin
from six.moves.urllib_parse import urljoin

import fogbugz


RETRY_ON_EXCS = (
    fogbugz.FogBugzLogonError,
)


def from_env_or_ask(k, question, is_password=False):
    what = os.environ.get(k)
    if what is not None:
        return what
    print('You can skip this question by setting ${}'.format(k))
    if is_password:
        return getpass.getpass()
    return input(question)


class FBClient(object):

    logger = logging.getLogger('fb.client')

    def __init__(self):
        self.__fb = None

        self._fburl = from_env_or_ask('FBURL', 'Fogbugz URL: ')
        self._fbuser = from_env_or_ask('FBUSER', 'Username: ')

        self._fbtoken = None
        self._fbpass = None

        if 'FBTOKEN' in os.environ:
            self._fbtoken = os.environ['FBTOKEN']
        else:
            self._fbpass = (
                self._password_from_keyring() or
                from_env_or_ask('FBPASS', 'Password: ', True)
            )

    @property
    def uses_token(self):
        return self._fbtoken is not None

    def _password_from_keyring(self):
        try:
            keyring = importlib.import_module('keyring')
        except ImportError:
            return
        return keyring.get_password(self._fburl, self._fbuser)

    @property
    def _fb(self):
        # Get connection lazily, to simplify testing
        if self.__fb is None:
            if self.uses_token:
                self.__fb = fogbugz.FogBugz(self._fburl, self._fbtoken)
            else:
                self.__fb = fogbugz.FogBugz(self._fburl)
        return self.__fb

    def retrying(self, f):

        @wraps(f)
        def helper(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except RETRY_ON_EXCS as exc:
                self.logger.warning('Retrying: %s', exc)
                self.login()
                return helper(*args, **kwargs)

        return helper

    def __getattr__(self, k):
        self.logger.debug(k)
        return self.retrying(getattr(self._fb, k))

    @property
    def current_user(self):
        return self._fbuser

    @property
    def current_token(self):
        return self._fb._token  # pylint: disable=protected-access

    def login(self):
        if not self.uses_token:
            self.logger.debug('Logging in')
            self._fb.logon(self._fbuser, self._fbpass)
        else:
            self.logger.debug('Not logging in: using token')

    def logout(self):
        if not self.uses_token:
            self.logger.debug('Logging out')
            self._fb.logoff()
        else:
            self.logger.debug('Not logging out: using token')

    def full_url(self, path):
        return urljoin(self._fburl, path)

    def full_url_with_token(self, path):
        return urljoin(
            self._fburl, path + '?token={}'.format(self.current_token))

    def checkins(self, ixbug):
        '''The API does not provide a call for this.'''
        kilnhg_url = self._fburl.replace('.fogbugz.', '.kilnhg.')
        base_url = urljoin(kilnhg_url, '/fogbugz/casecheckins/{}?token={}')
        url = base_url.format(ixbug, self.current_token)
        r = requests.get(url)
        r.raise_for_status()
        return r.json()

    def notify(self, ixbug, ixbugeventlatest, ixPerson):
        path = '/f/api/0/cases/{}'.format(ixbug)
        url = self.full_url_with_token(path)
        params = {
            'sCommand': 'edit',
            'sFormat': 'plain',
            'ixBug': ixbug,
            'rgixNotify': [ixPerson],
            'ixBugEventLatest': ixbugeventlatest,
        }

        payload = json.dumps(params)
        r = requests.post(url, data=payload, headers={
            'Content-Type': 'application/json',
        })
        r.raise_for_status()
        return r.json()

    def _http_get_case(self, session, ixbug):
        '''Get case from HTTP API.'''
        path = '/f/api/0/cases/{}'.format(ixbug)
        url = self.full_url_with_token(path)
        r = session.get(url)
        r.raise_for_status()
        return r

    def _http_get_event(self, session, ixbugevent):
        '''Get event from HTTP API.'''
        path = '/f/api/0/caseevents/{}'.format(ixbugevent)
        url = self.full_url_with_token(path)
        r = session.get(url)
        r.raise_for_status()
        return r

    def amend(self, ixbug, ixbugevent, params):
        session = requests.Session()

        # Get the edit history of this case
        r = self._http_get_case(session, ixbug)
        data = r.json()['data']
        ix_bug_event_latest = data['ixBugEventLatest']

        # Find latest edit for the event we are amending
        event_edits = data.get('eventEdits', [])
        all_edits = [-1] + [
            e['ixEdit']
            for e in event_edits if e['ixBugEvent'] == ixbugevent
        ]
        ix_edit = max(all_edits)

        # Get headers (in particular, sUniqueID) from current version,
        # as it's used to make sure nobody changed the ticketin the
        # meantime
        r = self._http_get_event(session, ixbugevent)

        # Finally, POST the update
        params = deepcopy(params)
        params.update({
            'sCommand': 'editEvent',
            'sFormat': 'plain',
            'ixBug': ixbug,
            'ixBugEvent': ixbugevent,
            'ixBugEventLatest': ix_bug_event_latest,
            'ixEditCurrent': ix_edit,
            'rgAttachments': [],
            'rgixAttachmentsToDelete': [],
            'rgsAttachmentsAdded': [],
        })
        payload = json.dumps(params)
        r = session.post(r.url, data=payload, headers={
            'Content-Type': 'application/json',
        })
        if r.ok:
            print('Amended!')
            return True
        else:
            errors = r.json()['errors']
            print('Error!')
            for e in errors:
                print('    {}'.format(e['message']))
            return False

    # TODO not working
    def duplicate(self, ixbug, ixdup):
        session = requests.Session()

        # Get the edit history of this case
        r = self._http_get_case(session, ixbug)
        data = r.json()['data']

        fields = [
            'tags',
            'subcases',
            'sVersion',
            'sTitle',
            'sFormat',
            'sEvent',
            'sCustomerEmail',
            'sComputer',
            'sCommand',
            'rgixNotify',
            'rgAttachments',
            'reactivateTime',
            'ixStatus',
            'ixProject',
            'ixBug',
            'ixArea',
            'hrsElapsedExtra',
            'hrsCurrEst',
            'fCloseCase',
            'dtDue',
            'dblStoryPts',
            'casesDependedOn',
            'ixBugEventLatest',
            'ixBugParent',
            'ixCategory',
            'ixDuplicateOf',
            'ixFixFor',
            'ixKanbanColumn2',
            'ixPersonAssignedTo',
            'ixPriority',
        ]
        params = {k: v for k, v in data.items() if k in fields}
        params.update({
            'sCommand': 'resolve',
            'sFormat': 'plain',
            'ixDuplicateOf': ixdup,
        })

        payload = json.dumps(data)
        r = session.post(r.url, data=payload, headers={
            'Content-Type': 'application/json',
        })
        if r.ok:
            print('OK')
            return True
        else:
            errors = r.json()['errors']
            print('Error!')
            for e in errors:
                print('    {}'.format(e['message']))
            return False

    @staticmethod
    def _raise_on_error(r):
        if not r.ok:
            data = r.json()
            msg = '\n'.join(e['message'] for e in data['errors'])
            raise ValueError(msg)

    def favorites(self):
        '''Get favorite cases.'''
        path = '/f/api/0/favorites/'
        url = self.full_url_with_token(path)
        r = requests.get(url, params={'json': '{}'})
        self._raise_on_error(r)
        return r.json()

    def _favorite(self, action, ixbug, category):
        # I am not sure what sType is supposed to be
        stype_map = {
            'Task': 'Bug',
            'Inquiry': 'Bug',
            'Feature': 'Bug',
        }
        stype = stype_map.get(category, category)
        path = '/f/api/0/favorites/'
        url = self.full_url_with_token(path)
        payload = json.dumps({
            'ixItem': ixbug,
            'sType': stype,
        })
        f = getattr(requests, action)
        r = f(url, data=payload, headers={
            'Content-Type': 'application/json',
        })
        self._raise_on_error(r)
        return r.json()

    def favorite(self, ixbug, category):
        '''Mark a case as favorite.'''
        self._favorite('post', ixbug, category)

    def unfavorite(self, ixbug, category):
        '''Unfavorite a case.'''
        self._favorite('delete', ixbug, category)
