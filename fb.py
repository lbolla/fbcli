from functools import wraps
import getpass
import logging
import os

import fogbugz


RETRY_ON_EXCS = (
    fogbugz.FogBugzLogonError,
)


class FBClient(object):

    logger = logging.getLogger('fb.client')

    def __init__(self):
        self._fburl = os.environ.get('FBURL', 'https://yougov.fogbugz.com/')

        self._fbuser = os.environ.get('FBUSER')
        if self._fbuser is None:
            self._fbuser = raw_input('Username: ')

        self._fbpass = os.environ.get('FBPASS')
        if self._fbpass is None:
            self._fbpass = getpass.getpass()

        self._fb = fogbugz.FogBugz(self._fburl)

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

    def login(self):
        self.logger.debug('Logging in')
        self._fb.logon(self._fbuser, self._fbpass)

    def build_url(self, path):
        return self._fburl + path
