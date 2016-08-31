from functools import wraps
import getpass
import json
import logging
import os
import importlib

from six.moves import input  # pylint: disable=redefined-builtin
from six.moves.urllib_parse import urljoin
from six.moves.urllib.request import Request, urlopen

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

    def checkins(self, ixbug):
        '''The API does not provide a call for this.'''
        kilnhg_url = self._fburl.replace('.fogbugz.', '.kilnhg.')
        base_url = urljoin(kilnhg_url, '/fogbugz/casecheckins/{}?token={}')
        url = base_url.format(ixbug, self.current_token)
        r = urlopen(url)
        assert r.code == 200
        return json.loads(r.read().decode())

    def notify(self, ixbug, ixbugeventlatest, ixPerson):
        base_url = self.full_url('/f/api/0/cases/{}?token={}')
        url = base_url.format(ixbug, self.current_token)
        payload = json.dumps({
            'ixBug': ixbug,
            'rgixNotify': [ixPerson],
            'ixBugEventLatest': ixbugeventlatest,
            'sCommand': "edit",
            'fCloseCase': False,
            'rgAttachments': [],
            'sEvent': "",
            'sFormat': "plain",
            'tags': [],
        }).encode()
        req = Request(url, data=payload, headers={
            'Content-Length': len(payload),
            'Content-Type': 'application/json',
        })
        r = urlopen(req)
        assert r.code == 200
        return json.loads(r.read().decode())
