#!/usr/bin/env python3
"""AG SoundEditor - Python/Tkinter port of KORG's 1995 Audio Gallery editor."""
import argparse

from agse.app import App


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('file', nargs='?', help='program file to open (.mid / .syx)')
    ap.add_argument('--scale', type=int, choices=(1, 2, 3, 4),
                    help='pixel zoom for the original 1-bit artwork (default: 2 on large screens)')
    args = ap.parse_args()
    App(scale=args.scale, path=args.file).run()


if __name__ == '__main__':
    main()
