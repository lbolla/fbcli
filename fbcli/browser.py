from subprocess import call
import os


def browse(url):
    browser = os.environ.get('BROWSER')
    if browser is None:
        # TODO possibly, try with xdg_open
        print('Set $BROWSER first')
    else:
        call([browser, url])
