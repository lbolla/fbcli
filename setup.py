from setuptools import setup, find_packages

from fbcli import __version__

setup(
    name='fbcli',
    version=__version__,
    author='Lorenzo Bolla',
    author_email='lorenzo.bolla@yougov.com',
    packages=find_packages('.'),
    install_requires=[
        'tornado>=4,<5',
    ],
    entry_points={
        'console_scripts': [
            'fb = fbcli.cli:main',
        ],
    },
)
