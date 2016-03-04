import sys
from setuptools import setup, find_packages

from fbcli import __version__

with open('README.md', 'r') as readme:
    long_description = readme.read()

PY2 = sys.version_info[0] == 2
PYPY = hasattr(sys, 'pypy_version_info')

extra_install_requires = []
tests_require = []
if PY2:
    tests_require.append('mock')
    if PYPY:
        extra_install_requires.append('lxml')

setup(
    name='fbcli',
    version=__version__,
    description='FogBugz command line interface.',
    long_description=long_description,
    url='https://github.com/lbolla/fbcli',
    author='Lorenzo Bolla',
    author_email='lbolla@gmail.com',
    packages=find_packages('.'),
    install_requires=[
        'fogbugz_bis>=1.0.3',
        'tornado>=4,<5dev',
        'pyyaml>=3,<4dev',
        'six',
    ] + extra_install_requires,
    test_suite='tests',
    tests_require=tests_require,
    entry_points={
        'console_scripts': [
            'fb = fbcli.cli:main',
        ],
    },
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Operating System :: OS Independent',
    ]
)
