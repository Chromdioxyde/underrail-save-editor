"""Underrail save model on top of the NRBF graph: character values, feats, specializations,
inventory and info.dat sync. All writes re-serialize the graph (see nrbf.Writer)."""
import gzip
import os
import random
import re
import shutil
import time
import zlib

import gamedata
import nrbf

import paths


def saves_dir():
    return os.path.join(gamedata.USERDIR, 'Saves') if gamedata.USERDIR else None



# backups live in the user's data dir, independent of where the program is installed
BACKUPS = paths.BACKUP_DIR
HEADER_LEN = 24  # GUID + version bytes, kept verbatim

# skill objects carry no name; the save keeps them in the in-game order
SKILL_NAMES = ['Guns', 'Heavy Guns', 'Throwing', 'Crossbows', 'Melee', 'Dodge', 'Evasion', 'Stealth',
               'Hacking', 'Lockpicking', 'Pickpocketing', 'Traps', 'Mechanics', 'Electronics',
               'Chemistry', 'Biology', 'Tailoring', 'Thought Control', 'Psychokinesis', 'Metathermics',
               'Temporal Manipulation', 'Persuasion', 'Intimidation', 'Mercantile']

POINT_FIELDS = [('PC1:E', 'Experience'), ('PC1:BAPC', 'Unspent attribute points'),
                ('PC1:SPC', 'Unspent skill points'), ('PC1:FC', 'Unspent feat points'),
                ('PC1:SP', 'Unspent specialization points')]

# item template class (.item root) -> item instance class, as observed in saves
INSTANCE_CLASS = {'ABCI': 'CII', 'AI2': 'AI3', 'ASI': 'ASII', 'BI': 'BII', 'BI1': 'BII1', 'BSI': 'NEII',
                  'C00': 'NEII', 'CI': 'CII', 'CI2': 'NEII', 'ESI2': 'NEII', 'EXI': 'NEII', 'FI': 'NEII',
                  'GBIX': 'NEII', 'GI': 'QSII', 'HI': 'HII', 'JSI': 'VPII', 'KI2': 'NEII', 'MI': 'NEII',
                  'NEI': 'NEII', 'OD': 'NEII', 'PMI': 'NEII', 'QSI': 'QSII', 'SBCI': 'CII', 'SEI': 'SEII',
                  'T5': 'NEII', 'TI': 'NEII', 'VAI': 'VPII', 'VBI': 'VPII', 'VEI': 'VPII', 'VFI': 'VPII',
                  'WI': 'WII'}

# item data classes the player can craft (weapons, armor pieces, shield emitters)
CRAFTABLE_CLASSES = {'WI', 'ASI', 'HI', 'BI', 'BI1', 'SEI'}

EQUIP_SLOTS = [('CGS:H', 'Head'), ('CGS:A', 'Armor'), ('CGS:B', 'Belt'), ('CGS:B1', 'Boots'),
               ('CGS:SE', 'Shield emitter')]


class Field:
    """An editable number. `same` prims get the same value, `extra` prims are shifted by the delta."""

    def __init__(self, name, prim, extra=(), same=(), info=None):
        self.name, self.prim, self.extra, self.same, self.info = name, prim, list(extra), list(same), info
        self.original = prim.value

    @property
    def value(self):
        return self.prim.value

    @property
    def is_float(self):
        return self.prim.ptype in (6, 11)


class File:
    """One NRBF file of a save (global.dat or info.dat)."""

    def __init__(self, path):
        self.path = path
        raw = open(path, 'rb').read()
        self.header = raw[:HEADER_LEN]
        body = raw[HEADER_LEN:]
        self.compressed = body[:2] == b'\x1f\x8b'
        if self.compressed:
            body = zlib.decompressobj(47).decompress(body)
        self.p = nrbf.Parser(body).parse()
        # .NET hands out object ids (negative for value types) and library ids from ONE counter, so
        # every absolute value is unique; Mono relies on that ("An object cannot be registered twice")
        used = [abs(i) for i in self.p.objects] + list(self.p.libs)
        self._next_id = max(used + [0]) + 1
        self.dirty = False
        self.repaired = self.repair_ids()

    def repair_ids(self):
        """Renumbers objects whose id clashes by absolute value with another object or library (written
        by editor versions before the fix). Returns how many were renumbered."""
        seen = {abs(i): ('lib', i) for i in self.p.libs}
        clashes = []
        for i in sorted(self.p.objects, key=abs):
            if abs(i) in seen:
                clashes.append(i)
            else:
                seen[abs(i)] = ('obj', i)
        for old in clashes:
            self.renumber(old, self.new_id(old < 0))
        if clashes:
            self.dirty = True
        return len(clashes)

    def renumber(self, old, new):
        objs = self.p.objects
        o = objs.pop(old)
        o.id = new
        objs[new] = o
        if self.p.root == old:
            self.p.root = new
        for x in objs.values():
            vals = x.values if isinstance(x, nrbf.Obj) else (x.items if isinstance(x, nrbf.Arr) and isinstance(x.items, list) else [])
            for k, v in enumerate(vals):
                if isinstance(v, nrbf.Ref) and v.id == old:
                    vals[k] = nrbf.Ref(new)

    def new_id(self, negative=False):
        i = self._next_id
        self._next_id += 1
        return -i if negative else i

    def obj(self, v):
        return nrbf.resolve(self.p, v)

    def val(self, v):
        v = self.obj(v)
        if isinstance(v, (nrbf.Prim, nrbf.Str)):
            return v.value
        if isinstance(v, nrbf.Obj) and v.names == ['value__']:
            return v.values[0].value
        return None

    def new_str(self, s):
        o = nrbf.Str(self.new_id(), s)
        self.p.objects[o.id] = o
        return o

    def set_str(self, o, member, s):
        """Strings may be shared between objects, so never mutate them; swap in a new one."""
        o.values[o.names.index(member)] = self.new_str(s)
        self.dirty = True

    def serialize(self):
        body = nrbf.serialize(self.p)
        nrbf.check(body)  # refuse to write anything the game couldn't load
        if self.compressed:
            body = gzip.compress(body, mtime=0)
        return self.header + body


def seq_get(o, prefix, parts=('',)):
    """Entries of an ISerializable-flattened list/dict, e.g. 'F:F:Count', 'F:F:0', ..."""
    n = o.get(f'{prefix}:Count').value
    return [tuple(o.get(f'{prefix}:{i}{part}') for part in parts) if len(parts) > 1 else o.get(f'{prefix}:{i}')
            for i in range(n)]


def seq_set(o, prefix, entries, parts=('',), types=None):
    """Rewrites the flattened list members. Member types are taken from existing entries,
    then `types` (part -> (binarytype, extra)), falling back to Object."""
    pat = re.compile(re.escape(prefix) + r':\d+(' + '|'.join(re.escape(p) for p in parts) + r')$')
    typed = o.bt is not None
    tmpl = dict(types or {})
    names, values, bt, extra = [], [], [], []
    for i, n in enumerate(o.names):
        m = pat.match(n)
        if m:
            if typed:
                tmpl[m.group(1)] = (o.bt[i], o.extra[i])
            continue
        names.append(n); values.append(o.values[i])
        if typed:
            bt.append(o.bt[i]); extra.append(o.extra[i])
    ci = names.index(f'{prefix}:Count')
    if isinstance(values[ci], nrbf.Prim):
        values[ci] = nrbf.Prim(values[ci].ptype, None, len(entries))
    else:
        values[ci] = nrbf.Prim(8, None, len(entries))
    new_n, new_v, new_bt, new_ex = [], [], [], []
    for idx, e in enumerate(entries):
        e = e if len(parts) > 1 else (e,)
        for part, v in zip(parts, e):
            new_n.append(f'{prefix}:{idx}{part}'); new_v.append(v)
            t = tmpl.get(part, (2, None))
            if t[0] == 0 and not isinstance(v, nrbf.Prim):
                t = (2, None)
            new_bt.append(t[0]); new_ex.append(t[1])
    o.names = names[:ci + 1] + new_n + names[ci + 1:]
    o.values = values[:ci + 1] + new_v + values[ci + 1:]
    if typed:
        o.bt = bt[:ci + 1] + new_bt + bt[ci + 1:]
        o.extra = extra[:ci + 1] + new_ex + extra[ci + 1:]


class Item:
    def __init__(self, save, obj, slot=None):
        self.save, self.obj, self.slot = save, obj, slot
        f = save.g
        self.dp = f.obj(obj.get('II:DP'))
        self.path = f.val(self.dp.get('LIDP:P')) if self.dp is not None and 'LIDP:P' in self.dp else None
        self.data = f.obj(self.dp.get('IIDP:D')) if self.dp is not None and 'IIDP:D' in self.dp else None
        self.info = gamedata.item(self.path) if self.path else None

    @property
    def crafted(self):
        """Crafted gear: embedded item data without a template id. Unique plot items (keys, data
        chips…) also carry embedded data, but keep their template id or aren't equipment."""
        if self.data is None or self.data.cls not in CRAFTABLE_CLASSES:
            return False
        return not self.save.g.val(self.data.get('I:C'))

    @property
    def name(self):
        if self.data is not None:
            return self.save.g.val(self.data.get('I:N')) or '?'
        if self.info:
            return self.info['name']
        return self.path or '?'

    @property
    def category(self):
        if self.info:
            return self.info['category']
        if self.data is not None:
            return {'WI': 'weapons', 'HI': 'armor', 'ASI': 'armor', 'BI': 'armor', 'BI1': 'armor',
                    'SEI': 'devices', 'TI': 'devices', 'KI2': 'plot', 'NEI': 'misc', 'QSI': 'ammo',
                    'CI': 'components'}.get(self.data.cls, self.data.cls)
        return ''

    def field(self, member, label):
        v = self.obj.get(member)
        return Field(label, v) if isinstance(v, nrbf.Prim) else None

    def fields(self):
        out = [self.field('II:S', 'Stack'), self.field('II:D', 'Durability'), self.field('II:B', 'Battery')]
        if 'CII:QL' in self.obj:
            out.append(self.field('CII:QL', 'Quality'))
        return [f for f in out if f]

    @property
    def visual(self):
        """Visual/icon id (I:VM) of the item."""
        if self.data is not None:
            return self.save.g.val(self.data.get('I:VM'))
        return self.info.get('vm') if self.info else None

    @property
    def weapon_type(self):
        if self.data is not None:
            return self.save.g.val(self.data.get('WI:WT')) if 'WI:WT' in self.data else None
        return self.info.get('wtype') if self.info else None

    def icon(self):
        """(png path, is_placeholder) — own icon, else a category placeholder, else (None, False)."""
        own = gamedata.icon_path(self.visual)
        if own:
            return own, False
        cls = self.data.cls if self.data is not None else (self.info['cls'] if self.info else None)
        ph = gamedata.placeholder_icon(self.category, cls, self.weapon_type)
        return ph, ph is not None

    @property
    def max_battery(self):
        """Battery capacity (I:MB), or None for items without a battery."""
        if self.data is not None:
            mb = self.save.g.val(self.data.get('I:MB')) if 'I:MB' in self.data else None
        else:
            mb = self.info.get('battery') if self.info else None
        return mb or None

    @property
    def max_durability(self):
        """Full durability as the game computes it, or None for items that don't wear down."""
        f = self.save.g
        if self.data is not None:
            if self.data.cls not in gamedata.DURABLE_CLASSES:
                return None
            wt = f.val(self.data.get('WI:WT')) if 'WI:WT' in self.data else None
            return gamedata.max_durability(f.val(self.data.get('I:L')) or 0, wt)
        if self.info and self.info['cls'] in gamedata.DURABLE_CLASSES:
            return gamedata.max_durability(self.info.get('level', 0), self.info.get('wtype'))
        return None


class Save:
    def __init__(self, folder):
        self.folder = folder
        self.path = os.path.join(folder, 'global.dat')
        self.g = File(self.path)
        info = os.path.join(folder, 'info.dat')
        self.info = File(info) if os.path.exists(info) else None
        root = self.g.p.objects[self.g.p.root]
        self.root = root
        self.pc = self.g.obj(root.get('TG:PC'))
        self.m = dict(zip(self.pc.names, self.pc.values))

    # --- basics -------------------------------------------------------------------------
    def obj(self, v):
        return self.g.obj(v)

    def members(self, o):
        return dict(zip(o.names, o.values))

    def val(self, v):
        return self.g.val(v)

    def _info_root(self):
        return self.info.p.objects[self.info.p.root] if self.info else None

    @property
    def name(self):
        return self.val(self.pc.get('C1:N'))

    def set_name(self, name):
        self.g.set_str(self.pc, 'C1:N', name)
        r = self._info_root()
        if r is not None and 'SGI:CN' in r:
            self.info.set_str(r, 'SGI:CN', name)

    @property
    def level(self):
        return self.val(self.pc.get('C1:L'))

    def level_field(self):
        r = self._info_root()
        same = [r.get('SGI:CL')] if r is not None and isinstance(r.get('SGI:CL'), nrbf.Prim) else []
        return Field('Level', self.pc.get('C1:L'), same=same)

    @property
    def portrait(self):
        return self.val(self.pc.get('C1:P2'))

    def set_portrait(self, pid):
        self.g.set_str(self.pc, 'C1:P2', pid)

    def location(self):
        r = self._info_root()
        return self.info.val(r.get('SGI:L')) if r is not None else None

    def points(self):
        return [Field(label, self.m[k]) for k, label in POINT_FIELDS if k in self.m]

    def vitals(self):
        out = []
        hp = self.obj(self.obj(self.m['C1:D2']).get('CD1:H'))
        if hp is not None:
            out.append(Field('Health (current)', hp.get('BV:V')))
        return out

    def attributes(self):
        ba = self.obj(self.m['C1:BA'])
        out = []
        for v in seq_get(ba, 'BA3:BA'):
            a = self.obj(v)
            out.append(Field(self.val(a.get('BA2:N')), a.get('S4:V'), [a.get('S4:MV')]))
        return out

    def skills(self):
        sk = self.obj(self.m['C1:S'])
        out = []
        for i, v in enumerate(seq_get(sk, 'S3:S')):
            s = self.obj(v)
            name = SKILL_NAMES[i] if i < len(SKILL_NAMES) else f'Skill {i}'
            out.append(Field(name, s.get('S4:V'), [s.get('S4:MV')]))
        return out

    def oddities(self):
        return [Field(self.val(k), v) for k, v in seq_get(self.pc, 'PC1:O', (':Key', ':Value'))
                if isinstance(v, nrbf.Prim)]

    # --- specializations ------------------------------------------------------------------
    def specs(self):
        out = []
        for k, v in seq_get(self.pc, 'C1:SPC', (':Key', ':Value')):
            snf = self.obj(v)
            # V and M were always equal in observed saves; keep them in sync (verified in-game)
            out.append(Field(self.val(k), snf.get('SNF:V'), same=[snf.get('SNF:M')]))
        return sorted(out, key=lambda f: f.name.lower())

    def add_spec(self, key, value=0):
        entries = seq_get(self.pc, 'C1:SPC', (':Key', ':Value'))
        if any(self.val(k) == key for k, _ in entries):
            raise ValueError(f'{key} already present')
        if not entries:
            raise ValueError('no existing specialization to copy the structure from')
        tmpl = self.obj(entries[0][1])
        snf = self.shallow_copy(tmpl)
        for m in ('SNF:V', 'SNF:M'):
            snf.values[snf.names.index(m)] = nrbf.Prim(8, None, int(value))
        entries.append((self.g.new_str(key), snf))
        seq_set(self.pc, 'C1:SPC', entries, (':Key', ':Value'))
        self.g.dirty = True

    def remove_spec(self, key):
        entries = [e for e in seq_get(self.pc, 'C1:SPC', (':Key', ':Value')) if self.val(e[0]) != key]
        seq_set(self.pc, 'C1:SPC', entries, (':Key', ':Value'))
        self.g.dirty = True

    # --- feats ----------------------------------------------------------------------------
    def _feat_owner(self):
        return self.obj(self.m['C1:F'])

    def feats(self):
        return [self.val(self.obj(v).get('FR:FTN')) for v in seq_get(self._feat_owner(), 'F:F')]

    def add_feat(self, fid):
        owner = self._feat_owner()
        entries = seq_get(owner, 'F:F')
        if fid in self.feats():
            raise ValueError(f'{fid} already present')
        tmpl = self.obj(entries[0])
        fr = self.shallow_copy(tmpl)
        fr.values[fr.names.index('FR:FTN')] = self.g.new_str(fid)
        seq_set(owner, 'F:F', entries + [fr])
        self.g.dirty = True

    def remove_feat(self, fid):
        owner = self._feat_owner()
        entries = [v for v in seq_get(owner, 'F:F') if self.val(self.obj(v).get('FR:FTN')) != fid]
        seq_set(owner, 'F:F', entries)
        self.g.dirty = True

    # --- blueprints -----------------------------------------------------------------------
    def _bp_list(self):
        sl = self.obj(self.m['PC1:B'])
        return sl, dict(zip(sl.names, sl.values))

    def blueprints(self):
        """Known blueprint ids, in stored order."""
        sl, m = self._bp_list()
        vals = self.obj(m['values']).items[:m['_size'].value]
        return [self.val(self.obj(v).get('IBR:IBFTN')) for v in vals]

    def _set_blueprints(self, entries):
        """entries: [(name Str/Ref, IBR obj/Ref)]. The SortedList is binary-searched by the game,
        so keys must be in .NET culture order; arrays keep their capacity (grown by doubling)."""
        sl, m = self._bp_list()
        entries = sorted(entries, key=lambda e: gamedata.sort_key(self.val(e[0])))
        keys, vals = self.obj(m['keys']), self.obj(m['values'])
        cap = max(len(keys.items), 4)
        while cap < len(entries):
            cap *= 2
        keys.items = [e[0] for e in entries] + [None] * (cap - len(entries))
        vals.items = [e[1] for e in entries] + [None] * (cap - len(entries))
        if vals.lens is not None:
            vals.lens = [cap]
        sl.values[sl.names.index('_size')] = nrbf.Prim(8, None, len(entries))
        ver = sl.get('version')
        sl.values[sl.names.index('version')] = nrbf.Prim(8, None, ver.value + 1)
        self.g.dirty = True

    def _bp_entries(self):
        sl, m = self._bp_list()
        n = m['_size'].value
        return list(zip(self.obj(m['keys']).items[:n], self.obj(m['values']).items[:n]))

    def add_blueprint(self, bid):
        bid = bid.lower()
        db = gamedata.blueprints()
        if bid not in db:
            raise ValueError(f'unknown blueprint {bid}')
        entries = self._bp_entries()
        if bid in self.blueprints():
            return
        if not entries:
            raise ValueError('no known blueprint in this save to copy the structure from')
        ibr = self.shallow_copy(self.obj(entries[0][1]))
        ibr.values[ibr.names.index('IBR:IBFTN')] = self.g.new_str(bid)
        entries.append((self.g.new_str(db[bid][0]), nrbf.Ref(ibr.id)))
        self._set_blueprints(entries)

    def remove_blueprint(self, bid):
        entries = [e for e in self._bp_entries() if self.val(self.obj(e[1]).get('IBR:IBFTN')) != bid]
        self._set_blueprints(entries)

    # --- object helpers -------------------------------------------------------------------
    def shallow_copy(self, o):
        """New object with the same class/metadata and member values. References are shared,
        except value types (negative ids), which .NET requires to be unique per owner: those are copied."""
        c = nrbf.Obj(self.g.new_id(o.id < 0), o.cls, o.names, o.lib, o.bt, o.extra, 1, o.meta)

        def conv(v):
            if isinstance(v, nrbf.Prim):
                return nrbf.Prim(v.ptype, None, v.value)
            if isinstance(v, (nrbf.Ref, nrbf.Obj, nrbf.Arr, nrbf.Str)):
                if v.id < 0:
                    return nrbf.Ref(self.deep_copy(self.obj(v)).id)
                return nrbf.Ref(v.id)
            return v
        c.values = [conv(v) for v in o.values]
        self.g.p.objects[c.id] = c
        return c

    def _parents(self):
        parents = {}
        for o in self.g.p.objects.values():
            for k in nrbf.children(o):
                parents.setdefault(k, set()).add(o.id)
        return parents

    def deep_copy(self, root):
        """Copies the subgraph owned by `root`. Strings, System.Version and anything also
        referenced from outside the subgraph stay shared."""
        objs = self.g.p.objects
        sub = {root.id}
        stack = [root.id]
        while stack:
            for k in nrbf.children(objs[stack.pop()]):
                if k not in sub:
                    sub.add(k); stack.append(k)
        parents = self._parents()
        own = set()
        for oid in sub:
            o = objs[oid]
            if oid == root.id:
                own.add(oid)
            elif isinstance(o, nrbf.Str) or (isinstance(o, nrbf.Obj) and o.cls == 'System.Version'):
                continue
            elif oid < 0 or parents.get(oid, set()) <= sub:
                # value types are always copied: .NET can't share them between objects
                own.add(oid)
        idmap = {oid: self.g.new_id(oid < 0) for oid in own}

        def conv(v):
            if isinstance(v, nrbf.Prim):
                return nrbf.Prim(v.ptype, None, v.value)
            if isinstance(v, (nrbf.Ref, nrbf.Obj, nrbf.Arr, nrbf.Str)):
                return nrbf.Ref(idmap.get(v.id, v.id))
            return v

        for oid in own:
            o = objs[oid]
            if isinstance(o, nrbf.Obj):
                c = nrbf.Obj(idmap[oid], o.cls, o.names, o.lib, o.bt, o.extra, 1, o.meta)
                c.values = [conv(v) for v in o.values]
            else:
                c = nrbf.Arr(idmap[oid], o.etype, o.rt, o.atype, o.lens, o.lbounds)
                c.items = nrbf.Prim(18, None, o.items.value) if isinstance(o.items, nrbf.Prim) else \
                    [conv(v) for v in o.items]
            objs[c.id] = c
        return objs[idmap[root.id]]

    def _new_guid(self, item):
        g = self.obj(item.get('II:I'))
        if g is None:
            return
        g = self.shallow_copy(g)
        item.values[item.names.index('II:I')] = nrbf.Ref(g.id)
        for i, n in enumerate(g.names):
            v = g.values[i]
            if isinstance(v, nrbf.Prim):
                lo, hi = {8: (-2**31, 2**31 - 1), 7: (-2**15, 2**15 - 1), 2: (0, 255)}.get(v.ptype, (0, 255))
                v.value = random.randint(lo, hi)
        # RFC 4122 version 4 bits (field _c is the 3rd group, _d the 4th)
        names = dict(zip(g.names, g.values))
        if '_c' in names:
            names['_c'].value = (names['_c'].value & 0x0fff) | 0x4000
            if names['_c'].value > 0x7fff:
                names['_c'].value -= 0x10000
        if '_d' in names:
            names['_d'].value = (names['_d'].value & 0x3f) | 0x80

    # --- inventory ------------------------------------------------------------------------
    def _inv(self):
        return self.obj(self.m['C1:B'])

    def inventory(self):
        return [Item(self, self.obj(v)) for v in seq_get(self._inv(), 'IC:I')]

    def equipped(self):
        gear = self.obj(self.m['C1:G'])
        slots = list(EQUIP_SLOTS)
        slots += [(f'CGS:QSI:{i}', f'Quick slot {i + 1}') for i in range(gear.get('CGS:QSI:Length').value)] \
            if 'CGS:QSI:Length' in gear else []
        slots += [(f'CGS:W:{i}:Value', f'Weapon {i + 1}') for i in range(gear.get('CGS:W:Count').value)] \
            if 'CGS:W:Count' in gear else []
        out = []
        for member, label in slots:
            s = self.obj(gear.get(member))
            it = self.obj(s.get('IS:I')) if s is not None else None
            if it is not None:
                out.append(Item(self, it, label))
        return out

    def remove_item(self, item):
        inv = self._inv()
        seq_set(inv, 'IC:I', [v for v in seq_get(inv, 'IC:I') if self.obj(v) is not item.obj])
        self.g.dirty = True

    def duplicate_item(self, item):
        c = self.deep_copy(item.obj)
        self._new_guid(c)
        inv = self._inv()
        seq_set(inv, 'IC:I', seq_get(inv, 'IC:I') + [nrbf.Ref(c.id)])
        self.g.dirty = True
        return Item(self, c)

    @staticmethod
    def default_durability(path):
        """Full durability of a fresh library item, or None if it doesn't wear down."""
        info = gamedata.item(path)
        if not info or info['cls'] not in gamedata.DURABLE_CLASSES:
            return None
        return gamedata.max_durability(info.get('level', 0), info.get('wtype'))

    def _all_items(self):
        return [o for o in self.g.p.objects.values() if isinstance(o, nrbf.Obj) and 'II:DP' in o.names]

    def add_item(self, path, count=1, durability=None, quality=None):
        info = gamedata.item(path)
        if not info:
            raise ValueError(f'unknown item {path}')
        inst_cls = INSTANCE_CLASS.get(info['cls'])
        if not inst_cls:
            raise ValueError(f'unsupported item class {info["cls"]}')
        items = self._all_items()
        lidp = [o for o in items if 'LIDP:P' in (self.obj(o.get('II:DP')) or nrbf.Obj(0, '', [])).names]
        same_path = [o for o in lidp if self.val(self.obj(o.get('II:DP')).get('LIDP:P')).lower() == info['path'].lower()]
        same_cls = [o for o in lidp if o.cls == inst_cls] or [o for o in items if o.cls == inst_cls]
        tmpl = (same_path or same_cls or lidp or items or [None])[0]
        if tmpl is None:
            raise ValueError('no item in this save to copy the structure from')
        it = self.deep_copy(tmpl)
        self._new_guid(it)
        if it.cls != inst_cls:
            # strip subclass members of the template, add the ones the target class needs
            keep = [i for i, n in enumerate(it.names) if n.startswith('II:')]
            it.names = [it.names[i] for i in keep]
            it.values = [it.values[i] for i in keep]
            if it.bt is not None:
                it.bt = [it.bt[i] for i in keep]; it.extra = [it.extra[i] for i in keep]
            it.cls = inst_cls
            add = {'WII': [('WII:A:Count', 8)], 'CII': [('CII:QL', 8)]}.get(inst_cls, [])
            for n, t in add:
                it.names.append(n); it.values.append(nrbf.Prim(t, None, 0))
                if it.bt is not None:
                    it.bt.append(0); it.extra.append(t)
        # fresh library data provider pointing at the item template
        lidp_tmpl = next((self.obj(o.get('II:DP')) for o in lidp), None)
        if lidp_tmpl is None:
            raise ValueError('no library item in this save to copy the structure from')
        dp = self.shallow_copy(lidp_tmpl)
        dp.cls = f'LIDP#G1>{info["cls"]}#-'
        dp.values[dp.names.index('LIDP:P')] = self.g.new_str(info['path'])
        it.values[it.names.index('II:DP')] = nrbf.Ref(dp.id)
        mv = dict(zip(it.names, range(len(it.names))))
        if durability is None:
            durability = self.default_durability(info['path'])
        sets = {'II:S': int(count), 'II:D': float(durability or 0.0), 'II:B': 0.0,
                'II:MB': 0, 'II:DR': 0.0, 'CII:QL': int(quality or 0)}
        for n, v in sets.items():
            if n in mv and isinstance(it.values[mv[n]], nrbf.Prim):
                it.values[mv[n]] = nrbf.Prim(it.values[mv[n]].ptype, None, v)
        cp = self.obj(it.get('II:CP'))
        if cp is not None and 'PC:P:Count' in cp:
            seq_set(cp, 'PC:P', [])
        if 'II:F:Count' in it.names:
            seq_set(it, 'II:F', [])
        if 'WII:A:Count' in it.names:
            seq_set(it, 'WII:A', [])
        inv = self._inv()
        seq_set(inv, 'IC:I', seq_get(inv, 'IC:I') + [nrbf.Ref(it.id)])
        self.g.dirty = True
        return Item(self, it)

    # --- generic field editing ------------------------------------------------------------
    def set(self, field, value):
        value = float(value) if field.is_float else int(value)
        if not field.is_float and not -2**31 <= value < 2**31:
            raise ValueError(f'{value} out of int32 range')
        delta = value - field.prim.value
        field.prim.value = value
        for p in field.same:
            p.value = value
        for p in field.extra:
            p.value = p.value + delta
        self.g.dirty = True
        if self.info and any(p in self._info_prims() for p in field.same):
            self.info.dirty = True

    def _info_prims(self):
        r = self._info_root()
        return [v for v in r.values if isinstance(v, nrbf.Prim)] if r is not None else []

    def write(self):
        # backups live outside the save folder so Steam Cloud doesn't sync them
        bakdir = os.path.join(BACKUPS, os.path.basename(os.path.abspath(self.folder)))
        stamp, n = time.strftime('%Y%m%d-%H%M%S'), 0
        while os.path.exists(bak := os.path.join(bakdir, stamp + (f'-{n}' if n else ''))):
            n += 1
        os.makedirs(bak)
        files = [self.g] + ([self.info] if self.info else [])
        data = [(f, f.serialize()) for f in files]  # serialize everything before touching disk
        for f, _ in data:
            shutil.copy2(f.path, bak)
        for f, blob in data:
            tmp = f.path + '.tmp'
            with open(tmp, 'wb') as out:
                out.write(blob)
            os.replace(tmp, f.path)
        return bak


DIFFICULTIES = ['Easy', 'Normal', 'Hard', 'Dominating', 'Custom']  # TimelapseVertigo.Rules.GameDifficulty
DLC_NAMES = {'xpbl': 'Expedition', 'xphw': 'Heavy Duty'}


def save_info(folder):
    """Cheap summary from info.dat, or None if unreadable."""
    try:
        f = File(os.path.join(folder, 'info.dat'))
        r = f.p.objects[f.p.root]
        diff = f.val(r.get('SGI:D'))
        ticks = f.val(r.get('SGI:P'))  # .NET TimeSpan ticks; equals the world clock TG:WT
        dlcs = [f.val(v) for v in seq_get(r, 'SGI:DL')] if 'SGI:DL:Count' in r else []
        return {'name': f.val(r.get('SGI:CN')), 'level': f.val(r.get('SGI:CL')), 'location': f.val(r.get('SGI:L')),
                'mtime': os.path.getmtime(folder), 'hours': ticks / 1e7 / 3600 if ticks else None,
                'difficulty': DIFFICULTIES[diff] if isinstance(diff, int) and 0 <= diff < len(DIFFICULTIES) else diff,
                'dlcs': [DLC_NAMES.get(d, d) for d in dlcs]}
    except Exception:
        return None


# short labels for the save list; any other item in data/rules/items/currency is shown by its name
CURRENCY_LABELS = {'currency\\stygiancoin': 'Stygian', 'currency\\sgscredits': 'SGS',
                   'currency\\usd': 'USD', 'currency\\zlatortiya': 'Zlatortiya'}
DETAILS_VERSION = 2  # bump when save_details() gains fields, so cached entries are rebuilt


def save_details(folder):
    """Expensive summary from global.dat (HP, XP, money), cached per save folder and mtime."""
    import json
    cache = os.path.join(gamedata.CACHE, 'savedetails.json')
    try:
        with open(cache) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {}
    mtime = os.path.getmtime(os.path.join(folder, 'global.dat'))
    hit = data.get(folder)
    if hit and hit.get('mtime') == mtime and hit.get('v') == DETAILS_VERSION:
        return hit['details']
    s = Save(folder)
    hp = s.obj(s.obj(s.m['C1:D2']).get('CD1:H'))
    money = {}
    for it in s.inventory():
        if it.category == 'currency':
            label = CURRENCY_LABELS.get((it.path or '').lower(), it.name)
            money[label] = money.get(label, 0) + it.fields()[0].value
    # fixed order: main currencies first
    order = list(CURRENCY_LABELS.values())
    money = dict(sorted(money.items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else len(order)))
    details = {'hp': s.val(hp.get('BV:V')) if hp else None, 'hp_max': s.val(hp.get('BV:MX')) if hp else None,
               'xp': s.val(s.m.get('PC1:E')), 'money': money,
               'unspent': {k: s.val(s.m.get(k)) for k, _ in POINT_FIELDS[1:] if k in s.m}}
    data[folder] = {'mtime': mtime, 'v': DETAILS_VERSION, 'details': details}
    os.makedirs(gamedata.CACHE, exist_ok=True)
    with open(cache, 'w') as fh:
        json.dump(data, fh)
    return details


def list_saves():
    out = []
    saves = saves_dir()
    if not saves or not os.path.isdir(saves):
        return []
    for d in os.listdir(saves):
        f = os.path.join(saves, d)
        if os.path.isfile(os.path.join(f, 'global.dat')):
            out.append((d, f, save_info(f)))
    return sorted(out, key=lambda x: -os.path.getmtime(x[1]))


game_running = paths.game_running
