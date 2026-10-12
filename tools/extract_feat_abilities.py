#!/usr/bin/env python3
"""Extracts which attacks/abilities each feat grants from underrail.exe into data/feat_abilities.json.

Developer tool, not needed to run the editor. Needs: pip install dnfile dncil
  python tools/extract_feat_abilities.py [path/to/underrail.exe]

How the game grants them (found by reading its IL):
  * a feat's on-added method calls  character.<attacks or abilities>.Add(Registry.Get<AbilityClass>())
    and its on-removed method the matching Remove
  * ability classes carry an id attribute (e.g. "SnipeAttack"); saves store it lowercased in CR:CFTN,
    in the character's capability sets C1:SA ("Attacks") and C1:SA1 ("Abilities")
  * those sets are SortedLists ordered by the ability's order value (bh), then its display name (y8)
Class and member names are obfuscated, so the classes are found via known strings ("SpecialAttacks/Snipe",
the Snipe feat's display name) rather than by name.
"""
import json
import os
import re
import sys

from dncil.clr.token import InvalidToken, StringToken, Token

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract_feat_requirements as ex  # noqa: E402


def main(exe):
    pe, md, tname, types, owner, extends, body, methods, strings_in, attrs = ex.load(exe)

    def mname(rid):
        return str(md.MethodDef.rows[rid - 1].Name)

    def attr_of(cls):
        return next((a for a, arg in attrs.get(cls, []) if arg), None)

    def find_class(pred):
        return next(c for c in attrs if any(pred(r) for r in methods(c)))

    # ability id attribute: on the Snipe attack class; feat id attribute: on the Snipe feat ("S")
    snipe_attack = find_class(lambda r: 'SpecialAttacks/Snipe' in strings_in(r))
    ability_attr = attr_of(snipe_attack)
    snipe_feat = next(c for c, lst in attrs.items() if any(arg == 'S' for _, arg in lst)
                      and any(mname(r) == '.ctor' and strings_in(r) == ['Snipe'] for r in methods(c)))
    feat_attr = attr_of(snipe_feat)

    def attr_id(cls, attr):
        return next((arg for a, arg in attrs.get(cls, []) if a == attr and arg), None)

    def generic_args(tok):
        """TypeDef arguments of a MethodSpec token."""
        ms = md.MethodSpec.rows[(tok & 0xFFFFFF) - 1]
        blob = bytes(ms.Instantiation.value) if hasattr(ms.Instantiation, 'value') else bytes(ms.Instantiation)
        out, i = [], 2
        while i < len(blob):
            if blob[i] not in (0x11, 0x12):
                return out
            v = blob[i + 1]
            if v & 0x80 == 0:
                code, i = v, i + 2
            elif v & 0xC0 == 0x80:
                code, i = ((v & 0x3F) << 8) | blob[i + 2], i + 3
            else:
                code, i = ((v & 0x1F) << 24) | (blob[i + 2] << 16) | (blob[i + 3] << 8) | blob[i + 4], i + 5
            if code & 3 == 0:
                out.append(tname(types[(code >> 2) - 1]))
        return out

    def grants(rid):
        """[(set getter, ability class, owner of the method called on the result)] for each
        set.Method(Get<AbilityClass>()) in a method."""
        b = body(rid)
        out, getter, pending = [], None, []
        for ins in b.instructions if b else []:
            o = ins.operand
            if not isinstance(o, (Token, InvalidToken)):
                continue
            if o.value >> 24 == 0x06 and ins.opcode.name == 'callvirt':
                callee = o.value & 0xFFFFFF
                out += [(g, c, (owner.get(callee), callee)) for g, c in pending]
                pending = []
                getter = mname(callee)  # the set getter directly precedes Get<T>()
            elif o.value >> 24 == 0x2B:
                pending = [(getter, c) for c in generic_args(o.value) if attr_id(c, ability_attr)]
        return out

    def find_method(cls, name):
        while cls:
            ms = methods(cls, name)
            if ms:
                return ms[0]
            cls = extends.get(cls)
        return None

    def evaluate(cls, name, depth=0):
        """Value of a parameterless virtual method made of constants, branches, adds and virtual calls."""
        rid = find_method(cls, name)
        b = body(rid) if rid else None
        if b is None or depth > 8:
            return None
        ins = b.instructions
        at = {x.offset: k for k, x in enumerate(ins)}
        k, stack = 0, []
        for _ in range(200):
            x = ins[k]
            op, o = x.opcode.name, x.operand
            k += 1
            if op.startswith('ldc.i4'):
                stack.append(-1 if op == 'ldc.i4.m1' else int(o) if op in ('ldc.i4', 'ldc.i4.s')
                             else int(op.split('.')[-1]))
            elif op == 'ldarg.0':
                stack.append('this')
            elif op in ('callvirt', 'call') and isinstance(o, (Token, InvalidToken)) and o.value >> 24 == 0x06:
                if stack and stack[-1] == 'this':
                    stack.pop()
                v = evaluate(cls, mname(o.value & 0xFFFFFF), depth + 1)
                if v is None:
                    return None
                stack.append(v)
            elif op == 'add':
                b2, a2 = stack.pop(), stack.pop()
                stack.append(a2 + b2)
            elif op in ('brtrue', 'brtrue.s', 'brfalse', 'brfalse.s', 'br', 'br.s'):
                take = op.startswith('br.') or op == 'br' or (bool(stack.pop()) == op.startswith('brtrue'))
                if take:
                    k = at[int(o)]
            elif op == 'ret':
                return stack.pop() if stack else None
            elif op == 'nop':
                pass
            else:
                return None
        return None

    def display(cls):
        rid = find_method(cls, 'y8')
        s = strings_in(rid) if rid else []
        return s[0] if len(s) == 1 else None

    # set getters: the one Aimed Shot uses holds the attacks, the other the abilities
    feats = {}
    for cls in attrs:
        fid = attr_id(cls, feat_attr)
        if not fid:
            continue
        added = [g for r in methods(cls) for g in grants(r)]
        if added:
            # on-added and on-removed both name the same classes; keep one of each
            feats[fid.lower()] = list(dict.fromkeys(added))
    # only the capability set's Add grants something (the on-removed method calls Remove, others are checks)
    set_cls = feats['s'][0][2][0]

    def calls_add(rid):
        b = body(rid)
        return any(isinstance(i.operand, (Token, InvalidToken)) and i.operand.value >> 24 == 0x0A
                   and str(md.MemberRef.rows[(i.operand.value & 0xFFFFFF) - 1].Name) == 'Add'
                   for i in (b.instructions if b else []))
    adds = {r for r in methods(set_cls) if calls_add(r)}
    feats = {f: list(dict.fromkeys((g, c) for g, c, (o, r) in lst if o == set_cls and r in adds))
             for f, lst in feats.items()}
    feats = {f: lst for f, lst in feats.items() if lst}
    attack_getter = feats['as'][0][0]
    abilities = {}
    out = {}
    for fid, lst in sorted(feats.items()):
        out[fid] = []
        for getter, cls in lst:
            aid = attr_id(cls, ability_attr).lower()
            out[fid].append([aid, 'Attacks' if getter == attack_getter else 'Abilities'])
    # order keys of every ability class, so entries can be placed where the game's SortedList expects them
    for cls in attrs:
        aid = attr_id(cls, ability_attr)
        if aid:
            abilities[aid.lower()] = [evaluate(cls, 'bh'), display(cls)]
    return out, dict(sorted(abilities.items()))


if __name__ == '__main__':
    import gamedata
    exe = sys.argv[1] if len(sys.argv) > 1 else os.path.join(gamedata.GAME, 'underrail.exe')
    feats, abilities = main(exe)
    dst = os.path.join(ROOT, 'data', 'feat_abilities.json')
    with open(dst, 'w') as f:
        json.dump({'source': 'underrail.exe', 'feats': feats, 'abilities': abilities}, f, indent=1)
    print(f'{len(feats)} feats granting {sum(map(len, feats.values()))} capabilities, '
          f'{len(abilities)} order keys -> {dst}')
