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

CACHE = 'worldmap_v4.json'
# Expedition's Black Sea zones share the coordinate space with the caves, so they get their own page
SEA_PREFIXES = ('xpbl', 'cvw')
PAGES = ('main', 'sea')


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

    zones, links, sprites = [], set(), []
    sprite_of = {}  # entity id -> sprite index
    for x in p.objects.values():
        if not isinstance(x, nrbf.Obj):
            continue
        if x.cls == 'SEA':
            m = gamedata._val(p, x.get('SEA:M'))
            f = nrbf.resolve(p, x.get('SEA:F'))
            if m and 'FloorGrid' not in m:  # editor grid, not drawn in game
                sprite_of[entity(x).id] = len(sprites)
                sprites.append({'m': m, 'f': [gamedata._val(p, f.get('X')), gamedata._val(p, f.get('Y'))],
                                'pos': pos(x)})
            continue
        if x.cls == 'ZMEA':
            zids = ids(x, 'ZMEA:R')
            if zids and zids != ['unknown']:
                X, Y, Z = pos(x)
                zones.append({'ids': zids, 'x': X, 'y': Y, 'z': Z, 'title': gamedata._val(p, x.get('ZMEA:CN')),
                              'contains': ids(x, 'ZMEA:C'), 'inset': gamedata._val(p, x.get('ZMEA:I')) == 1,
                              'page': 'sea' if zids[0].startswith(SEA_PREFIXES) else 'main',
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


def _page_of_sprites():
    """page of every sprite: from the zone it marks, else from the nearest zone marker"""
    zones = world()['zones']
    grid = {}
    for z in zones:
        grid.setdefault((round(z['x']), round(z['y'])), []).append(z)
    out = []
    for s in world()['sprites']:
        x, y, _ = s['pos']
        best, dist = None, 1e9
        for dx in range(-3, 4):
            for dy in range(-3, 4):
                for z in grid.get((round(x) + dx, round(y) + dy), ()):
                    d = (z['x'] - x) ** 2 + (z['y'] - y) ** 2
                    if d < dist:
                        best, dist = z, d
        out.append(best['page'] if best else ('sea' if 'xpbl' in s['m'].lower() else 'main'))
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
        w, h, pix = xnb.read_texture(os.path.join(gamedata.GAME, 'data', d['t'].replace('\\', '/').lower() + '.xnb'))
        _textures[d['t']] = Image.frombytes('RGBA', (w, h), bytes(pix))
    (sx, sy), (ux, uy), (tx, ty) = d['s'], d['uo'], d['to']
    fx, fy = s['f']
    a, b = project(*s['pos'])
    return (_textures[d['t']].crop((ux + fx * sx, uy + fy * sy, ux + (fx + 1) * sx, uy + (fy + 1) * sy)),
            (a - tx, b - ty))


def _render(page, path):
    from PIL import Image
    sprites = [s for s, pg in zip(world()['sprites'], _page_of_sprites()) if pg == page]
    pts = [project(*s['pos']) for s in sprites]
    left = min(a for a, b in pts) - MARGIN - 200
    top = min(b for a, b in pts) - MARGIN - 200
    width = max(a for a, b in pts) + MARGIN + 200 - left
    height = max(b for a, b in pts) + MARGIN + 200 - top
    img = Image.new('RGBA', (int(width), int(height)), (12, 12, 16, 255))
    # back to front, lower levels first
    for s in sorted(sprites, key=lambda s: (s['pos'][0] + s['pos'][1], s['pos'][2])):
        r = sprite_image(s)
        if r:
            img.alpha_composite(r[0], (int(r[1][0] - left), int(r[1][1] - top)))
    # crop to the drawn content
    box = img.getchannel('R').point(lambda v: 255 if v > 14 else 0).getbbox() or (0, 0, *img.size)
    box = (max(0, box[0] - MARGIN), max(0, box[1] - MARGIN), min(img.width, box[2] + MARGIN),
           min(img.height, box[3] + MARGIN))
    img.crop(box).convert('RGB').save(path)
    return [int(left) + box[0], int(top) + box[1]]


def page_image(page):
    """(png path, (left, top)) of a rendered map page; scene position of a zone = project() - (left, top)."""
    import json
    path = os.path.join(gamedata.CACHE, f'worldmap_{page}.png')
    meta = path[:-4] + '.json'
    stamp = [_path(), os.path.getmtime(_path())]
    try:
        with open(meta) as f:
            m = json.load(f)
        if m['stamp'] == stamp and os.path.exists(path):
            return path, m['origin']
    except (OSError, ValueError, KeyError):
        pass
    os.makedirs(gamedata.CACHE, exist_ok=True)
    origin = _render(page, path)
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
