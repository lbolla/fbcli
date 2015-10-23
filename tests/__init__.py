import os
import six

os.environ['FBURL'] = 'http://fogbugz/'
os.environ['FBUSER'] = 'user'
os.environ['FBPASS'] = 'pass'
os.environ['EDITOR'] = ''

six.add_move(six.MovedModule('mock', 'mock', 'unittest.mock'))
