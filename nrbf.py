"""MS-NRBF (.NET BinaryFormatter) reader/writer.

The reader builds an object graph (Obj/Arr/Str/Prim/Ref) and remembers how every record was
encoded; the writer re-emits it the same way, so an unmodified graph round-trips byte-identically.
Modified or newly created objects get fresh class metadata where needed."""
import struct

PRIM_SIZE = {1: 1, 2: 1, 6: 8, 7: 2, 8: 4, 9: 8, 10: 1, 11: 4, 12: 8, 13: 8, 14: 2, 15: 4, 16: 8}
PRIM_FMT = {1: '<?', 2: '<B', 6: '<d', 7: '<h', 8: '<i', 9: '<q', 10: '<b', 11: '<f', 12: '<q',
            13: '<q', 14: '<H', 15: '<I', 16: '<Q'}
PRIM_NAME = {1: 'bool', 2: 'byte', 3: 'char', 5: 'decimal', 6: 'double', 7: 'int16', 8: 'int32',
             9: 'int64', 10: 'sbyte', 11: 'float', 12: 'timespan', 13: 'datetime', 14: 'uint16',
             15: 'uint32', 16: 'uint64', 18: 'string'}


class Prim:
    """Primitive value. `offset` is its position in the parsed buffer (None for new values)."""
    __slots__ = ('ptype', 'offset', 'value')

    def __init__(self, ptype, offset, value):
        self.ptype, self.offset, self.value = ptype, offset, value

    def __repr__(self):
        return f'{self.value!r}'


class Ref:
    __slots__ = ('id',)

    def __init__(self, id):
        self.id = id


class Obj:
    """Class instance. `rt` is the record type it was read as (1-5); `meta` the metadata id for rt 1.
    `bt`/`extra` are the member type infos (None for untyped records 2/3)."""
    __slots__ = ('id', 'cls', 'names', 'values', 'lib', 'bt', 'extra', 'rt', 'meta')

    def __init__(self, id, cls, names, lib=None, bt=None, extra=None, rt=5, meta=None):
        self.id, self.cls, self.names, self.values, self.lib = id, cls, list(names), [], lib
        self.bt, self.extra, self.rt, self.meta = bt, extra, rt, meta

    def get(self, name, default=None):
        try:
            return self.values[self.names.index(name)]
        except ValueError:
            return default

    def __contains__(self, name):
        return name in self.names


class Arr:
    """Array. For rt 15 with byte elements, `items` is a single Prim holding bytes."""
    __slots__ = ('id', 'items', 'etype', 'rt', 'atype', 'lens', 'lbounds')

    def __init__(self, id, etype, rt, atype=0, lens=None, lbounds=None):
        self.id, self.items, self.etype, self.rt = id, [], etype, rt
        self.atype, self.lens, self.lbounds = atype, lens, lbounds


class Str:
    __slots__ = ('id', 'value', 'offset')

    def __init__(self, id, value, offset=None):
        self.id, self.value, self.offset = id, value, offset


class _Nulls:
    def __init__(self, n):
        self.n = n


class Parser:
    def __init__(self, data):
        self.d = data
        self.p = 0
        self.objects = {}
        self.classinfo = {}  # metadata id -> (cls, names, bt, extra, lib, rt)
        self.libs = {}
        self.root = None
        self.header = None
        self.top = []  # top-level records in stream order

    def u8(self):
        v = self.d[self.p]; self.p += 1; return v

    def i32(self):
        v = struct.unpack_from('<i', self.d, self.p)[0]; self.p += 4; return v

    def lps(self):
        n = 0; shift = 0
        while True:
            b = self.u8(); n |= (b & 0x7f) << shift; shift += 7
            if not b & 0x80:
                break
        s = self.d[self.p:self.p + n].decode('utf-8'); self.p += n; return s

    def prim(self, t):
        off = self.p
        if t in PRIM_FMT:
            v = struct.unpack_from(PRIM_FMT[t], self.d, self.p)[0]; self.p += PRIM_SIZE[t]
        elif t == 3:
            b = self.d[self.p]
            n = 1 if b < 0x80 else 2 if b < 0xe0 else 3 if b < 0xf0 else 4
            v = self.d[self.p:self.p + n].decode('utf-8'); self.p += n
        elif t in (5, 18):
            v = self.lps()
        else:
            raise ValueError(f'bad prim type {t} at {self.p}')
        return Prim(t, off, v)

    def classinfo_(self):
        oid = self.i32(); name = self.lps(); n = self.i32()
        return oid, name, [self.lps() for _ in range(n)]

    def typeinfo(self, n):
        bt = [self.u8() for _ in range(n)]
        extra = []
        for t in bt:
            if t in (0, 7):
                extra.append(self.u8())
            elif t == 3:
                extra.append(self.lps())
            elif t == 4:
                extra.append((self.lps(), self.i32()))
            else:
                extra.append(None)
        return bt, extra

    def parse(self):
        while True:
            r = self.record()
            if r == 'END':
                break
            if r is not None:
                self.top.append(r)
        return self

    def record(self):
        start = self.p
        rt = self.u8()
        if rt == 0:
            self.root = self.i32(); self.header = (self.i32(), self.i32(), self.i32()); return None
        if rt == 11:
            return 'END'
        if rt == 12:
            lid = self.i32(); self.libs[lid] = self.lps(); return self.record()
        if rt in (1, 2, 3, 4, 5):
            if rt == 1:
                oid = self.i32(); mid = self.i32()
                cls, names, bt, extra, lib, _ = self.classinfo[mid]
            else:
                oid, cls, names = self.classinfo_()
                mid = oid
                bt = extra = None
                if rt in (4, 5):
                    bt, extra = self.typeinfo(len(names))
                lib = self.i32() if rt in (3, 5) else None
                self.classinfo[oid] = (cls, names, bt, extra, lib, rt)
            o = Obj(oid, cls, names, lib, bt, extra, rt, mid)
            self.objects[oid] = o
            o.values = self.members(len(names), bt, extra)
            return o
        if rt == 6:
            oid = self.i32(); off = self.p; s = Str(oid, self.lps(), off); self.objects[oid] = s; return s
        if rt == 7:
            oid = self.i32(); atype = self.u8(); rank = self.i32()
            lens = [self.i32() for _ in range(rank)]
            lb = [self.i32() for _ in range(rank)] if atype in (3, 4, 5) else None
            bt, extra = self.typeinfo(1)
            total = 1
            for l in lens:
                total *= l
            a = Arr(oid, (bt[0], extra[0]), 7, atype, lens, lb); self.objects[oid] = a
            a.items = self.members(total, bt * total, extra * total)
            return a
        if rt == 8:
            return self.prim(self.u8())
        if rt == 9:
            return Ref(self.i32())
        if rt == 10:
            return None
        if rt == 13:
            return _Nulls(self.u8())
        if rt == 14:
            return _Nulls(self.i32())
        if rt == 15:
            oid = self.i32(); n = self.i32(); t = self.u8()
            a = Arr(oid, (0, t), 15); self.objects[oid] = a
            if t == 2:  # byte[]: store as blob
                a.items = Prim(18, self.p, bytes(self.d[self.p:self.p + n])); self.p += n
            else:
                a.items = [self.prim(t) for _ in range(n)]
            return a
        if rt in (16, 17):
            oid = self.i32(); n = self.i32()
            a = Arr(oid, (2 if rt == 16 else 1, None), rt); self.objects[oid] = a
            a.items = self.members(n, None, None)
            return a
        raise ValueError(f'unknown record type {rt} at {start}')

    def members(self, n, bt, extra):
        out = []
        while len(out) < n:
            i = len(out)
            if bt is not None and bt[i] == 0:
                out.append(self.prim(extra[i]))
                continue
            v = self.record()
            if isinstance(v, _Nulls):
                out.extend([None] * v.n)
            else:
                out.append(v)
        return out


def resolve(p, v):
    return p.objects.get(v.id) if isinstance(v, Ref) else v


class Writer:
    """Serializes a parsed graph. `libs` maps library id -> name (from the parser)."""

    def __init__(self, parser):
        self.p = parser
        self.out = bytearray()
        self.libs_done = set()
        self.meta_done = {}  # original metadata id -> emitted metadata object id
        self.shape_done = {}  # class shape -> emitted metadata object id
        self.emitted = set()
        self.wanted = []  # referenced ids, emitted top-level if nothing wrote them inline

    def u8(self, v):
        self.out.append(v)

    def i32(self, v):
        self.out += struct.pack('<i', v)

    def lps(self, s):
        b = s.encode('utf-8'); n = len(b)
        while True:
            if n >= 0x80:
                self.u8((n & 0x7f) | 0x80); n >>= 7
            else:
                self.u8(n); break
        self.out += b

    def prim(self, t, v):
        if t in PRIM_FMT:
            self.out += struct.pack(PRIM_FMT[t], v)
        elif t == 3:
            self.out += v.encode('utf-8')
        elif t in (5, 18):
            self.lps(v)
        else:
            raise ValueError(f'bad prim type {t}')

    def lib(self, lid):
        if lid is not None and lid not in self.libs_done:
            self.u8(12); self.i32(lid); self.lps(self.p.libs[lid]); self.libs_done.add(lid)

    def write(self):
        p = self.p
        self.u8(0); self.i32(p.root); [self.i32(x) for x in p.header]
        live = reachable(p)
        for r in p.top:
            if r.id in live and r.id not in self.emitted:
                self.record(r)
        # objects whose inline parent was removed but are still referenced elsewhere
        while self.wanted:
            oid = self.wanted.pop(0)
            if oid not in self.emitted:
                self.record(p.objects[oid])
        self.u8(11)
        return bytes(self.out)

    @staticmethod
    def shape(o):
        return (o.cls, o.lib, tuple(o.names), tuple(o.bt) if o.bt else None,
                tuple(o.extra) if o.extra else None)

    def record(self, r):
        if isinstance(r, (Obj, Arr, Str)):
            if r.id in self.emitted:
                r = Ref(r.id)
            else:
                self.emitted.add(r.id)
        if isinstance(r, Obj):
            self.obj(r)
        elif isinstance(r, Str):
            self.u8(6); self.i32(r.id); self.lps(r.value)
        elif isinstance(r, Arr):
            self.arr(r)
        elif isinstance(r, Prim):
            self.u8(8); self.u8(r.ptype); self.prim(r.ptype, r.value)
        elif isinstance(r, Ref):
            self.u8(9); self.i32(r.id)
            if r.id not in self.emitted:
                self.wanted.append(r.id)
        elif r is None:
            self.u8(10)
        else:
            raise TypeError(r)

    def obj(self, o):
        shape = self.shape(o)
        orig = self.p.classinfo.get(o.meta)
        unchanged = orig is not None and shape == (orig[0], orig[4], tuple(orig[1]),
                                                   tuple(orig[2]) if orig[2] else None,
                                                   tuple(orig[3]) if orig[3] else None)
        if unchanged:
            mid = self.meta_done.get(o.meta) if o.rt == 1 else None
            rt = orig[5]
        else:
            mid = self.shape_done.get(shape)
            rt = (5 if o.lib is not None else 4) if o.bt is not None else (3 if o.lib is not None else 2)
        if mid is not None:
            self.u8(1); self.i32(o.id); self.i32(mid)
        else:
            for t, x in zip(o.bt or (), o.extra or ()):
                if t == 4:
                    self.lib(x[1])
            self.lib(o.lib)
            self.u8(rt); self.i32(o.id); self.lps(o.cls); self.i32(len(o.names))
            for n in o.names:
                self.lps(n)
            if rt in (4, 5):
                self.typeinfo(o.bt, o.extra)
            if rt in (3, 5):
                self.i32(o.lib)
            if unchanged:
                self.meta_done.setdefault(o.meta, o.id)
            self.shape_done.setdefault(shape, o.id)
        self.members(o.values, o.bt, o.extra)

    def typeinfo(self, bt, extra):
        for t in bt:
            self.u8(t)
        for t, x in zip(bt, extra):
            if t in (0, 7):
                self.u8(x)
            elif t == 3:
                self.lps(x)
            elif t == 4:
                self.lps(x[0]); self.i32(x[1])

    def members(self, values, bt, extra, array=False):
        # .NET only collapses null runs inside arrays; class members get one ObjectNull each
        i, n = 0, len(values)
        while i < n:
            v = values[i]
            if bt is not None and bt[i] == 0:
                self.prim(extra[i], v.value); i += 1
                continue
            if v is None and not array:
                self.u8(10); i += 1
                continue
            if v is None:
                j = i
                while j < n and values[j] is None and not (bt is not None and bt[j] == 0):
                    j += 1
                run = j - i
                if run == 1:
                    self.u8(10)
                elif run < 256:
                    self.u8(13); self.u8(run)
                else:
                    self.u8(14); self.i32(run)
                i = j
                continue
            self.record(v); i += 1

    def arr(self, a):
        if a.rt == 15:
            self.u8(15); self.i32(a.id)
            t = a.etype[1]
            if t == 2:
                self.i32(len(a.items.value)); self.u8(2); self.out += a.items.value
            else:
                self.i32(len(a.items)); self.u8(t)
                for x in a.items:
                    self.prim(t, x.value)
        elif a.rt in (16, 17):
            self.u8(a.rt); self.i32(a.id); self.i32(len(a.items))
            self.members(a.items, None, None, True)
        else:
            bt, extra = a.etype
            if bt == 4:
                self.lib(extra[1])
            self.u8(7); self.i32(a.id); self.u8(a.atype); self.i32(len(a.lens))
            for l in a.lens:
                self.i32(l)
            if a.lbounds is not None:
                for l in a.lbounds:
                    self.i32(l)
            self.typeinfo([bt], [extra])
            n = len(a.items)
            self.members(a.items, [bt] * n, [extra] * n, True)


def children(o):
    if isinstance(o, Obj):
        vals = o.values
    elif isinstance(o, Arr) and isinstance(o.items, list):
        vals = o.items
    else:
        return
    for v in vals:
        if isinstance(v, (Ref, Obj, Arr, Str)):
            yield v.id


def reachable(p):
    seen = {p.root}
    stack = [p.root]
    while stack:
        for k in children(p.objects[stack.pop()]):
            if k not in seen:
                seen.add(k); stack.append(k)
    return seen


def serialize(parser):
    return Writer(parser).write()
