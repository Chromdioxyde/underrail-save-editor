#!/usr/bin/env python3
"""Underrail save editor: specialization points (and unspent spec points).

Usage:
  underrail_spec.py [SAVE] list
  underrail_spec.py [SAVE] set NAME=VALUE [NAME=VALUE ...]
  underrail_spec.py [SAVE] unspent N

SAVE is a save folder name (e.g. quicksave) or a path; default: quicksave.
A backup of global.dat is written to ./backups/<save>/ before every change.
"""
import os
import sys

from underrail_save import SAVES, Save


def main(argv):
    folder = os.path.join(SAVES, 'quicksave')
    if argv and argv[0] not in ('list', 'set', 'unspent'):
        a = argv.pop(0)
        folder = a if os.path.isdir(a) else os.path.join(SAVES, a)
    if not argv:
        print(__doc__); return 1
    s = Save(folder)
    specs = {f.name: f for f in s.specs()}
    unspent = s.points()[4]
    cmd = argv[0]
    if cmd == 'list':
        print(f'{s.name}, level {s.level}  ({folder})')
        for f in specs.values():
            print(f'  {f.name:32} {f.value:3}')
        print(f'  {"total":32} {sum(f.value for f in specs.values()):3}')
        print(f'unspent spec points: {unspent.value}')
        return 0
    if cmd == 'set':
        lower = {k.lower(): k for k in specs}
        for arg in argv[1:]:
            name, _, val = arg.partition('=')
            key = lower.get(name.lower())
            if key is None:
                cands = [k for k in specs if name.lower() in k.lower()]
                sys.exit(f'unknown spec {name!r}' + (f'; meant one of {cands}?' if cands else
                         ' (only specs already present in the save can be edited)'))
            print(f'{key}: {specs[key].value} -> {int(val)}')
            s.set(specs[key], val)
    elif cmd == 'unspent':
        print(f'unspent spec points: {unspent.value} -> {int(argv[1])}')
        s.set(unspent, argv[1])
    else:
        print(__doc__); return 1
    print(f'saved {s.path}\nbackup {s.write()}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
