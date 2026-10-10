#!/usr/bin/env python3
"""Extracts feat requirements from underrail.exe into data/feat_requirements.json.

Developer tool, not needed to run the editor. Needs: pip install dnfile dncil
  python tools/extract_feat_requirements.py [path/to/underrail.exe]

How the game defines feats (found by reading its IL):
  * every feat is a class derived from the feat base class; a custom attribute carries its id
    (e.g. "GunNut" -> saves store "gunnut"), the constructor passes the display name
  * the feat's requirement method builds a list of requirement objects, e.g.
      BaseAbilityRequirement(typeof(Intelligence), 7[, useModified])
      SkillRequirement(15[, useModified], typeof(Mechanics), ...)   any of the skills
      FeatRequirement(typeof(Gunslinger), ...)                      any of the feats
      RestrictedFeats(typeof(...), ...)                             none of the feats
      AnyPsiSkill(55[, useModified]), Level(10), PsiAbility(typeof(...), ...)
  * requirements compare against base values unless the useModified flag is set
Class and member names are obfuscated, so the requirement classes are recognised by their
diagnostic strings and constructor shapes rather than by name.
"""
import json
import os
import sys

import dnfile
from dncil.cil.body import CilMethodBody
from dncil.cil.body.reader import CilMethodBodyReaderBase
from dncil.cil.error import MethodBodyFormatError
from dncil.clr.token import InvalidToken, StringToken, Token

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def load(exe):
    pe = dnfile.dnPE(exe)
    md = pe.net.mdtables

    def tname(t):
        ns = str(t.TypeNamespace or '')
        return (ns + '.' if ns else '') + str(t.TypeName)

    types = md.TypeDef.rows
    owner = {}
    for t in types:
        for mm in t.MethodList:
            owner[mm.row_index] = tname(t)
    extends = {}
    for t in types:
        try:
            extends[tname(t)] = tname(t.Extends.row)
        except Exception:
            extends[tname(t)] = None

    class Reader(CilMethodBodyReaderBase):
        def __init__(self, rva):
            self.offset = pe.get_offset_from_rva(rva)

        def read(self, n):
            d = pe.get_data(pe.get_rva_from_offset(self.offset), n)
            self.offset += n
            return d

        def tell(self):
            return self.offset

        def seek(self, off):
            self.offset = off
            return off

    def body(rid):
        m = md.MethodDef.rows[rid - 1]
        if not m.Rva:
            return None
        try:
            return CilMethodBody(Reader(m.Rva))
        except MethodBodyFormatError:
            return None

    by_class = {}
    for r in range(1, len(md.MethodDef.rows) + 1):
        by_class.setdefault(owner.get(r), []).append(r)

    def methods(cls, name=None):
        return [r for r in by_class.get(cls, []) if name is None or str(md.MethodDef.rows[r - 1].Name) == name]

    _strings = {}

    def strings_in(rid):
        if rid in _strings:
            return _strings[rid]
        b = body(rid)
        out = []
        for ins in b.instructions if b else []:
            if isinstance(ins.operand, StringToken):
                out.append(pe.net.user_strings.get(ins.operand.value & 0xFFFFFF).value)
        _strings[rid] = out
        return out

    # custom attributes: type -> [(attribute type, first string argument)]
    attrs = {}
    for row in md.CustomAttribute.rows:
        try:
            if row.Parent.table.name != 'TypeDef':
                continue
            parent = tname(types[row.Parent.row_index - 1])
            if row.Type.table.name == 'MethodDef':
                attr = owner.get(row.Type.row_index, '?')
            else:
                cls = md.MemberRef.rows[row.Type.row_index - 1].Class.row
                attr = tname(cls) if hasattr(cls, 'TypeName') else '?'
            blob = bytes(row.Value.value) if row.Value is not None else b''
            arg = None
            if len(blob) > 3 and blob[:2] == b'\x01\x00' and blob[2] != 0xFF and blob[2] < 0x80:
                arg = blob[3:3 + blob[2]].decode('utf-8', 'replace')
            attrs.setdefault(parent, []).append((attr, arg))
        except Exception:
            continue
    return pe, md, tname, types, owner, extends, body, methods, strings_in, attrs


def main(exe):
    pe, md, tname, types, owner, extends, body, methods, strings_in, attrs = load(exe)

    def ancestors(n):
        out = []
        while n and len(out) < 12:
            n = extends.get(n)
            out.append(n)
        return out

    # recognise requirement classes by their diagnostic strings (looked up lazily, only for
    # classes that feat requirement methods actually construct)
    _kinds = {}

    def req_kind(n):
        if n in _kinds:
            return _kinds[n]
        s = [x for r in methods(n) for x in strings_in(r)]
        kind = '?'
        if 'baseAbilityType' in s:
            kind = 'attribute'
        elif any('SkillRequirement requires' in x for x in s):
            kind = 'skill'
        elif 'RestrictedFeats' in s or 'RestrictedFeat' in s:
            kind = 'not_feat'
        elif any('FeatRequirement requires' in x for x in s):
            kind = 'feat'
        elif 'Skills/AnyPsi' in s:
            kind = 'any_psi'
        elif 'Level' in s and 'character' in s:
            kind = 'level'
        elif 'PsiAbility' in s:
            kind = 'psi'
        elif 'NoOtherEmpoweredInvocationFeatsRequirement' in s:
            kind = 'only_one_empowered_invocation'
        elif 'NoOtherIncreasedBaseAbilityFeatsRequirement' in s:
            kind = 'only_one_increased_base_ability'
        _kinds[n] = kind
        return kind

    # feat base class = the one whose subclasses carry the id attribute most often
    id_attr = None
    counts = {}
    for n, lst in attrs.items():
        for a, arg in lst:
            if arg and n in extends:
                counts[a] = counts.get(a, 0) + 1
    # skill classes carry two attributes: display name and save class name; feats only one
    feat_attr_candidates = {}
    for n, lst in attrs.items():
        if len(lst) == 1 and lst[0][1]:
            feat_attr_candidates[lst[0][0]] = feat_attr_candidates.get(lst[0][0], 0) + 1

    def type_info(n):
        """Classify a type used as requirement argument."""
        lst = dict(attrs.get(n, []))
        ctor_strings = [s for r in methods(n, '.ctor') for s in strings_in(r)]
        return lst, ctor_strings

    def ctor_param_count(rid):
        sig = md.MethodDef.rows[rid - 1].Signature
        sig = bytes(sig.value) if hasattr(sig, 'value') else bytes(sig)
        return sig[1]

    def resolve_tok(tok):
        table, rid = tok >> 24, tok & 0xFFFFFF
        if table == 0x02:
            return ('type', tname(types[rid - 1]))
        if table == 0x06:
            return ('method', rid)
        return ('other', tok)

    def static_int(field_tok):
        """Value of a static int field assigned a constant in its class's static constructor."""
        rid = field_tok & 0xFFFFFF
        if field_tok >> 24 != 0x04:
            return None
        cls = next((tname(t) for t in types for fl in t.FieldList if fl.row_index == rid), None)
        for r in methods(cls, '.cctor'):
            b = body(r)
            last = None
            for ins in b.instructions if b else []:
                op = ins.opcode.name
                if op.startswith('ldc.i4'):
                    last = -1 if op == 'ldc.i4.m1' else (int(ins.operand) if op in ('ldc.i4.s', 'ldc.i4')
                                                         else int(op.split('.')[-1]))
                elif op == 'stsfld' and isinstance(ins.operand, (Token, InvalidToken)) and \
                        ins.operand.value == field_tok:
                    return last
                elif not op.startswith('nop'):
                    last = None if op != 'stsfld' else last
        return None

    def interpret(cls, depth=0):
        """Requirement list built by cls's requirement method (follows base calls)."""
        # the requirement method may be inherited from a base class
        rid, c = None, cls
        while c and rid is None:
            ms = methods(c, 'j0')
            rid = ms[0] if ms else None
            c = extends.get(c)
        if rid is None:
            return [], False
        b = body(rid)
        if not b:
            return [], False
        stack, locals_, reqs, dynamic = [], {}, None, False
        for ins in b.instructions:
            op = ins.opcode.name
            o = ins.operand
            tok = o.value if isinstance(o, (Token, InvalidToken)) else None
            if op.startswith('ldc.i4'):
                if op == 'ldc.i4.m1':
                    stack.append(-1)
                elif op in ('ldc.i4.s', 'ldc.i4'):
                    stack.append(int(o))
                else:
                    stack.append(int(op.split('.')[-1]))
            elif op == 'ldtoken':
                stack.append(resolve_tok(tok))
            elif op == 'call' and tok is not None and resolve_tok(tok)[0] == 'method':
                callee = resolve_tok(tok)[1]
                cname = str(md.MethodDef.rows[callee - 1].Name)
                if cname == 'j0' and stack and stack[-1] == 'this':
                    stack.pop()
                    base, dyn = interpret(owner.get(callee), depth + 1)
                    dynamic |= dyn
                    stack.append(list(base))
                else:
                    dynamic = True
                    stack.append(None)
            elif op == 'call':
                pass  # Type.GetTypeFromHandle etc. keep the ldtoken value
            elif op == 'ldarg.0':
                stack.append('this')
            elif op == 'ldnull':
                stack.append(None)
            elif op == 'ldsfld':
                v = static_int(tok) if tok is not None else None
                if v is None:
                    dynamic = True
                stack.append(v)
            elif op == 'add':
                b2 = stack.pop() if stack else None
                a2 = stack.pop() if stack else None
                stack.append(a2 + b2 if isinstance(a2, int) and isinstance(b2, int) else None)
            elif op in ('brtrue', 'brtrue.s', 'brfalse', 'brfalse.s'):
                # "if (list == null) list = new List()" after the base call: follow the fall-through
                v = stack.pop() if stack else None
                if isinstance(v, list) and v:
                    # base produced requirements: the code skips creating a new list
                    reqs = v
            elif op.startswith('nop'):
                pass
            elif op == 'newarr':
                n = stack.pop() if stack else 0
                stack.append([None] * (n if isinstance(n, int) else 0))
            elif op == 'dup':
                stack.append(stack[-1] if stack else None)
            elif op == 'stelem.ref':
                v = stack.pop(); i = stack.pop(); arr = stack.pop()
                if isinstance(arr, list) and isinstance(i, int) and i < len(arr):
                    arr[i] = v
                if v is None:
                    dynamic = True
            elif op == 'newobj':
                kind, target = resolve_tok(tok) if tok is not None else ('other', None)
                if kind != 'method':
                    # List<T> constructor (generic MemberRef); keep base requirements if there were any
                    stack.append(list(reqs) if reqs else [])
                    continue
                cls_name = owner.get(target)
                n = ctor_param_count(target)
                args = [stack.pop() for _ in range(n)][::-1] if len(stack) >= n else []
                kind = req_kind(cls_name)
                stack.append(('req', kind if kind != '?' else '?' + str(cls_name), args))
            elif op.startswith('stloc'):
                idx = int(op.split('.')[-1]) if '.' in op and op.split('.')[-1].isdigit() else o
                locals_[idx] = stack.pop() if stack else None
            elif op.startswith('ldloc'):
                idx = int(op.split('.')[-1]) if '.' in op and op.split('.')[-1].isdigit() else o
                stack.append(locals_.get(idx))
            elif op in ('callvirt',):
                if stack and stack[-1] == 'this':
                    stack.pop()
                    dynamic = True
                    stack.append(None)
                elif len(stack) >= 2 and isinstance(stack[-2], list):
                    item = stack.pop(); lst = stack.pop()
                    lst.append(item)
                    if reqs is None:
                        reqs = lst
                else:
                    dynamic = True
                    stack.append(None)
            elif op == 'ret':
                v = stack.pop() if stack else None
                if isinstance(v, list):
                    reqs = v
                break
            else:
                dynamic = True
        return [r for r in (reqs or []) if isinstance(r, tuple)], dynamic

    def names(arr, fn):
        return [fn(x[1]) for x in arr if isinstance(x, tuple) and x[0] == 'type'] if isinstance(arr, list) else []

    def feat_id(cls):
        for a, arg in attrs.get(cls, []):
            if a == feat_attr and arg:
                return arg.lower()
        return cls.lower()

    def skill_name(cls):
        for a, arg in attrs.get(cls, []):
            if arg and not arg.isupper() and len(arg) > 3:
                return arg
        return cls

    def attr_name(cls):
        for r in methods(cls, '.ctor'):
            s = strings_in(r)
            if s:
                return s[0]
        return cls

    def psi_name(cls):
        a = attrs.get(cls, [])
        return a[0][1] if a and a[0][1] else cls

    # the feat id attribute is the one whose values match the feat ids in data/knowledge/feats.k
    import gamedata
    known = set(gamedata.knowledge('feats'))
    score = {}
    for n, lst in attrs.items():
        for a, arg in lst:
            if arg and arg.lower() in known:
                score[a] = score.get(a, 0) + 1
    feat_attr = max(score, key=score.get)
    feat_classes = [n for n, lst in attrs.items() if any(a == feat_attr for a, _ in lst)]

    def const_bool(cls, name):
        """Constant returned by a (possibly inherited) parameterless bool method, else None."""
        c = cls
        while c:
            for r in methods(c, name):
                b = body(r)
                ins = list(b.instructions) if b else []
                if len(ins) == 2 and ins[0].opcode.name in ('ldc.i4.0', 'ldc.i4.1') and ins[1].opcode.name == 'ret':
                    return ins[0].opcode.name == 'ldc.i4.1'
                return None
            c = extends.get(c)
        return None

    # The feat base class has a bool method that the level-up screen filters on and whose false
    # value makes the tooltip say "This feat was acquired outside leveling." Find it by that string.
    # the feat base class: the ancestor shared by most feat classes
    anc_count = {}
    for c in feat_classes:
        for a_ in [c] + ancestors(c):
            if a_ and a_ != 'System.Object':
                anc_count[a_] = anc_count.get(a_, 0) + 1
    feat_base = max((a_ for a_ in anc_count if a_ not in feat_classes), key=anc_count.get)
    # Candidates: constant bool methods of the feat base queried by that tooltip method. The right
    # one is false for every tattoo (tattoos are only ever given by events) and true for most feats
    # that have regular requirements.
    candidates = set()
    for r in range(1, len(md.MethodDef.rows) + 1):
        if any('acquired outside leveling' in x for x in strings_in(r)):
            b = body(r)
            for ins in b.instructions if b else []:
                if ins.opcode.name == 'callvirt' and isinstance(ins.operand, (Token, InvalidToken)):
                    kind, target = resolve_tok(ins.operand.value)
                    if kind == 'method' and owner.get(target) == feat_base:
                        candidates.add(str(md.MethodDef.rows[target - 1].Name))
    tattoos = [c for c in feat_classes if feat_id(c).startswith('tattoo')]
    regular = [c for c in feat_classes if interpret(c)[0]]

    def score(name):
        if any(const_bool(c, name) is not False for c in tattoos):
            return -1
        return sum(const_bool(c, name) is True for c in regular)
    selectable_method = max(candidates, key=score) if candidates else None
    if selectable_method and score(selectable_method) <= len(regular) // 2:
        selectable_method = None  # no convincing candidate: leave the flag out

    out = {}
    for cls in feat_classes:
        fid = feat_id(cls)
        ctor = []
        for r in methods(cls, '.ctor'):
            b = body(r)
            prev = None
            for ins in b.instructions if b else []:
                if ins.opcode.name in ('call', 'callvirt') and isinstance(prev, str) and \
                        isinstance(ins.operand, (Token, InvalidToken)) and \
                        resolve_tok(ins.operand.value)[0] == 'method' and \
                        str(md.MethodDef.rows[resolve_tok(ins.operand.value)[1] - 1].Name) == '.ctor':
                    ctor.append(prev)
                prev = pe.net.user_strings.get(ins.operand.value & 0xFFFFFF).value \
                    if isinstance(ins.operand, StringToken) else None
        reqs, dynamic = interpret(cls)
        parsed = []
        for _, kind, args in reqs:
            ints = [a for a in args if isinstance(a, int)]
            arrays = [a for a in args if isinstance(a, list)]
            typ = [a for a in args if isinstance(a, tuple) and a[0] == 'type']
            r = {'kind': kind}
            if kind == 'attribute' and typ and ints:
                r.update(attribute=attr_name(typ[0][1]), min=ints[0], modified=bool(len(ints) > 1 and ints[1]))
            elif kind == 'skill' and ints:
                r.update(min=ints[0], modified=bool(len(ints) > 1 and ints[1]),
                         skills=names(arrays[0] if arrays else [], skill_name))
                if not r['skills'] or len(r['skills']) < len(arrays[0] if arrays else []):
                    r['dynamic'] = True
            elif kind in ('feat', 'not_feat') and arrays:
                r['feats'] = names(arrays[0], feat_id)
            elif kind == 'psi' and arrays:
                r['abilities'] = names(arrays[0], psi_name)
            elif kind in ('any_psi', 'level') and ints:
                r.update(min=ints[0], modified=bool(len(ints) > 1 and ints[1]))
            elif kind.startswith('?'):
                r = {'kind': 'other'}
            parsed.append(r)
        out[fid] = {'name': ctor[0] if ctor else fid, 'requires': parsed}
        if selectable_method:
            out[fid]['selectable'] = bool(const_bool(cls, selectable_method))
        if dynamic:
            out[fid]['dynamic'] = True
    resolve_runtime_parts(out)
    return out


SCHOOL_SKILLS = {'metathermics': 'Metathermics', 'psychokinesis': 'Psychokinesis',
                 'temporalmanipulation': 'Temporal Manipulation', 'thoughtcontrol': 'Thought Control'}


def resolve_runtime_parts(feats):
    """Fills in the two requirement patterns the game computes at runtime (read from its IL):
    * Empowered Invocation feats require 100 points in their own psi school's skill
    * Tempered feats exclude all other Tempered feats (the list is built from the feat registry)"""
    for fid, f in feats.items():
        if fid.startswith('empoweredinvocation'):
            school = SCHOOL_SKILLS.get(fid[len('empoweredinvocation'):])
            for r in f['requires']:
                if r.get('dynamic') and r['kind'] == 'skill' and school:
                    r['skills'] = [school]
                    del r['dynamic']
        if fid.startswith('tempered'):
            others = sorted(k for k in feats if k.startswith('tempered') and k != fid)
            f['requires'].append({'kind': 'not_feat', 'feats': others})
        if not any(r.get('dynamic') for r in f['requires']) and fid.startswith(('empoweredinvocation', 'tempered')):
            f.pop('dynamic', None)


if __name__ == '__main__':
    import gamedata
    exe = sys.argv[1] if len(sys.argv) > 1 else os.path.join(gamedata.GAME, 'underrail.exe')
    feats = main(exe)
    dst = os.path.join(ROOT, 'data', 'feat_requirements.json')
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, 'w') as f:
        json.dump({'source': 'underrail.exe', 'feats': dict(sorted(feats.items()))}, f, indent=1)
    print(f'{len(feats)} feats -> {dst}')
