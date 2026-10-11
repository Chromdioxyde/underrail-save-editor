"""The game's world map (data/maps/world/globalmap.uz), rendered like the in-game map.

The global map is a zone file whose entities are markers: ZMEA = a zone (ZMEA:R = zone ids, ZMEA:CN = title,
position = the entity's location in zone-sized grid units, X east, Y south), TRSMA = a transition between
zones (TRSMA:L1 / TRSMA:L2 zone id lists). Every marker entity also has a sprite aspect (SEA: SEA:M =
materialization under data/meta/materialization/locale, SEA:F = frame); the .mu file names the texture
(MU:T), frame size (MU:S), sheet offset (MU:UO) and draw origin (MU:TO). Positions are projected
isometrically: screen x = (X - Y) * 50, y = (X + Y) * 25 - Z * 30. ZMEA:I = 1 marks an inset (South Gate Station's levels drawn as a
stack beside the map); ZMEA:C lists the zones a marker stands for, so inset zones are shown at that marker.
"""
import os
import re

import gamedata
import nrbf

CACHE = 'worldmap_v6.json'
RENDER_VERSION = 4  # bump when the drawing changes
# Expedition's Black Sea zones share the coordinate space with the caves, so they get their own page
SEA_PREFIXES = ('xpbl', 'cvw')
# the global map holds separate maps ("areas", Z:A), each with its own coordinates and entity list (A6:E)
AREA_NAMES = {'up': 'Upper Underrail', 'lu': 'Lower Underrail', 'lux': 'Upper Caves', 'lc': 'Lower Caves',
              'dc': 'Deep Caverns', 'lup': 'Lower Passages', 'fo': 'Foundry', 'sgs': 'South Gate Station',
              'bs': 'Black Sea'}
PAGES = tuple(AREA_NAMES)


def _path():
    return os.path.join(gamedata.GAME, 'data', 'maps', 'world', 'globalmap.uz')


def _build():
    p = gamedata.read_nrbf(_path())
    parent = {}
    for x in p.objects.values():
        for k in nrbf.children(x):
            parent.setdefault(k, x.id)

    def entity(aspect):
        le = p.objects.get(parent.get(aspect.id))
        while le is not None and getattr(le, 'cls', '') != 'LE2':
            le = p.objects.get(parent.get(le.id))
        return le

    def pos(aspect):
        loc = nrbf.resolve(p, entity(aspect).get('E4:L1'))
        return [gamedata._val(p, loc.get(a)) for a in ('X', 'Y', 'Z')]

    def ids(o, prefix):
        n = o.get(f'{prefix}:Count').value if f'{prefix}:Count' in o.names else 0
        return [s.lower() for s in (gamedata._val(p, o.get(f'{prefix}:{k}')) for k in range(n)) if s]

    root = p.objects[p.root]
    area_of = {}
    for i in range(root.get('Z:A:Count').value):
        a = nrbf.resolve(p, root.get(f'Z:A:{i}'))
        lst = nrbf.resolve(p, a.get('A6:E'))
        arr = nrbf.resolve(p, lst.get('_items'))
        for v in arr.items[:gamedata._val(p, lst.get('_size'))]:
            o = nrbf.resolve(p, v)
            if o is not None:
                area_of[o.id] = gamedata._val(p, a.get('E2:N'))
    zones, links, sprites = [], set(), []
    sprite_of = {}  # entity id -> sprite index
    for x in p.objects.values():
        if not isinstance(x, nrbf.Obj):
            continue
        if x.cls == 'SEA':
            m = gamedata._val(p, x.get('SEA:M'))
            f = nrbf.resolve(p, x.get('SEA:F'))
            if m and 'FloorGrid' not in m:  # editor grid, not drawn in game
                le = entity(x)
                sprite_of[le.id] = len(sprites)
                sprites.append({'m': m, 'f': [gamedata._val(p, f.get('X')), gamedata._val(p, f.get('Y'))],
                                'pos': pos(x), 'vp': gamedata._val(p, le.get('E4:VP')) or 0,
                                'area': area_of.get(le.id)})
            continue
        if x.cls == 'ZMEA':
            zids = ids(x, 'ZMEA:R')
            if zids and zids != ['unknown']:
                X, Y, Z = pos(x)
                zones.append({'ids': zids, 'x': X, 'y': Y, 'z': Z, 'title': gamedata._val(p, x.get('ZMEA:CN')),
                              'contains': ids(x, 'ZMEA:C'), 'inset': gamedata._val(p, x.get('ZMEA:I')) == 1,
                              'page': area_of.get(entity(x).id),
                              'entity': entity(x).id})
        elif x.cls == 'TRSMA':
            for a in ids(x, 'TRSMA:L1'):
                for b in ids(x, 'TRSMA:L2'):
                    if a != b:
                        links.add(tuple(sorted((a, b))))
    for z in zones:
        z['sprite'] = sprite_of.get(z.pop('entity'))
    return {'zones': zones, 'links': sorted(links), 'sprites': sprites}


_world = None


def world():
    """{'zones': [{'ids', 'x', 'y', 'z', 'title', 'contains', 'inset', 'page'}], 'links': [(zone id, zone id)],
    'marker': zone id -> zone index}"""
    global _world
    if _world is None:
        _world = gamedata._cached(CACHE, [_path()], _build)
        # each zone id -> index of its marker: own marker first, then a marker that contains it, then an inset
        own, inner, inset = {}, {}, {}
        for n, z in enumerate(_world['zones']):
            for zid in z['ids']:
                (inset if z['inset'] else own).setdefault(zid, n)
            for zid in z['contains']:
                inner.setdefault(zid, n)
        _world['marker'] = {**inset, **inner, **own}
    return _world


def marker(zid):
    """Index of the map marker that shows a zone, or None. Zones without their own marker (sub-levels like
    'lux-c6x') fall back to the zone they belong to."""
    m = world()['marker']
    zid = zid.lower()
    while zid:
        if zid in m:
            return m[zid]
        shorter = re.sub(r'([_-]?[a-z]+|[_-])$', '', zid)
        if shorter == zid:
            return None
        zid = shorter
    return None


# isometric projection of the in-game map (pixels per zone)
TILE_W, TILE_H, LEVEL_H = 100, 50, 30
MARGIN = 120


def project(x, y, z):
    return (x - y) * TILE_W / 2, (x + y) * TILE_H / 2 - z * LEVEL_H


def _materialization(m):
    p = gamedata.read_nrbf(os.path.join(gamedata.GAME, 'data', 'meta', 'materialization', 'locale',
                                        m.replace('\\', '/').lower() + '.mu'))
    o = p.objects[p.root]

    def pt(k):
        v = nrbf.resolve(p, o.get(k))
        return [gamedata._val(p, v.get(a)) for a in v.names]
    return {'t': gamedata._val(p, o.get('MU:T')), 's': pt('MU:S'), 'uo': pt('MU:UO'), 'to': pt('MU:TO')}


def _sprite_zones():
    """Zone index every sprite belongs to: the zone it marks, else the nearest zone marker (or None)."""
    zones = world()['zones']
    own = {z['sprite']: n for n, z in enumerate(zones) if z.get('sprite') is not None}
    grid = {}
    for n, z in enumerate(zones):
        grid.setdefault((round(z['x']), round(z['y'])), []).append(n)
    out = []
    for i, s in enumerate(world()['sprites']):
        if i in own:
            out.append(own[i])
            continue
        x, y, _ = s['pos']
        best, dist = None, 1e9
        for dx in range(-3, 4):
            for dy in range(-3, 4):
                for n in grid.get((round(x) + dx, round(y) + dy), ()):
                    d = (zones[n]['x'] - x) ** 2 + (zones[n]['y'] - y) ** 2
                    if d < dist:
                        best, dist = n, d
        out.append(best)
    return out


def _sprites_of(page, area=None):
    """Sprites drawn on a page, optionally only those of one area (layer) of the world."""
    zones = world()['zones']
    out = []
    for s, n in zip(world()['sprites'], _sprite_zones()):
        if s.get('area') == page:
            out.append(s)
    return out


_mats, _textures = {}, {}


def sprite_image(s):
    """(PIL RGBA image, (x, y) of its top-left corner in projected coordinates) of a sprite, or None."""
    from PIL import Image
    import xnb
    m = s['m']
    if m not in _mats:
        try:
            _mats[m] = _materialization(m)
        except Exception:
            _mats[m] = None
    d = _mats[m]
    if d is None:
        return None
    if d['t'] not in _textures:
        # decoding the DXT textures in Python takes seconds, so they're kept as PNG in the cache
        src = os.path.join(gamedata.GAME, 'data', d['t'].replace('\\', '/').lower() + '.xnb')
        png = os.path.join(gamedata.CACHE, 'maptex', f"{os.path.basename(src)[:-4]}-{int(os.path.getmtime(src))}.png")
        if os.path.exists(png):
            _textures[d['t']] = Image.open(png).convert('RGBA')
        else:
            w, h, pix = xnb.read_texture(src)
            _textures[d['t']] = Image.frombytes('RGBA', (w, h), bytes(pix))
            os.makedirs(os.path.dirname(png), exist_ok=True)
            _textures[d['t']].save(png)
    (sx, sy), (ux, uy), (tx, ty) = d['s'], d['uo'], d['to']
    fx, fy = s['f']
    a, b = project(*s['pos'])
    return (_textures[d['t']].crop((ux + fx * sx, uy + fy * sy, ux + (fx + 1) * sx, uy + (fy + 1) * sy)),
            (a - tx, b - ty))


def _render(page, path, area=None):
    from PIL import Image
    sprites = _sprites_of(page, area)
    pts = [project(*s['pos']) for s in sprites]
    left = min(a for a, b in pts) - MARGIN - 200
    top = min(b for a, b in pts) - MARGIN - 200
    width = max(a for a, b in pts) + MARGIN + 200 - left
    height = max(b for a, b in pts) + MARGIN + 200 - top
    img = Image.new('RGBA', (int(width), int(height)), (12, 12, 16, 255))
    # connection lines first (they lie under the zones), then back to front, lower levels first, then by the
    # entity's draw priority (E4:VP)
    def order(s):
        line = 'TransitionConnection' in s['m']
        return (not line, s['pos'][0] + s['pos'][1], s['pos'][2], s.get('vp', 0))
    for s in sorted(sprites, key=order):
        r = sprite_image(s)
        if r:
            img.alpha_composite(r[0], (int(r[1][0] - left), int(r[1][1] - top)))
    # crop to the drawn content
    box = img.getchannel('R').point(lambda v: 255 if v > 14 else 0).getbbox() or (0, 0, *img.size)
    box = (max(0, box[0] - MARGIN), max(0, box[1] - MARGIN), min(img.width, box[2] + MARGIN),
           min(img.height, box[3] + MARGIN))
    img.crop(box).convert('RGB').save(path)
    return [int(left) + box[0], int(top) + box[1]]


def page_image(page, area=None):
    """(png path, (left, top)) of a rendered map page, or of one area (layer) of it; scene position of a
    zone = project() - (left, top)."""
    import json
    import re as _re
    suffix = '' if area is None else '_' + _re.sub(r'\W+', '', area.lower())
    path = os.path.join(gamedata.CACHE, f'worldmap_{page}{suffix}.png')
    meta = path[:-4] + '.json'
    stamp = [_path(), os.path.getmtime(_path()), RENDER_VERSION]
    try:
        with open(meta) as f:
            m = json.load(f)
        if m['stamp'] == stamp and os.path.exists(path):
            return path, m['origin']
    except (OSError, ValueError, KeyError):
        pass
    os.makedirs(gamedata.CACHE, exist_ok=True)
    origin = _render(page, path, area)
    with open(meta, 'w') as f:
        json.dump({'stamp': stamp, 'origin': origin}, f)
    return path, origin


def zone_sprite(n, origin):
    """(PIL RGBA image, (x, y) on the page image) of zone marker n's own sprite, or None."""
    z = world()['zones'][n]
    if z.get('sprite') is None:
        return None
    r = sprite_image(world()['sprites'][z['sprite']])
    if r is None:
        return None
    return r[0], (int(r[1][0]) - origin[0], int(r[1][1]) - origin[1])


def pages_ready():
    return all(os.path.exists(os.path.join(gamedata.CACHE, f'worldmap_{p}.png')) for p in PAGES)


# broad areas of the world by zone id prefix (first match wins), to tell the map's layers apart
REGIONS = [
    (('stationalpha', 'forlorn', 'crossroadcaves', 'lu-southgatestation'), 'South Gate Station'),
    (('up-cc', 'cc'), 'Core City'),
    (('fom', 'crys'), 'Foundry Mine'),
    (('fo',), 'Foundry'),
    (('jyt',), 'Caves'),
    (('ojy', 'jy'), 'Junkyard'),
    (('rc',), 'Rail Crossing'),
    (('lup', 'dun_lup'), 'Lower Passages'),
    (('cvw',), 'Waterways'),
    (('lux', 'cv'), 'Caves'),
    (('lu',), 'Lower Underrail'),
    (('up',), 'Upper Underrail'),
    (('dc',), 'Deep Caverns'),
    (('tch',), 'Institute of Tchort'),
    (('wbb', 'wba', 'warehouse'), 'Warehouses'),
    (('gammacompound', 'burc'), 'GMS Compound'),
    (('xpbl',), 'Black Sea'),
]


def region(zid):
    """Area (map) a zone is drawn on."""
    m = marker(zid)
    if m is not None and world()['zones'][m]['page'] in AREA_NAMES:
        return AREA_NAMES[world()['zones'][m]['page']]
    zid = zid.lower()
    for prefixes, name in REGIONS:
        if zid.startswith(prefixes):
            return name
    return 'Other'


def area_ready(page, area):
    import re as _re
    suffix = '' if area is None else '_' + _re.sub(r'\W+', '', area.lower())
    return os.path.exists(os.path.join(gamedata.CACHE, f'worldmap_{page}{suffix}.png'))
