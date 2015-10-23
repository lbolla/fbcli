import os
import unittest

from six.moves import mock

from fbcli import fb


class TestFB(unittest.TestCase):

    @mock.patch('fbcli.fb.from_env_or_ask')
    def test_trailing_slash(self, ask):
        expected = 'http://fogbugz.com/a/b/c'
        for base in [
                'http://fogbugz.com',
                'http://fogbugz.com/',
        ]:
            ask.return_value = base
            client = fb.FBClient()
            self.assertEqual(client.full_url('a/b/c'), expected)
            self.assertEqual(client.full_url('/a/b/c'), expected)
        del os.environ['FBURL']
