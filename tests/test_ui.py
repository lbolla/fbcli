import unittest
from fbcli import ui


class TestReadline(unittest.TestCase):

    def test_completer(self):
        self.assertEqual(ui.completer('mycase', 0), 'mycases ')
