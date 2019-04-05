from setuptools import setup, find_packages

from fbcli import __version__

with open('README.md', 'r') as readme:
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
    python_requires='>=3.6',
    install_requires=[
        'fogbugz>=1.0.5',
        'html2text>=2018.1.9',
        'tornado>=4,<5dev',
        'pyyaml>=4.2b1',
        'requests>=2.12.1,<3dev',
        'lazy-property==0.0.1',
        'six',
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
        'Programming Language :: Python :: 3',
        'Operating System :: OS Independent',
    ]
)
