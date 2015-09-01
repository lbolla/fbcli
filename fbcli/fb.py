from functools import wraps
import getpass
import logging
import os

import fogbugz


RETRY_ON_EXCS = (
    fogbugz.FogBugzLogonError,
)


def from_env_or_ask(k, question, is_password=False):
    what = os.environ.get(k)
    if what is not None:
        return what
    print 'You can skip this question by setting ${}'.format(k)
    if is_password:
        return getpass.getpass()
    return raw_input(question)


class FBClient(object):

    logger = logging.getLogger('fb.client')

    def __init__(self):
        self._fburl = from_env_or_ask('FBURL', 'Fogbugz URL: ')
        self._fbuser = from_env_or_ask('FBUSER', 'Username: ')
        self._fbpass = from_env_or_ask('FBPASS', 'Password: ', True)
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

    @property
    def current_token(self):
        return self._fb._token

    def login(self):
        self.logger.debug('Logging in')
        self._fb.logon(self._fbuser, self._fbpass)

    def full_url(self, path):
        return self._fburl + path
