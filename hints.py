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

def weapons(limit=40):
    """Library weapons ranked by average damage per base action point."""
    rows, seen = [], set()
    for info in gamedata.items().values():
        if info['cls'] != 'WI' or info['name'] in seen:
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


def armor_combos(recipe, top=5, comps=None):
    """Best component combinations of a recipe by protection score per (1 + penalty)."""
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
        score = rate(prot)
        results.append({'parts': list(zip([s for _, s in r['slots']], parts)), 'prot': prot, 'penalty': penalty,
                        'strength': strength, 'score': score, 'balance': score / (1 + 2 * penalty)})
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
