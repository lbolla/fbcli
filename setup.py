from setuptools import setup, find_packages

from fbcli import __version__

setup(
    name='fbcli',
    version=__version__,
    author='Lorenzo Bolla',
    author_email='lbolla@gmail.com',
    packages=find_packages('.'),
    install_requires=[
        'fogbugz',
        'tornado>=4,<5dev',
        'pyyaml>=3,<4dev',
    ],
    test_suite='tests',
    entry_points={
        'console_scripts': [
            'fb = fbcli.cli:main',
        ],
    },
)
