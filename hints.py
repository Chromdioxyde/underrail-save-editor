"""Gameplay hints computed from the game's own data: weapon damage per action point, armor component
combinations rated by protection versus armor penalty, and which merchants sell what.

Formulas (read from underrail.exe, see README):
  * weapon: average damage of all damage ranges x burst shots (WI:EB) / base action points (WI:AP)
  * armor component per damage type: threshold = C + Q*V, resistance = A + B*Q (Q = quality), each times
    the slot factor of the recipe; armor penalty = sum of component E x factor (quality-independent)
  * merchants: fixed shipments list items; random stock picks items whose trade category (I:T)
    matches one of the store's categories (TDY:C)
"""
import os

import gamedata
import nrbf

QUALITY = 160  # reference component quality for the armor tables
DAMAGE_TYPES = {0: 'Mechanical', 1: 'Heat', 2: 'Cold', 3: 'Electricity', 4: 'Acid', 5: 'Energy', 7: 'Bio'}
SHORT = {'Mechanical': 'Mech', 'Heat': 'Heat', 'Cold': 'Cold', 'Electricity': 'Elec', 'Acid': 'Acid',
         'Energy': 'Enrg', 'Bio': 'Bio'}
# weapon type ids (WI:WT) named after the weapons that use them
WEAPON_TYPES = {0: 'Pistol', 1: 'SMG', 2: 'Assault rifle', 3: 'Sniper rifle', 4: 'Shotgun', 5: 'Crossbow / special',
                6: 'Melee', 7: 'Grenade launcher', 8: 'Heavy energy', 9: 'Light machine gun', 10: 'Minigun',
                11: 'Rocket launcher'}
# store file prefixes whose location is unambiguous
LOCATIONS = {'cc': 'Core City', 'sgs': 'South Gate Station', 'jy': 'Junkyard', 'rc': 'Rail Crossing',
             'fo': 'Foundry', 'ch': 'Camp Hathor', 'pb': 'Port Balor'}


def _item_root(info):
    p = gamedata.read_nrbf(os.path.join(gamedata.GAME, 'data', 'rules', 'items',
                                        info['path'].replace('\\', '/') + '.item'))
    return p, p.objects[p.root]


def _val(p, o, k):
    return gamedata._val(p, o.get(k)) if k in o.names else None


# --- merchants ----------------------------------------------------------------------------

def store_name(store_id):
    loc, _, who = store_id.partition('_')
    placed = map_index()['merchants'].get(store_id.lower()) if map_index_ready() else None
    if placed and placed['npc'] and placed['zones']:
        # the trading NPC's own name and the zone they stand in
        zid = max(placed['zones'], key=placed['zones'].get)
        return f"{placed['npc']} ({LOCATIONS.get(loc) or zone_name(zid)})"
    if who and loc in LOCATIONS:
        return f'{who.replace("_", " ").title()} ({LOCATIONS[loc]})'
    return store_id.replace('_', ' ').title()


def _build_stores():
    d = os.path.join(gamedata.GAME, 'data', 'rules', 'stores')
    out = {}
    for fn in sorted(os.listdir(d)):
        if not fn.endswith('.store'):
            continue
        try:
            p = gamedata.read_nrbf(os.path.join(d, fn))
        except Exception:
            continue
        o = p.objects[p.root]
        fixed, tags = set(), set()
        for k in range(o.get('S1:S:Count').value if 'S1:S:Count' in o.names else 0):
            ship = nrbf.resolve(p, o.get(f'S1:S:{k}'))
            ic = nrbf.resolve(p, ship.get('MS1:SI'))
            if ic is None or 'IC:I:Count' not in ic.names:
                continue
            for j in range(ic.get('IC:I:Count').value):
                it = nrbf.resolve(p, ic.get(f'IC:I:{j}'))
                dp = nrbf.resolve(p, it.get('II:DP')) if it is not None else None
                if dp is not None and 'LIDP:P' in dp.names:
                    fixed.add(gamedata._val(p, dp.get('LIDP:P')).lower())
        for k in range(o.get('S1:TD:Count').value if 'S1:TD:Count' in o.names else 0):
            td = nrbf.resolve(p, o.get(f'S1:TD:{k}'))
            tag = gamedata._val(p, td.get('TDY:C')) if 'TDY:C' in td.names else None
            if tag is not None:
                tags.add(tag)
        out[fn[:-6]] = {'fixed': sorted(fixed), 'tags': sorted(tags)}
    return out


_stores = None


def stores():
    global _stores
    if _stores is None:
        d = os.path.join(gamedata.GAME, 'data', 'rules', 'stores')
        _stores = gamedata._cached('stores.json', [d], _build_stores)
    return _stores


_trade_tags = {}


def trade_tag(info):
    """Trade category of an item (I:T), used for merchants' random stock."""
    key = info['path'].lower()
    if key not in _trade_tags:
        try:
            p, o = _item_root(info)
            _trade_tags[key] = _val(p, o, 'I:T')
        except Exception:
            _trade_tags[key] = None
    return _trade_tags[key]


def where_to_buy(info):
    """(merchants with it in a fixed shipment, merchants that can roll it in random stock)"""
    key, tag = info['path'].lower(), trade_tag(info)
    fixed = [store_name(s) for s, d in stores().items() if key in d['fixed']]
    random_ = [store_name(s) for s, d in stores().items() if tag is not None and tag in d['tags']
               and store_name(s) not in fixed]
    return fixed, random_


# --- weapons ------------------------------------------------------------------------------

def weapons(limit=40, families=None):
    """Library weapons ranked by average damage per base action point, optionally only the given weapon
    families (see builds.weapon_family)."""
    import builds
    rows, seen = [], set()
    for info in gamedata.items().values():
        if info['cls'] != 'WI' or info['name'] in seen:
            continue
        if families is not None and builds.library_family(info) not in families:
            continue
        seen.add(info['name'])
        try:
            p, o = _item_root(info)
        except Exception:
            continue
        ap = _val(p, o, 'WI:AP') or 0
        burst = _val(p, o, 'WI:EB') or 0
        ranges = []
        for k in range(_val(p, o, 'WI:D:Count') or 0):
            d = nrbf.resolve(p, o.get(f'WI:D:{k}'))
            lo, hi, t = (gamedata._val(p, d.get(x)) for x in ('L', 'U', 'T'))
            ranges.append((lo, hi, DAMAGE_TYPES.get(t, str(t))))
        avg = sum((lo + hi) / 2 for lo, hi, _ in ranges) * max(1, burst)
        if ap > 0 and avg > 0:
            rows.append({'info': info, 'type': WEAPON_TYPES.get(info.get('wtype'), '?'), 'ap': ap, 'burst': burst,
                         'ranges': ranges, 'avg': avg, 'per_ap': avg / ap})
    rows.sort(key=lambda r: -r['per_ap'])
    return rows[:limit]


# --- armor --------------------------------------------------------------------------------

def components():
    """Armor component name -> stats at QUALITY (protection per damage type, penalty, strength)."""
    out = {}
    for info in gamedata.items().values():
        if info['cls'] not in ('ABCI', 'SBCI'):
            continue
        try:
            p, o = _item_root(info)
        except Exception:
            continue
        prot = {}
        for k in range(_val(p, o, 'ABCI:DRF:Count') or 0):
            d = nrbf.resolve(p, o.get(f'ABCI:DRF:{k}'))
            f = {n: gamedata._val(p, x) for n, x in zip(d.names, d.values)}
            prot[DAMAGE_TYPES.get(f['T'], str(f['T']))] = (f['A'] + f['B'] * QUALITY, f['C'] + QUALITY * f['V'])
        out[info['name']] = {'info': info, 'E': _val(p, o, 'ABCI:E') or 0, 'S': _val(p, o, 'ABCI:S') or 0,
                             'prot': prot, 'group': info['path'].split('\\')[1].lower()}
    return out


# recipes: slots (component folder per slot, None = slot may stay empty) and slot factors
RECIPES = {
    'Tactical vest': {'slots': [('vest', 'carrier vest'), ('ballisticpanels', 'ballistic panel'),
                                ('armors|ballisticarmorplates', 'armor plate'), ('fabric', 'fabric')],
                      'factors': [1, 1, 1, 1]},
    'Metal armor': {'slots': [('metalplates', 'metal plates'), ('vest', 'carrier vest')], 'factors': [1, 1],
                    'halve': 'Electricity'},
    'Leather armor': {'slots': [('leather', 'leather'), ('padding', 'padding'), ('fabric', 'fabric')],
                      'factors': [1, 1, 0.5]},
    'Metal helmet': {'slots': [('metalplates', 'metal plates'), ('padding', 'padding')], 'factors': [0.3, 0.35]},
    'Boots': {'slots': [('leather', 'leather'), ('padding', 'padding')], 'factors': [0.35, 0.35]},
    'Greaves': {'slots': [('metalplates', 'metal plates')], 'factors': [0.25]},
}
# how much each damage type counts when rating protection (mechanical damage is by far the most common)
WEIGHTS = {'Mechanical': 3.0, 'Energy': 1.0, 'Heat': 1.0, 'Electricity': 0.8, 'Cold': 0.6, 'Acid': 0.6, 'Bio': 0.4}


def rate(prot):
    """Single protection score: weighted resistance plus threshold (scaled to similar magnitude)."""
    return sum(WEIGHTS.get(t, 0.3) * (dr * 100 + dt * 1.5) for t, (dr, dt) in prot.items())


def armor_combos(recipe, top=5, comps=None, weight=2.0, max_penalty=None, max_strength=None):
    """Best component combinations of a recipe by protection score per (1 + weight * penalty); combinations
    above max_penalty or needing more than max_strength are left out."""
    import itertools
    comps = comps or components()
    r = RECIPES[recipe]
    choices = []
    for folders, _ in r['slots']:
        allowed = folders.split('|')
        choices.append([n for n, c in comps.items() if c['group'] in allowed])
    results = []
    for parts in itertools.product(*choices):
        prot, penalty, strength = {}, 0.0, 0
        for name, factor in zip(parts, r['factors']):
            c = comps[name]
            penalty += c['E'] * factor
            strength = max(strength, c['S'])
            for t, (dr, dt) in c['prot'].items():
                a, b = prot.get(t, (0, 0))
                prot[t] = (a + dr * factor, b + dt * factor)
        if r.get('halve') in prot:
            dr, dt = prot[r['halve']]
            prot[r['halve']] = (dr / 2, dt / 2)
        if (max_penalty is not None and penalty > max_penalty + 1e-9) or \
                (max_strength is not None and strength > max_strength):
            continue
        score = rate(prot)
        results.append({'parts': list(zip([s for _, s in r['slots']], parts)), 'prot': prot, 'penalty': penalty,
                        'strength': strength, 'score': score, 'balance': score / (1 + weight * penalty)})
    results.sort(key=lambda x: -x['balance'])
    # avoid near-duplicates (e.g. normal and infused variants of the same leather)
    out, seen = [], set()
    for res in results:
        key = tuple(round(v[0] * 100) for v in sorted(res['prot'].values())) + (round(res['penalty'] * 100),)
        if key in seen:
            continue
        seen.add(key)
        out.append(res)
        if len(out) >= top:
            break
    return out


def fmt_prot(prot):
    order = ['Mechanical', 'Energy', 'Heat', 'Electricity', 'Cold', 'Acid', 'Bio']
    return ', '.join(f'{SHORT.get(t, t)} {dr * 100:.0f}%/{dt:.0f}'
                     for t, (dr, dt) in sorted(prot.items(), key=lambda x: order.index(x[0]) if x[0] in order else 9)
                     if dr > 0.005 or dt >= 1)


# --- map locations ------------------------------------------------------------------------

# how an item sits in a map layer, by the class of the object holding its inventory
HOLDER_KINDS = {'CEA3': 'container', 'IO': 'random loot', 'C1': 'carried by an NPC', 'CGS': 'carried by an NPC',
                'SAP#G1>C1#-': 'carried by an NPC', 'GIJ': 'job reward', 'AL': 'on the ground'}
KIND_ORDER = ['container', 'on the ground', 'job reward', 'carried by an NPC', 'random loot']


def _maps_dir():
    return os.path.join(gamedata.GAME, 'data', 'maps', 'locale', 'static')


def _zone_names():
    """zone id (lower case, as in map file names) -> display name from the world map"""
    p = gamedata.read_nrbf(os.path.join(gamedata.GAME, 'data', 'maps', 'world', 'southunderrail.world'))
    root = p.objects[p.root]
    out = {}
    for k in range(root.get('WM:L:Count').value):
        loc = nrbf.resolve(p, root.get(f'WM:L:{k}'))
        zid, name = gamedata._val(p, loc.get('LD1:I')), gamedata._val(p, loc.get('LD1:N'))
        if zid:
            out[zid.lower()] = name or zid
    return out


def zone_id(layer_file):
    """Zone id of a map layer file: 'cc10_l2.uzl' -> 'cc10', 'xpbl_l10_l1.uzl' -> 'xpbl_l10'."""
    import re
    base = layer_file.rsplit('.', 1)[0].lower()
    m = re.match(r'^(.+)_l\d+(_[a-z].*)?$', base)
    return m.group(1) if m else base


def _build_map_index(progress=None):
    names = _zone_names()
    d = _maps_dir()
    files = sorted(f for f in os.listdir(d) if f.endswith('.uzl'))
    index, creatures, merchants, zones = {}, {}, {}, {}
    for n, fn in enumerate(files):
        if progress:
            progress(n, len(files))
        zid = zone_id(fn)
        zname = names.get(zid) or names.get(zid.split('_')[0])
        if not zname:
            # DLC layers whose ids aren't on the world map
            zname = {'xpbl': 'Expedition', 'xphw': 'Heavy Duty'}.get(zid.split('_')[0], zid)
        if 'test' in zid or zname.lower().startswith('test'):
            continue  # developer test maps aren't part of the game world
        try:
            p = gamedata.read_nrbf(os.path.join(d, fn))
        except Exception:
            continue
        zones[zid] = zname
        parent = {}
        for x in p.objects.values():
            for k in nrbf.children(x):
                parent.setdefault(k, x.id)
        for x in p.objects.values():
            if not isinstance(x, nrbf.Obj):
                continue
            if 'C1:N' in x.names:
                # characters and creatures placed in the zone (by display name)
                cname = gamedata._val(p, x.get('C1:N'))
                if cname:
                    by_zone = creatures.setdefault(cname, {})
                    by_zone[zid] = by_zone.get(zid, 0) + 1
            if 'MEA1:S' in x.names:
                # merchant aspect: store id, owned by the character that trades
                sid = gamedata._val(p, x.get('MEA1:S'))
                if sid:
                    m = merchants.setdefault(sid.lower(), {'zones': {}, 'npc': None})
                    m['zones'][zid] = m['zones'].get(zid, 0) + 1
                    o = x
                    while o is not None and not m['npc']:
                        for k in ('C1:N', 'E2:N'):
                            if k in getattr(o, 'names', ()):
                                m['npc'] = gamedata._val(p, o.get(k))
                        o = p.objects.get(parent.get(o.id))
            if 'II:DP' not in x.names:
                continue
            dp = nrbf.resolve(p, x.get('II:DP'))
            if dp is None or 'LIDP:P' not in dp.names:
                continue
            ic = parent.get(x.id)
            holder = p.objects.get(parent.get(ic)) if ic is not None else None
            kind = HOLDER_KINDS.get(getattr(holder, 'cls', ''), 'other')
            key = gamedata._val(p, dp.get('LIDP:P')).lower()
            entry = index.setdefault(key, {})
            entry[f'{zid}|{kind}'] = entry.get(f'{zid}|{kind}', 0) + 1
    if progress:
        progress(len(files), len(files))
    return {'items': index, 'creatures': creatures, 'merchants': merchants, 'zones': zones}


MAP_CACHE = 'map_index_v5.json'
_map_index = None


def map_index_ready():
    return _map_index is not None or os.path.exists(os.path.join(gamedata.CACHE, MAP_CACHE))


def map_index(progress=None):
    """{'items': item path -> {"zone id|kind": count}, 'creatures': name -> {zone id: count},
    'merchants': store id -> {'zones': {zone id: count}, 'npc': name}, 'zones': zone id -> display name};
    scanning all map layers takes under a minute, then it's cached."""
    global _map_index
    if _map_index is None:
        _map_index = gamedata._cached(MAP_CACHE, [_maps_dir()], lambda: _build_map_index(progress))
    return _map_index


def zone_name(zid):
    return map_index()['zones'].get(zid, zid) if map_index_ready() else zid


def found_spots(info):
    """[(zone id, kind, count)] for an item, most useful kinds first (fixed spots before random loot)."""
    entry = map_index()['items'].get(info['path'].lower(), {})
    rows = []
    for k, cnt in entry.items():
        zid, kind = k.rsplit('|', 1)
        rows.append((zid, kind, cnt))
    rows.sort(key=lambda r: (KIND_ORDER.index(r[1]) if r[1] in KIND_ORDER else 9, -r[2], r[0]))
    return rows


def where_found(info, limit=4):
    """([(zone, kind, count)], total) by zone display name, or None while the maps aren't scanned yet."""
    if not map_index_ready():
        return None
    merged = {}
    for zid, kind, cnt in found_spots(info):
        key = (zone_name(zid), kind)
        merged[key] = merged.get(key, 0) + cnt
    rows = [(z, k, c) for (z, k), c in merged.items()]
    rows.sort(key=lambda r: (KIND_ORDER.index(r[1]) if r[1] in KIND_ORDER else 9, -r[2], r[0]))
    return rows[:limit], len(rows)


# animal parts: the creature they come from (leathers name it, other parts are named after it)
PART_SUFFIXES = (' Leather', ' Skin', ' Scales', ' Carapace', ' Poison Gland', ' Gland', ' Hide', ' Shell')


def source_creature(info):
    """Creature an animal component is harvested from, or None."""
    try:
        p, o = _item_root(info)
    except Exception:
        return None
    cp = nrbf.resolve(p, o.get('I:CP')) if 'I:CP' in o.names else None
    if cp is not None and 'PC:P:Count' in cp.names:
        for k in range(cp.get('PC:P:Count').value):
            prop = nrbf.resolve(p, cp.get(f'PC:P:{k}'))
            if gamedata._val(p, prop.get('P:N')) == 'SourceCreature':
                name = gamedata._val(p, prop.get('P:V'))
                # infused leather is refined normal leather
                return name[len('Infused '):] if name and name.startswith('Infused ') else name
    if not map_index_ready():
        return None
    known = map_index()['creatures']
    name = info['name']
    for suffix in PART_SUFFIXES:
        if name.endswith(suffix):
            base = name[:-len(suffix)]
            base = base[len('Infused '):] if base.startswith('Infused ') else base
            if base in known:
                return base
    return None


def creature_spots(name):
    """{zone id: count} where creatures of this name (or variants like "<name> Alpha") are placed."""
    if not map_index_ready() or not name:
        return {}
    creatures = map_index()['creatures']
    words = name.split()
    # try the full name first, then shorter forms ("Heartbreaker Serpent" is placed as "Heartbreaker")
    for n in range(len(words), 0, -1):
        base = ' '.join(words[:n])
        zones = {}
        for cname, by_zone in creatures.items():
            # "Rathound" also matches "Rathound Alpha"/"Rathound King", but not "Ancient Rathound"
            if cname == base or cname.startswith(base + ' '):
                for z, c in by_zone.items():
                    zones[z] = zones.get(z, 0) + c
        if zones:
            return zones
    return {}


def creature_zones(name, limit=5):
    """([(zone, count)], total) by zone display name."""
    merged = {}
    for zid, c in creature_spots(name).items():
        merged[zone_name(zid)] = merged.get(zone_name(zid), 0) + c
    rows = sorted(merged.items(), key=lambda kv: (-kv[1], kv[0]))
    return rows[:limit], len(rows)


def merchant_zones(store_id):
    """{zone id: count} where the merchant with this store stands (empty if not placed in a map)."""
    if not map_index_ready():
        return {}
    return map_index()['merchants'].get(store_id.lower(), {}).get('zones', {})


def locations(info):
    """Everything known about where to get an item, with zone ids for the world map:
    {'merchants': [(name, fixed, {zone id: n})], 'found': [(zone id, kind, n)],
     'creature': name or None, 'creature_zones': {zone id: n}}"""
    key, tag = info['path'].lower(), trade_tag(info)
    merchants = {}
    for sid, d in stores().items():
        fixed = key in d['fixed']
        if fixed or (tag is not None and tag in d['tags']):
            name = store_name(sid)
            prev = merchants.get(name)
            zones = dict(prev[1]) if prev else {}
            for z, c in merchant_zones(sid).items():
                zones[z] = zones.get(z, 0) + c
            merchants[name] = (fixed or bool(prev and prev[0]), zones)
    ready = map_index_ready()
    creature = source_creature(info) if info.get('category') == 'components' else None
    return {'merchants': sorted(((n, f, z) for n, (f, z) in merchants.items()), key=lambda r: (not r[1], r[0])),
            'found': found_spots(info) if ready else [],
            'creature': creature,
            'creature_zones': creature_spots(creature) if creature else {}}
