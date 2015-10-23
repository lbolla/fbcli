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

A quick video tutorial is available [here](https://www.youtube.com/watch?v=2tunk7HD0GY).

[![Tutorial](https://j.gifs.com/vJxLDD.gif)](https://www.youtube.com/watch?v=2tunk7HD0GY)

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
