from setuptools import setup, find_packages

from fbcli import __version__

with open('README', 'r') as readme:
    long_description = readme.read()

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
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        'Programming Language :: Python :: 2.7',
        'Operating System :: OS Independent',
    ]
)
