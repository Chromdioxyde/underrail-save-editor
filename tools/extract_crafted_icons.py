#!/usr/bin/env python3
"""Extracts the icons of crafted weapons and shield emitters from underrail.exe into data/crafted_icons.json.

Crafted items get composite visual ids ("sledgehammer.2", "smg.3.frame", "knife.1.2.m1",
"shieldEmitter.p2.s1.e1"). The game registers their icons at startup in one method per recipe class: loops
that build an icon definition per id with layers (sheet name, grid cell, opacity) on the Weapons or Armors
sheet. Those methods are plain arithmetic, string formatting and list building, so a tiny IL interpreter runs
them here instead of re-implementing each pattern.

Usage: python tools/extract_crafted_icons.py [path/to/underrail.exe]   (needs: pip install dnfile dncil)
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dncil.clr.token import InvalidToken, StringToken, Token  # noqa: E402

import extract_feat_requirements as ex  # noqa: E402


class Obj:
    def __init__(self, cls):
        self.cls, self.f, self.args = cls, {}, None


class Ref:
    """Address of a local or argument (ldloca/ldarga)."""

    def __init__(self, store, i):
        self.store, self.i = store, i

    def get(self):
        return self.store.get(self.i, 0) if isinstance(self.store, dict) else self.store[self.i]

    def set(self, v):
        self.store[self.i] = v


def index(op, o):
    """Local/argument number of ldloc.2 / ldloc.s local(5) / ldarg.1 ..."""
    if o is None:
        return int(op.split('.')[-1])
    return o.index if hasattr(o, 'index') else int(o)


class Interp:
    def __init__(self, exe):
        (self.pe, self.md, self.tname, self.types, self.owner, _, self.body, self.methods, _, _) = ex.load(exe)
        self.us = self.pe.net.user_strings
        self.statics = {}
        self.field_owner = {}
        for t in self.types:
            for fl in t.FieldList:
                self.field_owner[fl.row_index] = self.tname(t)

    def nparams(self, blob):
        b = bytes(blob)
        i = 1
        n = b[i]
        if n & 0x80:  # compressed integer
            n = ((n & 0x3F) << 8) | b[i + 1] if not n & 0x40 else ((n & 0x1F) << 24) | (b[i + 1] << 16) | (b[i + 2] << 8) | b[i + 3]
        return n, bool(b[0] & 0x20)

    def member(self, t):
        """(kind, name, nparams, hasthis, rid) of a method token."""
        tb, rid = t >> 24, t & 0xFFFFFF
        if tb == 6:
            r = self.md.MethodDef.rows[rid - 1]
            n, this = self.nparams(r.Signature.value if hasattr(r.Signature, 'value') else r.Signature)
            return 'def', f'{self.owner.get(rid)}::{r.Name}', n, this, rid
        if tb == 10:
            r = self.md.MemberRef.rows[rid - 1]
            c = r.Class.row
            cname = self.tname(c) if hasattr(c, 'TypeName') else '?'
            n, this = self.nparams(r.Signature.value if hasattr(r.Signature, 'value') else r.Signature)
            return 'ref', f'{cname}::{r.Name}', n, this, rid
        if tb == 0x2B:  # MethodSpec (generic instance): resolve its method
            r = self.md.MethodSpec.rows[rid - 1]
            m = r.Method
            return self.member((0x06 if m.table.name == 'MethodDef' else 0x0A) << 24 | m.row_index)
        raise ValueError(hex(t))

    def external(self, name, args):
        short = name.split('.')[-1] if '::' not in name else name.split('::')[0].split('.')[-1] + '::' + name.split('::')[1]
        if short == 'String::Format':
            fmt, rest = args[0], args[1:]
            if len(rest) == 1 and isinstance(rest[0], list):
                rest = rest[0]
            return fmt.format(*rest)
        if short == 'String::Concat':
            parts = args[0] if len(args) == 1 and isinstance(args[0], list) else args
            return ''.join('' if a is None else str(a) for a in parts)
        if short == 'Int32::ToString':
            v = args[0].get() if isinstance(args[0], Ref) else args[0]
            return str(v)
        if short.endswith('::Add'):
            args[0].append(args[1])
            return None
        if short.endswith('::Insert'):
            args[0].insert(args[1], args[2])
            return None
        if short.endswith('::get_Count'):
            return len(args[0])
        if short.endswith('::get_Item'):
            return args[0][args[1]]
        if short.endswith('Object::.ctor'):
            return None
        raise NotImplementedError(name)

    def run(self, rid, args):
        b = self.body(rid)
        ins = b.instructions
        at = {i.offset: n for n, i in enumerate(ins)}
        loc = [0] * 64
        st = []
        pc = 0
        steps = 0
        while True:
            steps += 1
            if steps > 2_000_000:
                raise RuntimeError('too many steps')
            i = ins[pc]
            op, o = i.opcode.name, i.operand
            pc += 1
            if op.startswith('ldc.i4'):
                st.append(int(o) if o is not None else (-1 if op.endswith('m1') else int(op.split('.')[-1])))
            elif op in ('ldc.r4', 'ldc.r8'):
                st.append(float(o))
            elif op == 'ldstr':
                st.append(self.us.get(o.value & 0xFFFFFF).value)
            elif op == 'ldnull':
                st.append(None)
            elif op.startswith('ldloca'):
                st.append(Ref(loc, index(op, o)))
            elif op.startswith('ldloc'):
                st.append(loc[index(op, o)])
            elif op.startswith('stloc'):
                loc[index(op, o)] = st.pop()
            elif op.startswith('ldarga'):
                st.append(Ref(args, index(op, o)))
            elif op.startswith('ldarg'):
                st.append(args[index(op, o)])
            elif op.startswith('starg'):
                args[index(op, o)] = st.pop()
            elif op in ('add', 'sub', 'mul', 'div', 'rem'):
                b2, a = st.pop(), st.pop()
                if op == 'add':
                    st.append(a + b2)
                elif op == 'sub':
                    st.append(a - b2)
                elif op == 'mul':
                    st.append(a * b2)
                elif op == 'div':
                    st.append(int(a / b2) if isinstance(a, int) and isinstance(b2, int) else a / b2)
                else:
                    st.append(int(__import__('math').fmod(a, b2)) if isinstance(a, int) else a % b2)
            elif op in ('box', 'unbox.any', 'castclass', 'isinst', 'nop'):
                pass
            elif op.startswith('conv.i'):
                st.append(int(st.pop()))
            elif op.startswith('conv.r'):
                st.append(float(st.pop()))
            elif op == 'dup':
                st.append(st[-1])
            elif op == 'pop':
                st.pop()
            elif op in ('br', 'br.s'):
                pc = at[o]
            elif op in ('brtrue', 'brtrue.s', 'brfalse', 'brfalse.s'):
                v = st.pop()
                if bool(v) == op.startswith('brtrue'):
                    pc = at[o]
            elif op.split('.')[0] in ('beq', 'bne', 'blt', 'ble', 'bgt', 'bge'):
                b2, a = st.pop(), st.pop()
                kind = op.split('.')[0]
                ok = {'beq': a == b2, 'bne': a != b2, 'blt': a < b2, 'ble': a <= b2, 'bgt': a > b2, 'bge': a >= b2}[kind]
                if ok:
                    pc = at[o]
            elif op in ('ceq', 'clt', 'cgt'):
                b2, a = st.pop(), st.pop()
                st.append(int({'ceq': a == b2, 'clt': a < b2, 'cgt': a > b2}[op]))
            elif op == 'newarr':
                st.append([None] * st.pop())
            elif op.startswith('stelem'):
                v, idx, arr = st.pop(), st.pop(), st.pop()
                arr[idx] = v
            elif op.startswith('ldelem'):
                idx, arr = st.pop(), st.pop()
                st.append(arr[idx])
            elif op == 'ldlen':
                st.append(len(st.pop()))
            elif op.startswith('ldind'):
                st.append(st.pop().get())
            elif op.startswith('stind'):
                v, r = st.pop(), st.pop()
                r.set(v)
            elif op == 'ldsfld':
                st.append(self.statics.get(o.value & 0xFFFFFF))
            elif op == 'ldsflda':
                st.append(Ref(self.statics, o.value & 0xFFFFFF))
            elif op == 'stsfld':
                self.statics[o.value & 0xFFFFFF] = st.pop()
            elif op == 'ldflda':
                obj = st.pop()
                obj = obj.get() if isinstance(obj, Ref) else obj
                st.append(Ref(obj.f, o.value & 0xFFFFFF))
            elif op == 'ldfld':
                obj = st.pop()
                obj = obj.get() if isinstance(obj, Ref) else obj
                # constructors aren't run (they touch engine state); a field read before it's written is the
                # collection the constructor would have created
                st.append(obj.f.setdefault(o.value & 0xFFFFFF, []))
            elif op == 'stfld':
                v, obj = st.pop(), st.pop()
                obj = obj.get() if isinstance(obj, Ref) else obj
                obj.f[o.value & 0xFFFFFF] = v
            elif op == 'ret':
                return st.pop() if st else None
            elif op in ('call', 'callvirt', 'newobj'):
                kind, name, n, this, mrid = self.member(o.value)
                cargs = [st.pop() for _ in range(n)][::-1]
                if op == 'newobj':
                    if name.endswith('Point::.ctor'):
                        st.append(tuple(cargs))
                        continue
                    if kind == 'ref':
                        st.append([])  # collections
                        continue
                    obj = Obj(name.split('::')[0])
                    obj.args = cargs
                    st.append(obj)
                    continue
                if this:
                    cargs = [st.pop()] + cargs
                if kind == 'def':
                    r = self.run(mrid, cargs)
                else:
                    r = self.external(name, cargs)
                if not name.endswith(('::Add', '::Insert', 'Object::.ctor')) or r is not None:
                    st.append(r) if self.returns(kind, mrid, name) else None
            else:
                raise NotImplementedError(op)

    def returns(self, kind, rid, name):
        """Whether a method returns a value (its signature's return type isn't void)."""
        if kind == 'def':
            sig = self.md.MethodDef.rows[rid - 1].Signature
        else:
            sig = self.md.MemberRef.rows[rid - 1].Signature
        b = bytes(sig.value if hasattr(sig, 'value') else sig)
        i = 1
        i += 1 if b[1] < 0x80 else (2 if b[1] < 0xC0 else 4)
        return b[i] != 0x01  # ELEMENT_TYPE_VOID


def icon_methods(it):
    """Methods that register composite icons of crafted items: they name the Weapons or Armors icon sheet
    (shield emitters live on Armors) and build layers from grid points."""
    out = []
    for rid in range(1, len(it.md.MethodDef.rows) + 1):
        b = it.body(rid)
        if not b:
            continue
        strs, points = [], 0
        for i in b.instructions:
            if isinstance(i.operand, StringToken):
                strs.append(it.us.get(i.operand.value & 0xFFFFFF).value)
            elif i.opcode.name == 'newobj' and isinstance(i.operand, (Token, InvalidToken)):
                try:
                    if it.member(i.operand.value)[1].endswith('Point::.ctor'):
                        points += 1
                except Exception:
                    pass
        if points and any(s.endswith(('Weapons', 'Armors')) for s in strs) and any('{0}' in s for s in strs):
            out.append(rid)
    return out


def extract(exe):
    it = Interp(exe)
    icons = {}
    for rid in icon_methods(it):
        name = f'{it.owner.get(rid)}::{it.md.MethodDef.rows[rid - 1].Name}'
        try:
            defs = it.run(rid, [None] * 8)
        except Exception as e:
            print(f'skipped {name}: {e!r}', file=sys.stderr)
            continue
        if not isinstance(defs, list):
            continue
        n = 0
        for d in defs:
            if not isinstance(d, Obj):
                continue
            vm = next((v for v in d.f.values() if isinstance(v, str)), None)
            layers = next((v for v in d.f.values() if isinstance(v, list)), None)
            if not vm or layers is None:
                continue
            parts = []
            for layer in layers:
                sheet, (col, row), alpha = layer.args[:3]
                parts.append([sheet, col, row, round(alpha, 3)])
            icons[vm] = parts
            n += 1
        print(f'{name}: {n} icons', file=sys.stderr)
    return dict(sorted(icons.items()))


if __name__ == '__main__':
    import gamedata
    exe = sys.argv[1] if len(sys.argv) > 1 else os.path.join(gamedata.GAME, 'underrail.exe')
    icons = extract(exe)
    dst = os.path.join(ROOT, 'data', 'crafted_icons.json')
    with open(dst, 'w') as f:
        json.dump({'source': 'underrail.exe', 'icons': icons}, f, separators=(',', ':'))
    print(f'{len(icons)} crafted item icons -> {dst}')
