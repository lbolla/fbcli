# -*- coding: utf-8 -*-
# pylint: disable=R0201

from __future__ import unicode_literals

import os
import unittest

try:
    from bs4 import BeautifulSoup
except ImportError:
    from BeautifulSoup import BeautifulSoup

from fbcli import cli

THIS_DIR = os.path.abspath(os.path.dirname(__file__))
FIXTURE_DIR = os.path.join(THIS_DIR, 'fixtures')


def get_fixture(what):
    with open(os.path.join(FIXTURE_DIR, what), 'r') as fid:
        if what.endswith('.xml'):
            # Soup
            if BeautifulSoup.__module__ != 'bs4':
                return BeautifulSoup(fid.read())
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
            raise cli.Aborted()
        with cli.exec_ctx():
            f()


class TestFBPerson(unittest.TestCase):

    def test_init(self):
        xml = get_fixture('person.xml')
        fb = cli.FBPerson(xml)
        self.assertEqual(fb.id, 246)
        self.assertEqual(fb.fullname, 'José Arcadio Buendía')
        self.assertEqual(fb.email, 'jose.arcadio.buendia@soledad.com')
