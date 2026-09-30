"""Access to the graphics and data extracted from the original application."""
import json
import os

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets')
_data = None


def data():
    global _data
    if _data is None:
        with open(os.path.join(ASSETS, 'data.json')) as f:
            d = json.load(f)
        for key in ('dlog', 'ditl', 'cntl', 'menu', 'pgpr', 'strings'):
            d[key] = {int(k): v for k, v in d[key].items()}
        _data = d
    return _data


def pict_path(pict_id):
    return os.path.join(ASSETS, f'pict_{pict_id}.png')


def dlog(i):
    return data()['dlog'][i]


def ditl(i):
    return {it['n']: it for it in data()['ditl'][i]}


def cntl(i):
    return data()['cntl'][i]
