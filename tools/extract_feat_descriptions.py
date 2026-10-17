#!/usr/bin/env python3
"""Extracts the values the game inserts into feat and specialization descriptions from underrail.exe
into data/feat_descriptions.json.

Developer tool, not needed to run the editor. Needs: pip install dnfile dncil
  python tools/extract_feat_descriptions.py [path/to/underrail.exe]

How the game fills the descriptions (found by reading its IL):
  * the description texts in data/knowledge/feats.k and specialization.k contain .NET String.Format
    placeholders {0}..{4}; the tooltip code calls  String.Format(knowledge("Feats/" + key), feat.Args())
  * Args() is a parameterless virtual method of the feat base class (and of the specialization base
    class) returning object[]; the base returns an empty array, feats override it. Typical body:
        new object[] { (int)(StaticField * 100.0), Convert.ToInt32(Other * 100.0), Turns(Cooldown, false) }
    with the static fields set to constants in the class's static constructor
  * helpers called from there: a turn formatter (ceil(seconds / seconds-per-turn) + " " + localized
    "turn"/"turns" from ui.k), a damage-range struct formatter, enum/attribute display names (looked up
    in the knowledge files or the attribute class's constructor), Math.Round/Ceiling, Convert.ToInt32,
    Double.ToString(format), string concatenation
  * none of the Args() methods reads the player character: every value is a constant of the game
    data, so all resolved values are emitted as final text
Class and member names are obfuscated, so nothing is matched by name: the Args() method is found by its
signature (instance, no parameters, returns object[]) on the feat/spec base class, and its IL is run by
a small symbolic CIL interpreter (below) that also runs static/instance constructors and inlines the
game helpers it calls. The knowledge lookup helper is recognised by the "Failed to load knowledge item"
string of the loader it calls and answered from the game's .k files.

Output: {"source": "underrail.exe", "feats": {feat id: [arg, ...]}, "specs": {spec key: [arg, ...]}}
where each arg is {"text": "<exactly what String.Format inserts>"} or null when the interpreter could
not resolve it.
"""
import json
import math
import os
import re
import struct
import sys
from decimal import ROUND_HALF_UP, Decimal

from dncil.clr.argument import Argument
from dncil.clr.local import Local
from dncil.clr.token import InvalidToken, Token

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract_feat_requirements as ex  # noqa: E402


class Abort(Exception):
    """The interpreter cannot follow the method (unknown branch condition, exception, too deep)."""


class _Unknown:
    def __repr__(self):
        return 'UNK'


UNK = _Unknown()


class F32(float):
    """A System.Single value (formatted with 7 significant digits)."""


def f32(x):
    return F32(struct.unpack('<f', struct.pack('<f', x))[0])


class TypeV:
    def __init__(self, cls):
        self.cls = cls

    def __eq__(self, o):
        return isinstance(o, TypeV) and o.cls == self.cls

    def __hash__(self):
        return hash(self.cls)


class Obj:
    def __init__(self, cls):
        self.cls = cls
        self.fields = {}


class Arr:
    def __init__(self, items):
        self.items = items


class EnumV:
    def __init__(self, cls, value, name):
        self.cls, self.value, self.name = cls, value, name


class SB:
    """System.Text.StringBuilder"""

    def __init__(self, s=''):
        self.s = s


class Ref:
    """Managed pointer (ldloca/ldarga/ldflda/ldsflda)."""

    def __init__(self, get, set_):
        self.get, self.set = get, set_


def unknown(v):
    return v is UNK


# ---------------------------------------------------------------- .NET formatting

def g_format(x, digits):
    """.NET Framework Double.ToString() ("G15") / Single.ToString() ("G7"), invariant culture."""
    if math.isnan(x):
        return 'NaN'
    if math.isinf(x):
        return 'Infinity' if x > 0 else '-Infinity'
    s = format(x, f'.{digits}g')
    if 'e' in s:
        m, e = s.split('e')
        return f'{m}E{e[0]}{int(e[1:]):02d}'
    return '0' if s == '-0' else s


def round_half_up(x, places):
    d = Decimal(g_format(float(x), 15)) if not isinstance(x, int) else Decimal(x)
    return d.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def custom_format(x, fmt):
    """Numeric format strings used by the game: standard F/N/P/D<n> and simple custom patterns
    like "0", "0.0", "0.##", "#,##0.0", optionally with a literal %."""
    f = fmt.strip()
    if f and f[0] in 'FfNnPpDd' and (len(f) == 1 or f[1:].isdigit()):
        kind = f[0].upper()
        n = int(f[1:]) if len(f) > 1 else (0 if kind == 'D' else 2)
        if kind == 'D':
            return str(int(x)).rjust(n, '0') if x >= 0 else '-' + str(-int(x)).rjust(n, '0')
        v = x * 100 if kind == 'P' else x
        d = round_half_up(v, n)
        s = f'{d:,.{n}f}' if kind in 'NP' else f'{d:.{n}f}'
        return s + ' %' if kind == 'P' else s
    pct = '%' in f
    core = f.replace('%', '')
    intpart, _, frac = core.partition('.')
    if set(intpart) - set('#0,') or set(frac) - set('#0'):
        return None
    v = x * 100 if pct else x
    d = round_half_up(v, len(frac))
    s = f'{d:,.{len(frac)}f}' if ',' in intpart else f'{d:.{len(frac)}f}'
    if frac:
        ip, fp = s.split('.')
        keep = len(frac.rstrip('#'))
        fp = fp[:keep] + fp[keep:].rstrip('0')
        s = ip + ('.' + fp if fp else '')
    if intpart.count('0') == 0 and s.lstrip('-').startswith('0') and '.' in s:
        s = s.replace('0.', '.', 1)
    return s + ('%' if pct else '')


def to_str(v, fmt=None):
    """Object.ToString()/IFormattable.ToString(fmt) of an interpreter value; None if unknown."""
    if unknown(v):
        return None
    if v is None:
        return ''
    if isinstance(v, str):
        return v
    if isinstance(v, bool):
        return 'True' if v else 'False'
    if isinstance(v, EnumV):
        return v.name
    if isinstance(v, (int, float)):
        if fmt:
            return custom_format(v, fmt)
        if isinstance(v, int):
            return str(v)
        return g_format(v, 7 if isinstance(v, F32) else 15)
    if isinstance(v, SB):
        return v.s
    if isinstance(v, TypeV):
        return v.cls
    return None


def net_format(fmt, args):
    """String.Format with composite format items {index[,alignment][:format]}."""
    out, i = [], 0
    while i < len(fmt):
        c = fmt[i]
        if c == '{' and fmt[i + 1:i + 2] == '{':
            out.append('{'); i += 2; continue
        if c == '}' and fmt[i + 1:i + 2] == '}':
            out.append('}'); i += 2; continue
        if c == '{':
            j = fmt.index('}', i)
            item = fmt[i + 1:j]
            spec = None
            if ':' in item:
                item, spec = item.split(':', 1)
            align = 0
            if ',' in item:
                item, a = item.split(',', 1)
                align = int(a)
            idx = int(item)
            if idx >= len(args):
                return UNK
            s = to_str(args[idx], spec)
            if s is None:
                return UNK
            out.append(s.rjust(align) if align > 0 else s.ljust(-align))
            i = j + 1
            continue
        out.append(c)
        i += 1
    return ''.join(out)


# ---------------------------------------------------------------- signatures

def _cuint(b, i):
    if b[i] & 0x80 == 0:
        return b[i], i + 1
    if b[i] & 0xC0 == 0x80:
        return ((b[i] & 0x3F) << 8) | b[i + 1], i + 2
    return ((b[i] & 0x1F) << 24) | (b[i + 1] << 16) | (b[i + 2] << 8) | b[i + 3], i + 4


def _type(b, i):
    """Parses one type of a signature blob -> (descriptor, next index)."""
    e = b[i]
    i += 1
    if e in (0x0F, 0x10, 0x1D, 0x45):  # ptr, byref, szarray, pinned
        t, i = _type(b, i)
        return (e, t), i
    if e in (0x11, 0x12):  # valuetype / class + TypeDefOrRef coded token
        tok, i = _cuint(b, i)
        return (e, tok), i
    if e in (0x13, 0x1E):  # generic var
        n, i = _cuint(b, i)
        return (e, n), i
    if e == 0x15:  # generic instantiation
        t, i = _type(b, i)
        n, i = _cuint(b, i)
        for _ in range(n):
            _, i = _type(b, i)
        return (e, t), i
    if e == 0x14:  # general array
        t, i = _type(b, i)
        rank, i = _cuint(b, i)
        n, i = _cuint(b, i)
        for _ in range(n):
            _, i = _cuint(b, i)
        n, i = _cuint(b, i)
        for _ in range(n):
            _, i = _cuint(b, i)
        return (e, t), i
    if e in (0x1F, 0x20):  # custom modifiers
        _, i = _cuint(b, i)
        return _type(b, i)
    return e, i


def method_sig(blob):
    """-> (hasthis, [param types], return type)"""
    b = bytes(blob)
    flags = b[0]
    i = 1
    if flags & 0x10:
        _, i = _cuint(b, i)
    n, i = _cuint(b, i)
    ret, i = _type(b, i)
    params = []
    for _ in range(n):
        if b[i] == 0x41:  # sentinel
            i += 1
        t, i = _type(b, i)
        params.append(t)
    return bool(flags & 0x20), params, ret


def _blob(x):
    return bytes(x.value) if hasattr(x, 'value') else bytes(x)


# ---------------------------------------------------------------- interpreter

class Machine:
    MAX_DEPTH = 14
    MAX_STEPS = 50000

    def __init__(self, exe):
        import gamedata
        self.gamedata = gamedata
        (self.pe, self.md, self.tname, self.types, self.owner, self.extends, self.body,
         self.methods, self.strings_in, self.attrs) = ex.load(exe)
        md = self.md
        self.field_owner = {}
        for t in self.types:
            for fl in t.FieldList:
                self.field_owner[fl.row_index] = self.tname(t)
        self.enum_consts = {}  # enum class -> {value: name}
        for c in md.Constant.rows:
            if c.Parent.table.name == 'Field':
                rid = c.Parent.row_index
                cls = self.field_owner.get(rid)
                if cls and self.extends.get(cls) == 'System.Enum':
                    raw = bytes(c.Value.value)
                    v = int.from_bytes(raw[:4].ljust(4, b'\0'), 'little', signed=True) if len(raw) <= 4 else \
                        int.from_bytes(raw[:8], 'little', signed=True)
                    self.enum_consts.setdefault(cls, {}).setdefault(v, str(md.Field.rows[rid - 1].Name))
        self.statics = {}
        self.cctor_done = set()
        self._bodies = {}
        self._sigs = {}
        self._knowledge = {}
        self.knowledge_lookup = self._find_knowledge_lookup()
        self.failures = {}
        self.typerows = {self.tname(t): t for t in self.types}

    # -- metadata helpers
    def mname(self, rid):
        return str(self.md.MethodDef.rows[rid - 1].Name)

    def msig(self, rid):
        if rid not in self._sigs:
            self._sigs[rid] = method_sig(_blob(self.md.MethodDef.rows[rid - 1].Signature))
        return self._sigs[rid]

    def instructions(self, rid):
        if rid not in self._bodies:
            b = self.body(rid)
            ins = list(b.instructions) if b else None
            self._bodies[rid] = (ins, {x.offset: k for k, x in enumerate(ins)} if ins else {})
        return self._bodies[rid]

    def ustr(self, tok):
        return self.pe.net.user_strings.get(tok.value & 0xFFFFFF).value

    def field_type(self, rid):
        b = _blob(self.md.Field.rows[rid - 1].Signature)
        return _type(b, 1)[0]

    def field_static(self, rid):
        return bool(self.md.Field.rows[rid - 1].Flags.fdStatic)

    def typedef_or_ref_name(self, coded):
        tag, rid = coded & 3, coded >> 2
        try:
            if tag == 0:
                return self.tname(self.types[rid - 1])
            if tag == 1:
                return self.tname(self.md.TypeRef.rows[rid - 1])
        except IndexError:
            pass
        return None

    def token_type_name(self, tok):
        table, rid = tok >> 24, tok & 0xFFFFFF
        if table == 0x02:
            return self.tname(self.types[rid - 1])
        if table == 0x01:
            return self.tname(self.md.TypeRef.rows[rid - 1])
        return None

    def default(self, t):
        if t in (0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x18, 0x19):
            return 0
        if t == 0x0C:
            return F32(0.0)
        if t == 0x0D:
            return 0.0
        if isinstance(t, tuple) and t[0] == 0x11:
            n = self.typedef_or_ref_name(t[1])
            if n in self.enum_consts:
                return 0
            return Obj(n) if n in self.extends else UNK
        return None

    def coerce(self, t, v):
        if t == 0x0C and isinstance(v, (int, float)) and not isinstance(v, bool):
            return f32(v)
        if t == 0x0D and isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
        if t == 0x02 and isinstance(v, int):
            return bool(v)
        return v

    def is_subclass(self, cls, base):
        c, n = cls, 0
        while c and n < 30:
            if c == base:
                return True
            c, n = self.extends.get(c), n + 1
        return False

    def virtual(self, cls, rid):
        """Override of method rid in cls's hierarchy (same name and signature)."""
        name, s = self.mname(rid), _blob(self.md.MethodDef.rows[rid - 1].Signature)
        c, n = cls, 0
        while c and n < 30:
            for r in self.methods(c, name):
                if _blob(self.md.MethodDef.rows[r - 1].Signature) == s:
                    return r
            c, n = self.extends.get(c), n + 1
        return rid

    def _find_knowledge_lookup(self):
        loaders = set()
        for rid in range(1, len(self.md.MethodDef.rows) + 1):
            try:
                if any("Failed to load knowledge item" in s for s in self.strings_in(rid)):
                    loaders.add(rid)
            except Exception:
                continue
        for loader in loaders:
            for rid in self.methods(self.owner[loader]):
                hasthis, params, ret = self.msig(rid)
                if hasthis or params != [0x0E] or ret != 0x0E:
                    continue
                ins, _ = self.instructions(rid)
                if any(i.opcode.name == 'call' and isinstance(i.operand, (Token, InvalidToken))
                       and i.operand.value == (0x06 << 24 | loader) for i in ins or []):
                    return rid
        return None

    def knowledge(self, path):
        f, _, key = path.partition('/')
        f = f.lower()
        if f not in self._knowledge:
            try:
                self._knowledge[f] = self.gamedata.knowledge(f)
            except OSError:
                self._knowledge[f] = {}
        return self._knowledge[f].get(key.lower(), '') or ''

    # -- objects
    def ensure_cctor(self, cls):
        if cls in self.cctor_done:
            return
        self.cctor_done.add(cls)
        for rid in self.methods(cls, '.cctor'):
            try:
                self.run(rid, [], 0, lenient=True)
            except Abort:
                pass

    def new_object(self, cls):
        o = Obj(cls)
        c, n = cls, 0
        while c and n < 30:
            t = self.typerows.get(c)
            if t is not None:
                for fl in t.FieldList:
                    if not self.field_static(fl.row_index):
                        o.fields[fl.row_index] = self.default(self.field_type(fl.row_index))
            c, n = self.extends.get(c), n + 1
        return o

    def instance(self, cls):
        """An object of cls built by its parameterless constructor."""
        self.ensure_cctor(cls)
        o = self.new_object(cls)
        for rid in self.methods(cls, '.ctor'):
            if not self.msig(rid)[1]:
                try:
                    self.run(rid, [o], 0, lenient=True)
                except Abort:
                    pass
                break
        return o

    # -- framework methods
    def builtin(self, cls, name, args, params, hasthis):
        """Framework MemberRef calls the game's helpers use. Returns UNK for anything else."""
        def val(x):
            return x.get() if isinstance(x, Ref) else x
        a = [val(x) for x in args]
        if any(unknown(x) for x in a) and not (cls == 'System.String' and name == 'Concat'):
            return UNK
        num = all(isinstance(x, (int, float)) for x in a)
        if cls == 'System.Math' and num and a:
            x = a[0]
            if name == 'Round':
                if len(a) == 2 and params[1] in (0x08,):
                    return float(round(x, a[1]))
                if len(a) == 1:
                    return float(round(x))
            if name == 'Ceiling':
                return float(math.ceil(x))
            if name == 'Floor':
                return float(math.floor(x))
            if name == 'Truncate':
                return float(math.trunc(x))
            if name == 'Abs':
                return abs(x)
            if name == 'Max' and len(a) == 2:
                return max(a)
            if name == 'Min' and len(a) == 2:
                return min(a)
            if name == 'Pow':
                return float(x ** a[1])
            if name == 'Sqrt':
                return math.sqrt(x)
            return UNK
        if cls == 'System.Convert' and a:
            x = a[0]
            if name in ('ToInt32', 'ToInt64', 'ToInt16') and isinstance(x, (int, float)):
                return int(round(x)) if isinstance(x, float) else int(x)
            if name == 'ToDouble' and isinstance(x, (int, float)):
                return float(x)
            if name == 'ToSingle' and isinstance(x, (int, float)):
                return f32(x)
            if name == 'ToString':
                s = to_str(x)
                return UNK if s is None else s
            return UNK
        if name == 'GetTypeFromHandle':
            return a[0]
        if name == '.ctor' and cls == 'System.Object':
            return None
        if cls == 'System.String':
            if name == 'Concat':
                parts = a[0].items if len(a) == 1 and isinstance(a[0], Arr) else a
                ss = [to_str(p) for p in parts]
                return UNK if any(s is None for s in ss) else ''.join(ss)
            if name == 'Format' and a and isinstance(a[0], str):
                rest = a[1].items if len(a) == 2 and isinstance(a[1], Arr) else a[1:]
                return net_format(a[0], rest)
            if name in ('IsNullOrEmpty', 'IsNullOrWhiteSpace'):
                return int(a[0] is None or (a[0].strip() if name.endswith('Space') else a[0]) == '')
            if name in ('op_Equality', 'Equals') and len(a) == 2:
                return int(a[0] == a[1])
            if name == 'op_Inequality':
                return int(a[0] != a[1])
            s = a[0] if a and isinstance(a[0], str) else None
            if s is None:
                return UNK
            if name in ('ToLowerInvariant', 'ToLower'):
                return s.lower()
            if name in ('ToUpperInvariant', 'ToUpper'):
                return s.upper()
            if name == 'Trim' and len(a) == 1:
                return s.strip()
            if name == 'get_Length':
                return len(s)
            if name == 'get_Chars':
                return ord(s[a[1]])
            if name == 'Substring':
                return s[a[1]:] if len(a) == 2 else s[a[1]:a[1] + a[2]]
            if name == 'Replace' and all(isinstance(x, str) for x in a[1:]):
                return s.replace(a[1], a[2])
            if name == 'Contains' and isinstance(a[1], str):
                return int(a[1] in s)
            if name == 'StartsWith' and len(a) == 2 and isinstance(a[1], str):
                return int(s.startswith(a[1]))
            if name == 'Insert':
                return s[:a[1]] + a[2] + s[a[1]:]
            if name == 'ToString':
                return s
            return UNK
        if cls == 'System.Text.StringBuilder' and a and isinstance(a[0], SB):
            sb = a[0]
            if name == 'get_Chars':
                return ord(sb.s[a[1]])
            if name == 'get_Length':
                return len(sb.s)
            if name == 'Insert':
                ins = to_str(a[2])
                sb.s = sb.s[:a[1]] + ins + sb.s[a[1]:]
                return sb
            if name == 'Append':
                sb.s += to_str(a[1]) or ''
                return sb
            if name == 'ToString':
                return sb.s
            return UNK
        if name == 'ToString' and hasthis:
            fmt = a[1] if len(a) > 1 and isinstance(a[1], str) else None
            if len(a) > 1 and fmt is None and not (len(a) == 2 and a[1] is None):
                return UNK  # IFormatProvider overloads
            s = to_str(a[0], fmt)
            return UNK if s is None else s
        if name == 'GetType' and a:
            o = a[0]
            if isinstance(o, Obj):
                return TypeV(o.cls)
            if isinstance(o, EnumV):
                return TypeV(o.cls)
            return UNK
        if cls == 'System.Type':
            if name == 'get_Name' and isinstance(a[0], TypeV):
                return a[0].cls.rsplit('.', 1)[-1]
            if name == 'get_FullName' and isinstance(a[0], TypeV):
                return a[0].cls
            if name in ('op_Equality', 'op_Inequality') and len(a) == 2:
                eq = a[0] == a[1]
                return int(eq if name == 'op_Equality' else not eq)
        return UNK

    def memberref_name(self, rid):
        """MemberRef -> (declaring class name, member name)"""
        row = self.md.MemberRef.rows[rid - 1]
        try:
            parent = row.Class.row
            cls = self.tname(parent) if hasattr(parent, 'TypeName') else '?'
        except Exception:
            cls = '?'
        return cls, str(row.Name)

    def memberref(self, rid):
        """-> (class name, method name, (hasthis, params, ret))"""
        return (*self.memberref_name(rid), method_sig(_blob(self.md.MemberRef.rows[rid - 1].Signature)))

    # -- calls
    def call(self, tok, stack, virt, constrained, depth):
        table, rid = tok >> 24, tok & 0xFFFFFF
        if table == 0x2B:  # generic method instantiation: not followed
            row = self.md.MethodSpec.rows[rid - 1]
            m = row.Method
            if m.table.name == 'MethodDef':
                hasthis, params, ret = self.msig(m.row_index)
            else:
                hasthis, params, ret = self.memberref(m.row_index)[2]
            n = len(params) + hasthis
            del stack[len(stack) - n:]
            if ret != 0x01:
                stack.append(UNK)
            return
        if table == 0x0A:
            cls, name, (hasthis, params, ret) = self.memberref(rid)
            n = len(params) + hasthis
            args = stack[len(stack) - n:] if n else []
            del stack[len(stack) - n:]
            this = args[0] if hasthis and args else None
            tv = this.get() if isinstance(this, Ref) else this
            if constrained is not None and name == 'ToString' and not params and isinstance(this, Ref):
                # constrained. callvirt ToString on a value-type receiver: enums print their member name
                tn = self.token_type_name(constrained)
                if tn in self.enum_consts and isinstance(tv, int):
                    tv = EnumV(tn, tv, self.enum_consts[tn].get(tv, str(tv)))
                s = to_str(tv)
                stack.append(UNK if s is None else s)
                return
            if virt and hasthis and isinstance(tv, Obj) and name == 'ToString':
                over = next((r for c in self._chain(tv.cls) for r in self.methods(c, 'ToString')
                             if not self.msig(r)[1]), None)
                if over:
                    r = self.run(over, [tv], depth + 1)
                    stack.append(r)
                    return
            v = self.builtin(cls, name, args, params, hasthis)
            if ret != 0x01:
                stack.append(self.coerce(ret, v))
            return
        if table != 0x06:
            raise Abort(f'call token {tok:#x}')
        hasthis, params, ret = self.msig(rid)
        n = len(params) + hasthis
        args = stack[len(stack) - n:] if n else []
        del stack[len(stack) - n:]
        args = [args[0]] + [self.coerce(t, v) for t, v in zip(params, args[1:])] if hasthis else \
            [self.coerce(t, v) for t, v in zip(params, args)]
        if rid == self.knowledge_lookup:
            v = self.knowledge(args[0]) if isinstance(args[0], str) else UNK
            stack.append(v)
            return
        v = self.registry_lookup(args, ret)
        if v is not None:
            stack.append(v)
            return
        target = rid
        if hasthis and virt:
            tv = args[0].get() if isinstance(args[0], Ref) else args[0]
            if isinstance(tv, Obj):
                target = self.virtual(tv.cls, rid)
        ins, _ = self.instructions(target)
        if ins is None:
            v = UNK  # abstract / extern
        else:
            try:
                v = self.run(target, args, depth + 1)
            except Abort as e:
                self.failures.setdefault(f'{self.owner.get(target)}::{self.mname(target)}', str(e))
                v = UNK
        if ret != 0x01:
            stack.append(self.coerce(ret, v))

    def registry_lookup(self, args, ret):
        """Registry lookups "Get(typeof(T))" are not followed (they search runtime collections):
        a call with a single System.Type argument returning a base class of T yields an instance
        of T (the game uses this to fetch e.g. the attribute object for typeof(Agility))."""
        ts = [a for a in args if isinstance(a, TypeV)]
        if len(ts) == 1 and isinstance(ret, tuple) and ret[0] == 0x12:
            base = self.typedef_or_ref_name(ret[1])
            if base and self.is_subclass(ts[0].cls, base):
                return self.instance(ts[0].cls)
        return None

    def _chain(self, cls):
        c, n = cls, 0
        while c and n < 30:
            yield c
            c, n = self.extends.get(c), n + 1

    # -- method body
    def run(self, rid, args, depth, lenient=False):
        """Interprets method rid with the given arguments; returns its return value.
        lenient: ignore stores into unknown arrays (constructors also fill tables Args() never reads)."""
        if depth > self.MAX_DEPTH:
            raise Abort('too deep')
        ins, index = self.instructions(rid)
        if ins is None:
            raise Abort('no body')
        cls = self.owner.get(rid)
        self.ensure_cctor(cls)
        args = list(args)
        locals_ = {}
        stack = []
        pc, steps, constrained = 0, 0, None
        md = self.md

        def pop():
            if not stack:
                raise Abort('stack underflow')
            return stack.pop()

        def deref(v):
            return v.get() if isinstance(v, Ref) else v

        def branch(target):
            return index[target]

        def binop(op, a, b):
            a, b = deref(a), deref(b)
            if unknown(a) or unknown(b):
                return UNK
            if isinstance(a, bool):
                a = int(a)
            if isinstance(b, bool):
                b = int(b)
            if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
                if op in ('ceq',):
                    return int(a is b or a == b)
                return UNK
            fl = isinstance(a, float) or isinstance(b, float)
            both32 = isinstance(a, F32) and isinstance(b, F32)
            if op == 'add':
                r = a + b
            elif op == 'sub':
                r = a - b
            elif op == 'mul':
                r = a * b
            elif op in ('div', 'div.un'):
                if fl:
                    r = a / b if b else (math.copysign(math.inf, a) if a else math.nan)
                else:
                    if b == 0:
                        raise Abort('division by zero')
                    r = abs(a) // abs(b) * (1 if (a >= 0) == (b >= 0) else -1)
            elif op in ('rem', 'rem.un'):
                if fl:
                    r = math.fmod(a, b)
                else:
                    if b == 0:
                        raise Abort('division by zero')
                    r = a - b * (abs(a) // abs(b) * (1 if (a >= 0) == (b >= 0) else -1))
            elif op == 'and':
                r = int(a) & int(b)
            elif op == 'or':
                r = int(a) | int(b)
            elif op == 'xor':
                r = int(a) ^ int(b)
            elif op == 'shl':
                r = (int(a) << int(b)) & 0xFFFFFFFF
                r = r - (1 << 32) if r & 0x80000000 else r
            elif op in ('shr', 'shr.un'):
                r = int(a) >> int(b)
            elif op == 'ceq':
                return int(a == b)
            elif op in ('cgt', 'cgt.un'):
                return int(a > b)
            elif op in ('clt', 'clt.un'):
                return int(a < b)
            else:
                return UNK
            if fl:
                return f32(r) if both32 else float(r)
            return int(r)  # no 32-bit wraparound: the game's constants are small

        def cond(v):
            v = deref(v)
            if unknown(v):
                raise Abort('unknown branch condition')
            if isinstance(v, (int, float)):
                return v != 0
            if isinstance(v, (str, Obj, Arr, TypeV, EnumV, SB)):
                return True
            return v is not None

        def conv(op, v):
            v = deref(v)
            if unknown(v):
                return UNK
            if isinstance(v, EnumV):
                v = v.value
            if not isinstance(v, (int, float)):
                return UNK
            kind = op.split('.', 1)[1].replace('ovf.', '').replace('.un', '')
            if kind in ('r8', 'r'):
                return float(v)
            if kind == 'r4':
                return f32(v)
            if isinstance(v, float):
                if math.isnan(v) or math.isinf(v):
                    raise Abort('conv of non-finite')
                v = math.trunc(v)
            bits = {'i1': 8, 'u1': 8, 'i2': 16, 'u2': 16, 'i4': 32, 'u4': 32, 'i8': 64, 'u8': 64,
                    'i': 64, 'u': 64}.get(kind)
            if bits is None:
                return UNK
            v &= (1 << bits) - 1
            if kind.startswith('i') and v & (1 << (bits - 1)):
                v -= 1 << bits
            return v

        def field_ref(obj, frid):
            def get():
                o = deref(obj)
                if isinstance(o, Obj):
                    return o.fields.get(frid, self.default(self.field_type(frid)))
                return UNK

            def set_(v):
                o = deref(obj)
                if isinstance(o, Obj):
                    o.fields[frid] = v
                elif isinstance(obj, Ref):  # uninitialised struct local
                    no = self.new_object(self.field_owner.get(frid))
                    no.fields[frid] = v
                    obj.set(no)
            return Ref(get, set_)

        def static_ref(frid):
            owner_cls = self.field_owner.get(frid)
            if owner_cls:
                self.ensure_cctor(owner_cls)

            def get():
                return self.statics.get(frid, self.default(self.field_type(frid)))

            def set_(v):
                self.statics[frid] = v
            return Ref(get, set_)

        def var_index(op, o):
            if isinstance(o, (Local, Argument)):
                return o.index
            if isinstance(o, int):
                return o
            return int(op.rsplit('.', 1)[1])

        while True:
            steps += 1
            if steps > self.MAX_STEPS or pc >= len(ins):
                raise Abort('runaway')
            i = ins[pc]
            op = i.opcode.name
            o = i.operand
            tok = o.value if isinstance(o, (Token, InvalidToken)) else None
            pc += 1
            if op in ('nop', 'readonly.', 'volatile.', 'unaligned.', 'tail.') or op.startswith('nop'):
                continue
            if op == 'constrained.':
                constrained = tok
                continue
            if op.startswith('ldarg'):
                if op.startswith('ldarga'):
                    k = var_index(op, o)
                    stack.append(Ref(lambda k=k: args[k], lambda v, k=k: args.__setitem__(k, v)))
                else:
                    stack.append(args[var_index(op, o)])
            elif op.startswith('starg'):
                args[var_index(op, o)] = pop()
            elif op.startswith('ldloca'):
                k = var_index(op, o)
                stack.append(Ref(lambda k=k: locals_.get(k, 0), lambda v, k=k: locals_.__setitem__(k, v)))
            elif op.startswith('ldloc'):
                stack.append(locals_.get(var_index(op, o), 0))
            elif op.startswith('stloc'):
                locals_[var_index(op, o)] = pop()
            elif op.startswith('ldc.i4'):
                stack.append(-1 if op == 'ldc.i4.m1' else int(o) if op in ('ldc.i4', 'ldc.i4.s')
                             else int(op.split('.')[-1]))
            elif op == 'ldc.i8':
                stack.append(int(o))
            elif op == 'ldc.r4':
                stack.append(f32(o))
            elif op == 'ldc.r8':
                stack.append(float(o))
            elif op == 'ldstr':
                stack.append(self.ustr(o))
            elif op == 'ldnull':
                stack.append(None)
            elif op == 'dup':
                v = pop()
                stack += [v, v]
            elif op == 'pop':
                pop()
            elif op in ('add', 'sub', 'mul', 'div', 'div.un', 'rem', 'rem.un', 'and', 'or', 'xor', 'shl',
                        'shr', 'shr.un', 'ceq', 'cgt', 'cgt.un', 'clt', 'clt.un') or \
                    op.startswith(('add.ovf', 'sub.ovf', 'mul.ovf')):
                b = pop()
                a = pop()
                stack.append(binop(op.split('.ovf')[0], a, b))
            elif op == 'neg':
                v = deref(pop())
                stack.append(-v if isinstance(v, (int, float)) and not unknown(v) else UNK)
            elif op == 'not':
                v = deref(pop())
                stack.append(~v if isinstance(v, int) else UNK)
            elif op.startswith('conv.'):
                stack.append(conv(op, pop()))
            elif op in ('br', 'br.s', 'leave', 'leave.s'):
                pc = branch(o)
            elif op in ('brtrue', 'brtrue.s', 'brfalse', 'brfalse.s'):
                c = cond(pop())
                if c == op.startswith('brtrue'):
                    pc = branch(o)
            elif op.split('.')[0] in ('beq', 'bne', 'bge', 'bgt', 'ble', 'blt'):
                b = pop()
                a = pop()
                base = op.split('.')[0]
                if base in ('beq', 'bne'):
                    r = binop('ceq', a, b)
                elif base in ('bgt', 'ble'):
                    r = binop('cgt', a, b)
                else:
                    r = binop('clt', a, b)
                if unknown(r):
                    raise Abort('unknown branch condition')
                # unordered (.un) float compares: NaN makes ble.un/bge.un/bne.un true
                take = bool(r) if base in ('beq', 'bgt', 'blt') else not r
                if take:
                    pc = branch(o)
            elif op == 'switch':
                v = deref(pop())
                if not isinstance(v, int):
                    raise Abort('unknown switch')
                if 0 <= v < len(o):
                    pc = branch(o[v])
            elif op == 'ret':
                return pop() if stack else None
            elif op in ('call', 'callvirt'):
                if tok is None:
                    raise Abort('bad call')
                self.call(tok, stack, op == 'callvirt', constrained, depth)
                constrained = None
            elif op == 'newobj':
                table, crid = tok >> 24, tok & 0xFFFFFF
                if table == 0x06:
                    ocls = self.owner.get(crid)
                    self.ensure_cctor(ocls)
                    obj = self.new_object(ocls)
                    hasthis, params, ret = self.msig(crid)
                    n = len(params)
                    cargs = stack[len(stack) - n:] if n else []
                    del stack[len(stack) - n:]
                    try:
                        self.run(crid, [obj] + [self.coerce(t, v) for t, v in zip(params, cargs)], depth + 1,
                                 lenient=True)
                    except Abort:
                        pass
                    stack.append(obj)
                else:
                    cls_name, name, (hasthis, params, ret) = self.memberref(crid) if table == 0x0A else \
                        ('?', '?', (True, [], 1))
                    n = len(params)
                    cargs = stack[len(stack) - n:] if n else []
                    del stack[len(stack) - n:]
                    if cls_name == 'System.Text.StringBuilder' and len(cargs) <= 1:
                        s = deref(cargs[0]) if cargs else ''
                        stack.append(SB(s) if isinstance(s, str) else SB('') if s is None or not cargs else UNK)
                    else:
                        stack.append(UNK)
            elif op in ('ldfld', 'ldflda'):
                obj = pop()
                r = field_ref(obj, tok & 0xFFFFFF)
                stack.append(r if op == 'ldflda' else r.get())
            elif op == 'stfld':
                v = pop()
                obj = pop()
                frid = tok & 0xFFFFFF
                field_ref(obj, frid).set(self.coerce(self.field_type(frid), v))
            elif op in ('ldsfld', 'ldsflda'):
                if tok >> 24 != 0x04:  # framework static field: only String.Empty is known
                    known_ = tok >> 24 == 0x0A and self.memberref_name(tok & 0xFFFFFF) == ('System.String', 'Empty')
                    stack.append('' if known_ else UNK)
                    continue
                r = static_ref(tok & 0xFFFFFF)
                stack.append(r if op == 'ldsflda' else r.get())
            elif op == 'stsfld':
                v = pop()
                if tok >> 24 == 0x04:
                    frid = tok & 0xFFFFFF
                    static_ref(frid).set(self.coerce(self.field_type(frid), v))
            elif op == 'box':
                v = deref(pop())
                tn = self.token_type_name(tok)
                if tn in self.enum_consts and isinstance(v, int):
                    v = EnumV(tn, v, self.enum_consts[tn].get(v, str(v)))
                elif tn == 'System.Single' and isinstance(v, (int, float)):
                    v = f32(v)
                elif tn == 'System.Double' and isinstance(v, (int, float)):
                    v = float(v)
                elif tn == 'System.Boolean' and isinstance(v, int):
                    v = bool(v)
                stack.append(v)
            elif op in ('unbox.any', 'unbox'):
                v = pop()
                stack.append(v.value if isinstance(v, EnumV) else v)
            elif op == 'newarr':
                n = deref(pop())
                if not isinstance(n, int):
                    raise Abort('unknown array size')
                tn = self.token_type_name(tok)
                d = 0 if tn in ('System.Int32', 'System.Char', 'System.Int64', 'System.Boolean') else \
                    0.0 if tn == 'System.Double' else None
                stack.append(Arr([d] * n))
            elif op == 'ldlen':
                a = deref(pop())
                stack.append(len(a.items) if isinstance(a, Arr) else UNK)
            elif op.startswith('stelem'):
                v = pop()
                k = deref(pop())
                a = deref(pop())
                if isinstance(a, Arr) and isinstance(k, int) and 0 <= k < len(a.items):
                    a.items[k] = v
                elif not lenient:
                    raise Abort('bad stelem')
            elif op.startswith('ldelema'):
                k = deref(pop())
                a = deref(pop())
                if isinstance(a, Arr) and isinstance(k, int):
                    stack.append(Ref(lambda a=a, k=k: a.items[k], lambda v, a=a, k=k: a.items.__setitem__(k, v)))
                else:
                    stack.append(UNK)
            elif op.startswith('ldelem'):
                k = deref(pop())
                a = deref(pop())
                stack.append(a.items[k] if isinstance(a, Arr) and isinstance(k, int) and 0 <= k < len(a.items)
                             else UNK)
            elif op == 'ldtoken':
                tn = self.token_type_name(tok)
                stack.append(TypeV(tn) if tn else UNK)
            elif op == 'isinst':
                v = deref(pop())
                tn = self.token_type_name(tok)
                if isinstance(v, Obj):
                    stack.append(v if self.is_subclass(v.cls, tn) else None)
                elif v is None:
                    stack.append(None)
                else:
                    stack.append(UNK)
            elif op == 'castclass':
                pass
            elif op == 'initobj':
                r = pop()
                tn = self.token_type_name(tok)
                if isinstance(r, Ref):
                    r.set(self.new_object(tn) if tn in self.extends and tn not in self.enum_consts else 0)
            elif op.startswith('ldind') or op == 'ldobj':
                r = pop()
                stack.append(r.get() if isinstance(r, Ref) else UNK)
            elif op.startswith('stind') or op == 'stobj':
                v = pop()
                r = pop()
                if isinstance(r, Ref):
                    r.set(v)
            elif op in ('ldftn', 'ldvirtftn'):
                if op == 'ldvirtftn':
                    pop()
                stack.append(UNK)
            else:
                # throw, endfinally, rethrow, localloc, calli, ...
                raise Abort(f'unsupported {op}')


# ---------------------------------------------------------------- extraction

ARGS_SIG = b'\x20\x00\x1d\x1c'  # instance, no parameters, returns object[]


def args_method(m, cls):
    """The (possibly inherited) parameterless object[] method of cls."""
    for c in m._chain(cls):
        for r in m.methods(c):
            if _blob(m.md.MethodDef.rows[r - 1].Signature) == ARGS_SIG and m.mname(r) != '.ctor':
                return r
    return None


def evaluate(m, cls):
    rid = args_method(m, cls)
    if rid is None:
        return []
    this = m.instance(cls)
    try:
        arr = m.run(rid, [this], 0)
    except Abort as e:
        m.failures.setdefault(f'{cls}::{m.mname(rid)}', str(e))
        return None
    if not isinstance(arr, Arr):
        return None
    out = []
    for v in arr.items:
        s = to_str(v)
        out.append(None if s is None else {'text': s})
    return out


def main(exe):
    m = Machine(exe)
    import gamedata
    known = set(gamedata.knowledge('feats'))
    score = {}
    for n, lst in m.attrs.items():
        for a, arg in lst:
            if arg and arg.lower() in known:
                score[a] = score.get(a, 0) + 1
    feat_attr = max(score, key=score.get)
    feat_classes = {n: next(arg.lower() for a, arg in lst if a == feat_attr and arg)
                    for n, lst in m.attrs.items() if any(a == feat_attr and arg for a, arg in lst)}
    feats = {}
    for cls, fid in sorted(feat_classes.items(), key=lambda x: x[1]):
        feats[fid] = evaluate(m, cls)

    # specializations: classes with a constant method returning the owning feat type and one
    # returning the save key (see extract_feat_requirements.extract_specs)
    known_keys = set(gamedata.knowledge('specialization'))
    specs = {}
    for t in m.types:
        cls = m.tname(t)
        feat = key = None
        for r in m.methods(cls):
            ins, _ = m.instructions(r)
            ops = [i.opcode.name for i in ins or []]
            if ops == ['ldtoken', 'call', 'ret'] and isinstance(ins[0].operand, (Token, InvalidToken)):
                feat = feat or m.token_type_name(ins[0].operand.value) in feat_classes
            elif ops == ['ldstr', 'ret']:
                v = m.ustr(ins[0].operand)
                if v.lower() in known_keys and ' ' not in v:
                    key = v
        if feat and key:
            specs[key] = evaluate(m, cls)
    return feats, dict(sorted(specs.items())), m.failures


def summarize(label, data, descs):
    full = part = none = 0
    for k, args in data.items():
        need = sorted({int(x) for x in re.findall(r'\{(\d+)[^}]*\}', descs.get(k, ''))})
        if not need:
            continue
        got = [i for i in need if args and i < len(args) and args[i] is not None]
        if len(got) == len(need):
            full += 1
        elif got:
            part += 1
        else:
            none += 1
    print(f'{label}: {len(data)} classes; with placeholders: {full} fully resolved, {part} partially, {none} unresolved')


if __name__ == '__main__':
    import gamedata
    exe = sys.argv[1] if len(sys.argv) > 1 else os.path.join(gamedata.GAME, 'underrail.exe')
    feats, specs, failures = main(exe)
    dst = os.path.join(ROOT, 'data', 'feat_descriptions.json')
    with open(dst, 'w') as f:
        json.dump({'source': 'underrail.exe', 'feats': feats, 'specs': specs}, f, indent=1)
    summarize('feats', feats, {k: v[1] for k, v in gamedata.feats().items()})
    summarize('specs', specs, {k: v[1] for k, v in gamedata.specs().items()})
    for where, why in sorted(failures.items()):
        print(f'  not followed: {where} ({why})')
    print(f'-> {dst}')
