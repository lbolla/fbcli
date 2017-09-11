# FogBugz Command Line Interface

[<img src="https://travis-ci.org/lbolla/fbcli.svg?branch=master">](https://travis-ci.org/lbolla/fbcli) [![Codacy Badge](https://api.codacy.com/project/badge/Grade/3699c35b755d41fbb540ae4e02118260)](https://www.codacy.com/app/lbolla/fbcli?utm_source=github.com&amp;utm_medium=referral&amp;utm_content=lbolla/fbcli&amp;utm_campaign=Badge_Grade)

Install with:

    $> python setup.py install

Run with:

    fb
    fb --logging=debug  # verbose
    fb --help  # for more options

Get help from `fb`:

    >>> help
    >>> help <command>  # for more

Python2 is deprecated: please use Python3.

# Configuration

`fbcli` can make use of several environmental variables:

- FBURL: the URL to FogBugz, e.g. `https://<your_company>.fogbugz.com/`
- FBUSER: your username, e.g. lorenzo.bolla@example.com
- FBTOKEN: your FogBugz API token, e.g. abcdefghilmnopqrstuvz
- FBPASS: your FogBugz password

If you have 2-factor authentication enabled on your FogBugz account,
you can't use username/password, you must use the token.

# Tutorial

A quick video tutorial is available [here](https://www.youtube.com/watch?v=2tunk7HD0GY).

[![Tutorial](https://j.gifs.com/vJxLDD.gif)](https://www.youtube.com/watch?v=2tunk7HD0GY)

# Development

Run tests with:

    >>> python setup.py test

Run tests for Py27, Py35 and PyPy with:

    >>> pip install tox
    >>> tox

# References

- FogBugz API Intro: https://developers.fogbugz.com/default.asp?W194
- FogBugz API Reference: http://help.fogcreek.com/the-fogbugz-api
- FogBugzPy: https://developers.fogbugz.com/?W199

# Acknowledgements

Ported to Python 3 by Jason R. Coombs.
