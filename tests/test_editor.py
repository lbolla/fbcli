# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import unittest

import yaml

from fbcli import editor


class TestText(unittest.TestCase):

    def test_meta_and_body(self):
        txt = '''Title: Valid title
Project: Proj
Area: misc
Assign to: me
Priority: high
---
This is the body'''
        t = editor.Text(txt)
        self.assertEqual(t.meta['Title'], 'Valid title')
        self.assertEqual(t.meta['Project'], 'Proj')
        self.assertEqual(t.meta['Area'], 'misc')
        self.assertEqual(t.meta['Assign to'], 'me')
        self.assertEqual(t.meta['Priority'], 'high')

    def test_invalid_yaml(self):
        txt = '''Title:Invalid because no space after column
Project:Proj
Area:misc
Assign to: me
Priority: for consideration
---
This is the body'''
        t = editor.Text(txt)
        with self.assertRaises(yaml.error.YAMLError):
            t.meta  # pylint: disable=pointless-statement

    def test_utf8_body(self):
        txt = '''Title: Some ¢hars
Project: Proj
Area: misc
Assign to: me
Priority: high
---
This is the body with mo®e utf8.
'''
        t = editor.Text(txt)
        self.assertEqual(t.meta['Title'], 'Some ¢hars')
        self.assertEqual(t.body, 'This is the body with mo®e utf8.')

    def test_body_with_comments(self):
        txt = '''Title: title title
Project: Proj
Area: misc
Assign to: me
Priority: high
---
# This comment should stay
This is the body.
# This comment should stay, too

# This comment won't be included because there are no blank lines
# Lines starting wth "#" will be ignored.
# Leave this file empty to abort action.
# It's possible to add metadata in the format of a header.
# Use "---" as separator between the header and the body.
# E.g. To upload files use:
#    Files:
#      - path_to_file_1
#      - path_to_file_2
'''
        expected = '''# This comment should stay
This is the body.
# This comment should stay, too'''
        t = editor.Text(txt)
        self.assertEqual(t.body, expected)

    def test_new_invalid_title(self):
        txt = '''Title: <title>
Project: Proj
Area: misc
Assign to: me
Priority: for consideration
---
This is the body'''
        t = editor.Text(txt)
        with self.assertRaises(AssertionError):
            t.get_params_for_new()

    def test_new_empty_title(self):
        txt = '''Title:
Project: Proj
Area: misc
Assign to: me
Priority: for consideration
---
This is the body'''
        t = editor.Text(txt)
        with self.assertRaises(AssertionError):
            t.get_params_for_new()


class TestEditor(unittest.TestCase):

    def test_write_new(self):
        editor.clear()
        expected = '''
# Lines starting wth "#" will be ignored.
# Leave this file empty to abort action.
# It's possible to add metadata in the format of a header.
# Use "---" as separator between the header and the body.
# E.g. To upload files use:
#    Files:
#      - path_to_file_1
#      - path_to_file_2
'''

        with editor.writing():
            with open(editor.FNAME, 'r') as fid:
                body = fid.read()
            self.assertEqual(body, expected)
