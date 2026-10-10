"""Read-only lookups into the Underrail install: item database, feat/spec names, portraits.
Everything is derived from the user's game files at runtime and cached in ~/.cache."""
import json
import os
import re
import zlib

import nrbf

GAME = os.path.expanduser('$UNDERRAIL_GAME_DIR')
USERDIR = os.path.expanduser('$UNDERRAIL_USER_DIR/'
                             'Documents/My Games/Underrail')
CACHE = os.path.expanduser('~/.cache/underrail-save-editor')
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
    stamp = [os.path.getmtime(s) for s in sources if os.path.exists(s)]
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
                'battery': _val(p, o.get('I:MB')) or 0,
            }
    return out


_items = None


def items():
    """lower-case item path (as referenced by saves, without .item) -> info dict"""
    global _items
    if _items is None:
        base = os.path.join(GAME, 'data', 'rules', 'items')
        _items = _cached('items-v3.json', [base, os.path.join(GAME, 'underrail.exe')], _build_items)
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


_names = None


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
    return out


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
    """Writes <pid>_s/_l/_h.png into CustomPortraits (square crop, game sizes)."""
    from PIL import Image
    im = Image.open(image_path).convert('RGBA')
    side = min(im.size)
    left, top = (im.width - side) // 2, (im.height - side) // 2
    im = im.crop((left, top, left + side, top + side))
    d = custom_portrait_dir()
    os.makedirs(d, exist_ok=True)
    for suffix, size in PORTRAIT_SIZES.items():
        im.resize((size, size), Image.LANCZOS).save(os.path.join(d, f'{pid}_{suffix}.png'))

