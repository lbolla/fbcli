# FogBugz Command Line Interface

[<img src="https://travis-ci.org/lbolla/fbcli.svg?branch=master">](https://travis-ci.org/lbolla/fbcli)

Install with:

    $> python setup.py install

Run with:

    fb
    fb --logging=debug  # verbose
    fb --help  # for more options

Get help from `fb`:

    >>> help
    >>> help <command>  # for more

# Tutorial

<iframe width="420" height="315" src="https://www.youtube.com/embed/2tunk7HD0GY" frameborder="0" allowfullscreen></iframe>

# Development

Run tests with:

    >>> python setup.py test

Run tests for Py27 and Py35 with:

    >>> pip install tox
    >>> tox

# References

- FogBugzPy: https://developers.fogbugz.com/?W199
- FogBugz XML API:
  - https://developers.fogbugz.com/default.asp?W194
  - http://help.fogcreek.com/8202/xml-api

# Acknowledgements

Ported to Python 3 by Jason R. Coombs.
