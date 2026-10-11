"""Read-only lookups into the Underrail install: item database, feat/spec names, portraits.
Everything is derived from the user's game files at runtime and cached in ~/.cache."""
import json
import os
import re
import zlib

import nrbf

import paths

GAME = USERDIR = ICON_DIR = None
CACHE = paths.CACHE_DIR


def configure():
    """(Re)reads the game and user folders (detected or chosen by the user). Returns True if both exist."""
    global GAME, USERDIR, ICON_DIR, _items, _names
    GAME, USERDIR = paths.resolve()
    ICON_DIR = os.path.join(GAME, 'data', 'icons') if GAME else None
    _items = _names = None
    return GAME is not None and USERDIR is not None


HEADER_LEN = 24


def read_nrbf(path):
    raw = open(path, 'rb').read()[HEADER_LEN:]
    if raw[:2] == b'\x1f\x8b':
        raw = zlib.decompressobj(47).decompress(raw)  # some files carry trailing junk after the gzip member
    return nrbf.Parser(raw).parse()


def _val(p, v):
    v = nrbf.resolve(p, v)
    if isinstance(v, (nrbf.Prim, nrbf.Str)):
        return v.value
    if isinstance(v, nrbf.Obj) and v.names == ['value__']:
        return v.values[0].value
    return None


def _cached(name, sources, build):
    """JSON cache invalidated when any source path's mtime changes."""
    # the source paths are part of the stamp, so switching game folders never reuses old data
    stamp = [[s, os.path.getmtime(s)] for s in sources if os.path.exists(s)]
    path = os.path.join(CACHE, name)
    try:
        with open(path) as f:
            c = json.load(f)
        if c['stamp'] == stamp:
            return c['data']
    except (OSError, ValueError, KeyError):
        pass
    data = build()
    os.makedirs(CACHE, exist_ok=True)
    with open(path, 'w') as f:
        json.dump({'stamp': stamp, 'data': data}, f)
    return data


# item data classes whose instances wear down (others always store 0)
DURABLE_CLASSES = {'WI', 'ASI', 'HI', 'BI', 'SEI'}  # belts (BI1) always store 0
# weapon types (WI:WT) with doubled durability: 9 = light machine guns, 10 = miniguns
DOUBLE_DURABILITY_WTYPES = {9, 10}


def max_durability(level, wtype=None):
    """Port of the game's item max-durability formula (constants from its static config class)."""
    v = 120 + 60 * level + 30 * max(0, level - 5) if level > 0 else 200
    return v * 2 if wtype in DOUBLE_DURABILITY_WTYPES else v


QUALITY = {0: 'Junk', 1: 'Common', 2: 'Fine', 3: 'Good', 4: 'Superior', 5: 'Excellent', 6: 'Unique'}


def _build_items():
    base = os.path.join(GAME, 'data', 'rules', 'items')
    out = {}
    for root, _, files in os.walk(base):
        for fn in files:
            if not fn.endswith('.item'):
                continue
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, base)[:-5].replace('/', '\\')
            try:
                p = read_nrbf(full)
            except Exception:
                continue
            o = p.objects[p.root]
            out[rel.lower()] = {
                'path': rel, 'cls': o.cls, 'id': _val(p, o.get('I:C')), 'name': _val(p, o.get('I:N')) or fn[:-5],
                'desc': _val(p, o.get('I:D')) or '', 'quality': _val(p, o.get('I:Q')),
                'stack': _val(p, o.get('I:MS')) or 1, 'value': _val(p, o.get('I:CV')),
                'weight': _val(p, o.get('I:W')), 'category': rel.split('\\')[0].lower(),
                'level': _val(p, o.get('I:L')) or 0, 'wtype': _val(p, o.get('WI:WT')),
                'battery': _val(p, o.get('I:MB')) or 0, 'vm': _val(p, o.get('I:VM')),
            }
    return out


def items():
    """lower-case item path (as referenced by saves, without .item) -> info dict"""
    global _items
    if _items is None:
        base = os.path.join(GAME, 'data', 'rules', 'items')
        _items = _cached('items-v4.json', [base, os.path.join(GAME, 'underrail.exe')], _build_items)
    return _items


def item(path):
    return items().get(path.lower().replace('/', '\\'))


def knowledge(name):
    """key -> text from data/knowledge/<name>.k"""
    p = read_nrbf(os.path.join(GAME, 'data', 'knowledge', name + '.k'))
    r = p.objects[p.root]
    return {_val(p, r.get(f'KI:S:{i}:Key')): _val(p, r.get(f'KI:S:{i}:Value'))
            for i in range(r.get('KI:S:Count').value)}


def _exe_strings():
    data = open(os.path.join(GAME, 'underrail.exe'), 'rb').read()
    ascii_ = [m.decode() for m in re.findall(rb'[\x20-\x7e]{3,}', data)]
    utf16 = [m.decode('utf-16-le') for m in re.findall(rb'(?:[\x20-\x7e]\x00){3,}', data)]
    return ascii_, utf16


def _norm(s):
    return re.sub(r'[^a-z0-9]', '', s.lower())


# feats whose ids are abbreviations, named after their in-game descriptions
_FEAT_ABBR = {'s2': 'Sprint', 'as': 'Aimed Shot', 's': 'Snipe', 'a': 'Assassinate', 'kcs': 'Kneecap Shot',
              'ss': 'Sharpshooter', 'o': 'Opportunist', 'g': 'Gunslinger', 'pe': 'Psi Empathy',
              'ci': 'Cryogenic Induction', 'h': 'Hypothermia', 'i': 'Interloper', 'ct': 'Cerebral Trauma',
              'ms': 'Mental Subversion', 'co': 'Conditioning', 'td': 'Thermodynamicity', 'pm': 'Pyromaniac',
              # matched via the exe's unassigned feat names: Execute fits the pistol attack, and the
              # MarksmanPrecision spec (crossbow precision) belongs to "ds" (see its "-old" description)
              'im': 'Execute', 'ds': 'Marksman'}


def _build_names():
    """CamelCase identifier -> display name pairs from the exe, plus all identifiers."""
    strs, utf16 = _exe_strings()
    pairs = {}
    for a, b in zip(strs, strs[1:]):
        a = a.strip(); b = b.strip()
        if re.fullmatch(r'[A-Za-z0-9]+', a) and a != b and _norm(a) == _norm(b):
            pairs.setdefault(a.lower(), b)
    idents = sorted({s.strip() for s in strs + utf16 if re.fullmatch(r'[A-Z][A-Za-z0-9]{3,60}', s.strip())})
    return {'pairs': pairs, 'idents': idents}


def _name_data():
    global _names
    if _names is None:
        _names = _cached('names-v2.json', [os.path.join(GAME, 'underrail.exe')], _build_names)
    return _names


def split_camel(s):
    return re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', s)


def feats():
    """feat id -> (display name, description), excluding outdated/variant entries"""
    k = knowledge('feats')
    pairs = _name_data()['pairs']
    idents = {s.lower(): s for s in _name_data()['idents']}
    out = {}
    for key, desc in k.items():
        # skip outdated ("-old") and DLC-specific variants of a base description
        if key in ('feats', 'generalinfo') or '-' in key:
            continue
        name = (_FEAT_ABBR.get(key) or pairs.get(key)
                or (split_camel(idents[key]) if key in idents else key.upper() if len(key) <= 3
                    else key.replace('_', ' ').title()))
        out[key] = (name, desc.replace('\r\n', '\n'))
    # the feat classes in the game code are authoritative: they drop outdated description entries
    # and give the official names (descriptions still come from feats.k, also for DLC variants)
    code = feat_requirements()
    if code:
        merged = {}
        for fid, info in code.items():
            desc = out.get(fid, (None, ''))[1] or next(
                (v.replace('\r\n', '\n') for kk, v in k.items() if kk.startswith(fid + '-')), '')
            # per-attribute / per-school variants share one generic description
            for prefix, shared in (('increased', 'increasedbaseability'), ('empoweredinvocation', 'empoweredinvocation')):
                if not desc and fid.startswith(prefix) and shared in k:
                    desc = k[shared].replace('\r\n', '\n')
            merged[fid] = (info.get('name') or out.get(fid, (fid,))[0], desc)
        return merged
    return out


DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
_feat_reqs = None


def feat_requirements():
    """feat id -> {'name', 'requires': [...]}, extracted from underrail.exe by
    tools/extract_feat_requirements.py and shipped as data/feat_requirements.json."""
    global _feat_reqs
    if _feat_reqs is None:
        try:
            with open(os.path.join(DATA_DIR, 'feat_requirements.json')) as f:
                _feat_reqs = json.load(f)['feats']
        except (OSError, ValueError, KeyError):
            _feat_reqs = {}
    return _feat_reqs


def spec_rules():
    """spec key -> {'feat': feat id it belongs to, 'name', 'max': max points or None}."""
    feat_requirements()
    try:
        with open(os.path.join(DATA_DIR, 'feat_requirements.json')) as f:
            return json.load(f).get('specs', {})
    except (OSError, ValueError):
        return {}


def feat_name(fid):
    f = feats().get(fid)
    return f[0] if f else fid


def blueprints():
    """blueprint id (lower-case, as stored in saves) -> (display name, description)"""
    k = knowledge('itemblueprints')
    return {key[:-5]: (name, k.get(key[:-5], '').replace('\r\n', '\n'))
            for key, name in k.items() if key.endswith('_name')}


def sort_key(s):
    """Approximates .NET's culture-aware string order (verified against the saved blueprint lists):
    hyphen/apostrophe ignored, punctuation < digits < letters, case only as a tie-breaker."""
    prim = []
    for c in s:
        if c in "-'":
            continue
        prim.append((3, c.lower()) if c.isalpha() else (2, c) if c.isdigit() else (1, c))
    return prim, [c.isupper() for c in s if c.isalpha()], s


def specs():
    """spec key as stored in saves (CamelCase) -> (display name, description)"""
    k = knowledge('specialization')
    idents = {s.lower(): s for s in _name_data()['idents']}
    out = {}
    for key, desc in k.items():
        if key == 'generalinfo' or '-' in key:
            continue
        camel = idents.get(key)
        if camel:
            out[camel] = (split_camel(camel), desc.replace('\r\n', '\n'))
    return out


def portrait_dirs():
    base = os.path.join(GAME, 'data', 'portraits')
    return [(d, os.path.join(base, d)) for d in ('male', 'female', 'genderless')]


def custom_portrait_dir():
    return os.path.join(USERDIR, 'CustomPortraits')


def portraits():
    """portrait id -> (group, path of the _l image) for built-in and custom portraits"""
    out = {}
    for group, d in portrait_dirs() + [('custom', custom_portrait_dir())]:
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            m = re.fullmatch(r'(.+)_l\.(xnb|png)', fn, re.I)
            if m and m.group(1) not in out:
                out[m.group(1)] = (group, os.path.join(d, fn))
    return out


def portrait_png(pid, path):
    """Path to a cached PNG of the portrait (decoding XNB on first use)."""
    if path.lower().endswith('.png'):
        return path
    out = os.path.join(CACHE, 'portraits', f'{pid}.png')
    if os.path.exists(out) and os.path.getmtime(out) >= os.path.getmtime(path):
        return out
    import xnb
    from PIL import Image
    w, h, px = xnb.read_texture(path)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    Image.frombytes('RGBA', (w, h), px).save(out)
    return out


PORTRAIT_SIZES = {'s': 50, 'l': 100, 'h': 200}


def import_portrait(image_path, pid):
    """Writes <pid>_s/_l/_h.png into CustomPortraits (square crop, game sizes). The game scans that
    folder for *_l.png at startup and uses the lower-cased file name (minus "_l") as portrait id."""
    pid = pid.lower()
    from PIL import Image
    im = Image.open(image_path).convert('RGBA')
    side = min(im.size)
    left, top = (im.width - side) // 2, (im.height - side) // 2
    im = im.crop((left, top, left + side, top + side))
    d = custom_portrait_dir()
    os.makedirs(d, exist_ok=True)
    for suffix, size in PORTRAIT_SIZES.items():
        im.resize((size, size), Image.LANCZOS).save(os.path.join(d, f'{pid}_{suffix}.png'))



# --- item icons ---------------------------------------------------------------------------
# Icons live in sprite sheets (data/icons/*.xnb). icons.iconset maps names to grid cells; item
# visuals not listed there are "<Sheet>.<n>" = cell n of a 10-column grid. Cells are 33 px on a
# 34 px pitch (verified visually against the sheets).
ICON_SIZE, ICON_PITCH, ICON_COLS = 33, 34, 10


def _iconset():
    p = read_nrbf(os.path.join(ICON_DIR, 'icons.iconset'))
    r = p.objects[p.root]
    out = {}
    for i in range(r.get('ISD:I:Count').value):
        d = nrbf.resolve(p, r.get(f'ISD:I:{i}'))
        parts = []
        for k in range(d.get('ID:P:Count').value):
            part = nrbf.resolve(p, d.get(f'ID:P:{k}'))
            pt = nrbf.resolve(p, part.get('IPD:P'))
            parts.append((_val(p, part.get('IPD:TN')), pt.values[0].value, pt.values[1].value,
                          _val(p, part.get('IPD:A'))))
        out[_val(p, d.get('ID:N'))] = parts
    return out


def icon_file(vm):
    return os.path.join(CACHE, 'icons', re.sub(r'[^A-Za-z0-9_.-]', '_', vm) + '.png')


def icon_path(vm):
    """Cached PNG of an item visual, or None (not extracted yet / no icon)."""
    if not vm:
        return None
    f = icon_file(vm)
    return f if os.path.exists(f) else None


def extract_icons(vms=None, progress=None):
    """Cuts the icons of all item visuals (or the given ones) out of the sheets into the cache."""
    import xnb
    from PIL import Image
    if vms is None:
        vms = {i.get('vm') for i in items().values()}
    vms = sorted(v for v in vms if v)
    iconset = _iconset()
    try:
        # crafted weapons' composite visuals, registered by the game at runtime (data/weapon_icons.json)
        with open(os.path.join(DATA_DIR, 'weapon_icons.json')) as f:
            for vm, parts in json.load(f)['icons'].items():
                iconset.setdefault(vm, [tuple(p) for p in parts])
    except (OSError, ValueError, KeyError):
        pass
    try:
        with open(os.path.join(DATA_DIR, 'ammo_icons.json')) as f:
            ammo_cells = json.load(f)['icons']
    except (OSError, ValueError, KeyError):
        ammo_cells = {}
    sheet_names = {f[:-4].lower(): f[:-4] for f in os.listdir(ICON_DIR) if f.endswith('.xnb')}
    sheets = {}

    def tile(tn, x, y):
        key = tn.lower()
        if key not in sheets:
            w, h, px = xnb.read_texture(os.path.join(ICON_DIR, sheet_names[key] + '.xnb'))
            sheets[key] = Image.frombytes('RGBA', (w, h), px)
        x0, y0 = x * ICON_PITCH, y * ICON_PITCH
        return sheets[key].crop((x0, y0, x0 + ICON_SIZE, y0 + ICON_SIZE))

    os.makedirs(os.path.join(CACHE, 'icons'), exist_ok=True)
    for n, vm in enumerate(vms):
        if progress:
            progress(n, len(vms))
        if os.path.exists(icon_file(vm)):
            continue
        try:
            parts = iconset.get(vm)
            if parts:
                img = Image.new('RGBA', (ICON_SIZE, ICON_SIZE))
                # multi-part icons are layers drawn in order, each with its own opacity
                for tn, x, y, a in parts:
                    layer = tile(tn, x, y)
                    if a is not None and a < 1.0:
                        layer.putalpha(layer.getchannel('A').point(lambda v, a=a: int(v * a)))
                    img.alpha_composite(layer)
            elif vm in ammo_cells:
                # bullets: registered by the game at runtime, see data/ammo_icons.json
                sheet, x, y = ammo_cells[vm]
                img = tile(sheet, x, y)
            else:
                m = re.fullmatch(r'(\w+)\.(\d+)', vm)
                if not m or m.group(1).lower() not in sheet_names:
                    continue
                k = int(m.group(2))
                img = tile(m.group(1), k % ICON_COLS, k // ICON_COLS)
            img.save(icon_file(vm))
        except Exception:
            continue
    if progress:
        progress(len(vms), len(vms))


def placeholder_icon(category, cls=None, wtype=None):
    """Faded icon of a typical item of the same category – narrowed to the same item class (helmet,
    suit, boots…) and weapon type where possible – for items whose own visual has no icon.
    Returns a cached PNG path or None."""
    key = '_'.join(str(k) for k in (category, cls, wtype) if k is not None)
    out = os.path.join(CACHE, 'icons', f'placeholder_{re.sub(r"[^A-Za-z0-9_]", "_", key)}.png')
    if os.path.exists(out):
        return out
    pool = [i for i in items().values() if i['category'] == category and icon_path(i.get('vm'))]
    if cls is not None:
        pool = [i for i in pool if i['cls'] == cls] or pool
    src = None
    if wtype is not None:
        same = [i for i in pool if i.get('wtype') == wtype]
        if not same:
            # weapon type without a library weapon (e.g. heavy energy weapons): generic weapon icon
            extract_icons({'Overview.Weapon'})
            src = icon_path('Overview.Weapon')
        pool = same or pool
    if src is None:
        if not pool:
            return None
        # lowest-level, then alphabetical: tends to be the plain base version of the item type
        src = icon_path(min(pool, key=lambda i: (i.get('level') or 0, i['name']))['vm'])
    from PIL import Image
    img = Image.open(src).convert('RGBA')
    img.putalpha(img.getchannel('A').point(lambda v: int(v * 0.45)))
    img.save(out)
    return out


_items = _names = None
configure()
