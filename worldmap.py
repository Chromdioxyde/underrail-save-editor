"""Schematic world map from the game's global map (data/maps/world/globalmap.uz).

The global map is a zone file whose entities are markers: ZMEA = a zone (ZMEA:R = zone ids, ZMEA:CN = title,
position = the entity's location in zone-sized grid units, X east, Y south), TRSMA = a transition between
zones (TRSMA:L1 / TRSMA:L2 zone id lists). ZMEA:I = 1 marks an inset (South Gate Station's levels drawn as a
stack beside the map); ZMEA:C lists the zones a marker stands for, so inset zones are shown at that marker.
"""
import os
import re

import gamedata
import nrbf

CACHE = 'worldmap_v2.json'
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

    def pos(aspect):
        le = p.objects.get(parent.get(aspect.id))
        while le is not None and getattr(le, 'cls', '') != 'LE2':
            le = p.objects.get(parent.get(le.id))
        loc = nrbf.resolve(p, le.get('E4:L1'))
        return [gamedata._val(p, loc.get(a)) for a in ('X', 'Y', 'Z')]

    def ids(o, prefix):
        n = o.get(f'{prefix}:Count').value if f'{prefix}:Count' in o.names else 0
        return [s.lower() for s in (gamedata._val(p, o.get(f'{prefix}:{k}')) for k in range(n)) if s]

    zones, links = [], set()
    for x in p.objects.values():
        if not isinstance(x, nrbf.Obj):
            continue
        if x.cls == 'ZMEA':
            zids = ids(x, 'ZMEA:R')
            if zids and zids != ['unknown']:
                X, Y, Z = pos(x)
                zones.append({'ids': zids, 'x': X, 'y': Y, 'z': Z, 'title': gamedata._val(p, x.get('ZMEA:CN')),
                              'contains': ids(x, 'ZMEA:C'), 'inset': gamedata._val(p, x.get('ZMEA:I')) == 1,
                              'page': 'sea' if zids[0].startswith(SEA_PREFIXES) else 'main'})
        elif x.cls == 'TRSMA':
            for a in ids(x, 'TRSMA:L1'):
                for b in ids(x, 'TRSMA:L2'):
                    if a != b:
                        links.add(tuple(sorted((a, b))))
    return {'zones': zones, 'links': sorted(links)}


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
