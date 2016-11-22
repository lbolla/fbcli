# -*- coding: utf-8 -*-
# pylint: disable=no-self-use,protected-access

from __future__ import unicode_literals

import os
import unittest

from bs4 import BeautifulSoup

from fbcli import cli
from fbcli import errors

THIS_DIR = os.path.abspath(os.path.dirname(__file__))
FIXTURE_DIR = os.path.join(THIS_DIR, 'fixtures')


def get_fixture(what):
    with open(os.path.join(FIXTURE_DIR, what), 'r') as fid:
        if what.endswith('.xml'):
            # Soup
            return BeautifulSoup(fid.read(), 'xml')
        else:
            # Raw
            return fid.read()


class TestExecCtx(unittest.TestCase):

    def test_ignore_keyboard_interrupt(self):
        def f():
            raise KeyboardInterrupt
        with cli.exec_ctx():
            f()

    def test_quit_on_eof(self):
        def f():
            raise EOFError
        with self.assertRaises(SystemExit):
            with cli.exec_ctx():
                f()

    def test_ignore_aborted(self):
        def f():
            raise errors.Aborted()
        with cli.exec_ctx():
            f()


class TestFBPerson(unittest.TestCase):

    def test_init(self):
        xml = get_fixture('person.xml')
        fb = cli.FBPerson(xml)
        self.assertEqual(fb.id, 246)
        self.assertEqual(fb.fullname, 'José Arcadio Buendía')
        self.assertEqual(fb.email, 'jose.arcadio.buendia@soledad.com')


class TestFBAttachment(unittest.TestCase):

    def test_init(self):
        xml = get_fixture('attachment.xml')
        fb = cli.FBAttachment(xml)
        self.assertEqual(fb.filename, 'app_report (1).csv')
        self.assertEqual(
            fb.url, 'http://fogbugz/default.asp?pg=pgDownload&pgType='
            'pgFile&ixBugEvent=66555&ixAttachment=4790&s'
            'FileName=app_report%20(1).csv&sTicket=')


class TestFBCase(unittest.TestCase):

    def test_init(self):
        xml = get_fixture('FB41675.xml')
        fb = cli.FBCase(xml)
        self.assertEqual(fb.parent_id, 0)
        self.assertEqual(fb.children_ids, [])
        self.assertEqual(fb.related_ids, [])


class TestFBBugEvent(unittest.TestCase):

    def test_utf8(self):
        parent = cli.FBCase(get_fixture('FB41675.xml'))
        xml = get_fixture('FB38451.xml')
        fb = cli.FBBugEvent(parent, xml)
        self.assertTrue(fb.comment.startswith(u"Yes. \\xa0I'll"))


class TestFBMilestone(unittest.TestCase):

    def test_init(self):
        xml = get_fixture('milestone.xml')
        fb = cli.FBMilestone(xml)
        self.assertEqual(fb.id, 4)
        self.assertEqual(fb.name, 'ASAP')


class TestAlias(unittest.TestCase):

    def test_additional_args(self):

        @cli.command('foo')
        def _foo_cmd(*args):
            return args

        a = cli.alias('foo_alias', 'foo bar')
        self.assertEqual(a('baz'), ('bar', 'baz'))


class TestKW(unittest.TestCase):

    def test_parse_on_kwargs(self):

        s = 'stitle=title'.split()
        self.assertEqual(cli._parse_kwargs(s), {
            'stitle': 'title',
        })

    def test_parse_multiple_kwargs(self):

        s = (
            'stitle=title with spaces '
            'spriority=priority with more spaces'
        ).split()
        self.assertEqual(cli._parse_kwargs(s), {
            'stitle': 'title with spaces',
            'spriority': 'priority with more spaces',
        })

    def test_parse_for_api(self):

        s = 'Title=title'.split()
        self.assertEqual(cli._api_kwargs(s), {
            'sTitle': 'title',
        })
