"""Comparable stats of weapons and armor, read the same way from save items (incl. crafted ones with
embedded data) and from the game's item files.

Weapon damage with the character's skill follows the formula from the game's wiki:
  damage * (1 + k * effective skill / 100), k = 0.7, or 0.5 for light weapons (pistols, knives)
The effective skill is the value the game stores in the save (S4:MV: base plus attribute, feat and gear
bonuses).
"""
import gamedata
import nrbf

DAMAGE_TYPES = {0: 'Mechanical', 1: 'Heat', 2: 'Cold', 3: 'Electricity', 4: 'Acid', 5: 'Energy', 7: 'Bio'}
SHORT = {'Mechanical': 'Mech', 'Heat': 'Heat', 'Cold': 'Cold', 'Electricity': 'Elec', 'Acid': 'Acid',
         'Energy': 'Enrg', 'Bio': 'Bio'}
SKILL_OF_FAMILY = {'pistol': 'Guns', 'energy pistol': 'Guns', 'smg': 'Guns', 'assault rifle': 'Guns',
                   'sniper rifle': 'Guns', 'shotgun': 'Guns', 'light machine gun': 'Heavy Guns',
                   'minigun': 'Heavy Guns', 'grenade launcher': 'Heavy Guns', 'rocket launcher': 'Heavy Guns',
                   'crossbow': 'Crossbows', 'knife': 'Melee', 'fist': 'Melee', 'sledgehammer': 'Melee',
                   'crowbar': 'Melee', 'spear': 'Melee', 'sword': 'Melee', 'melee': 'Melee', 'throwing': 'Throwing'}
LIGHT_FAMILIES = {'pistol', 'energy pistol', 'knife'}
# equipment slot (as Save.equipped labels it) per item data class
SLOT_OF_CLASS = {'ASI': ['Armor'], 'HI': ['Head'], 'BI': ['Boots'], 'BI1': ['Belt'], 'SEI': ['Shield emitter'],
                 'WI': ['Weapon 1', 'Weapon 2']}


PROTECTION_ORDER = ['Mechanical', 'Energy', 'Heat', 'Electricity', 'Cold', 'Acid', 'Bio']
STAT_ORDER = ['damage', 'ap', 'per_ap', 'your_per_ap', 'crit', 'crit_dmg', 'precision'] + \
    [f'{p}_{t}' for t in PROTECTION_ORDER for p in ('dr', 'dt')] + \
    ['penalty', 'strength', 'range', 'max_range', 'magazine', 'level', 'durability', 'weight']


def order(key):
    return STAT_ORDER.index(key) if key in STAT_ORDER else len(STAT_ORDER)


class Stat:
    """One comparable value. better: +1 higher is better, -1 lower is better, 0 neutral."""

    def __init__(self, key, label, value, text=None, better=1):
        self.key, self.label, self.value, self.better = key, label, value, better
        self.text = text if text is not None else ('–' if value is None else f'{value:g}')


class Reader:
    """Uniform access to an item data object in a save graph or an item file."""

    def __init__(self, val, res, obj):
        self.val, self.res, self.o = val, res, obj

    def get(self, key, o=None):
        o = self.o if o is None else o
        return self.val(o, key) if key in o.names else None

    def ref(self, key, o=None):
        o = self.o if o is None else o
        return self.res(o.get(key)) if key in o.names else None

    def seq(self, key, o=None):
        n = self.get(f'{key}:Count', o) or 0
        return [self.ref(f'{key}:{i}', o) for i in range(n)]


def save_reader(it):
    """Reader for a save Item: its embedded data, else its library item file."""
    if it.data is not None:
        g = it.save.g
        return Reader(lambda o, k: g.val(o.get(k)), g.obj, it.data)
    return library_reader(it.info) if it.info else None


def library_reader(info):
    import hints
    try:
        p, o = hints._item_root(info)
    except Exception:
        return None
    return Reader(lambda ob, k: gamedata._val(p, ob.get(k)), lambda v: nrbf.resolve(p, v), o)


def weapon_family(r):
    import builds
    return builds.weapon_family(r.get('WI:WT'), r.get('WI:WVM'))


def stats(r, skills=None, strength=None):
    """[Stat] of a weapon or armor piece; skills = {skill name: effective value} for the character's damage."""
    if r is None:
        return []
    cls = r.o.cls
    out = []
    if cls == 'WI':
        family = weapon_family(r)
        ranges = []
        for d in r.seq('WI:D'):
            if d is not None:
                ranges.append((r.get('L', d), r.get('U', d), DAMAGE_TYPES.get(r.get('T', d), '?')))
        burst = r.get('WI:EB') or 0
        avg = sum((lo + hi) / 2 for lo, hi, _ in ranges) * max(1, burst)
        ap = r.get('WI:AP') or 0
        out.append(Stat('damage', 'Damage', avg, ' + '.join(f'{lo}–{hi} {SHORT.get(t, t)}' for lo, hi, t in ranges)
                        + (f' ×{burst}' if burst > 1 else '')))
        out.append(Stat('ap', 'Action points', ap, better=-1))
        out.append(Stat('per_ap', 'Damage per AP', avg / ap if ap else None,
                        f'{avg / ap:.2f}' if ap else '–'))
        skill = SKILL_OF_FAMILY.get(family)
        if skills and skill in skills and ap:
            k = 0.5 if family in LIGHT_FAMILIES else 0.7
            mult = 1 + k * skills[skill] / 100
            out.append(Stat('your_per_ap', 'Your damage per AP', avg * mult / ap, f'{avg * mult / ap:.2f}'))
        crit = r.get('WI:CSC')
        out.append(Stat('crit', 'Critical chance', crit, '–' if crit is None else f'{crit * 100:.0f}%'))
        cdb = r.get('WI:CDB')
        out.append(Stat('crit_dmg', 'Critical damage', cdb, '–' if cdb is None else f'×{cdb:g}'))
        prec = r.get('WI:PB')
        out.append(Stat('precision', 'Precision bonus', prec, '–' if not prec else f'{prec * 100:+.0f}%'))
        ms = r.get('WI:MS')
        out.append(Stat('strength', 'Strength requirement', ms, better=-1,
                        text='–' if not ms else (f'{ms} ⚠' if strength is not None and ms > strength else f'{ms}')))
        rng, mx = r.get('WI:OR'), r.get('WI:MR')
        if rng or mx:
            out.append(Stat('range', 'Optimal range', rng))
            out.append(Stat('max_range', 'Maximum range', mx))
        mag = r.get('WI:M')
        if mag:
            out.append(Stat('magazine', 'Magazine', mag))
    elif cls in ('ASI', 'HI', 'BI', 'BI1'):
        prot = {}
        for d in r.seq('AI1:DR'):
            if d is not None:
                prot[DAMAGE_TYPES.get(r.get('T', d), '?')] = (r.get('R', d) or 0, r.get('V', d) or 0)
        for t in PROTECTION_ORDER:
            if t in prot:
                dr, dt = prot[t]
                out.append(Stat(f'dr_{t}', f'{t} resistance', dr, f'{dr * 100:.0f}%'))
                out.append(Stat(f'dt_{t}', f'{t} threshold', dt))
        pen = r.get('AI1:E')
        if pen is not None:
            out.append(Stat('penalty', 'Armor penalty', pen, f'{pen * 100:.0f}%', better=-1))
        s = r.get('AT1:S')
        if s:
            out.append(Stat('strength', 'Strength requirement', s, better=-1,
                            text=f'{s} ⚠' if strength is not None and s > strength else f'{s}'))
    lvl = r.get('I:L')
    if lvl is not None and cls in SLOT_OF_CLASS:
        out.append(Stat('level', 'Item level', lvl))
        mx = gamedata.max_durability(lvl, r.get('WI:WT')) if cls in gamedata.DURABLE_CLASSES else None
        if mx:
            out.append(Stat('durability', 'Maximum durability', mx))
    w = r.get('I:W')
    if w is not None:
        out.append(Stat('weight', 'Weight', w, f'{w:g}', better=-1))
    return out


def character(save):
    """(effective skills, base Strength) of a save's character."""
    if save is None:
        return None, None
    skills = {f.name: f.extra[0].value if f.extra else f.value for f in save.skills()}
    strength = {f.name: f.value for f in save.attributes()}.get('Strength')
    return skills, strength
