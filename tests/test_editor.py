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
