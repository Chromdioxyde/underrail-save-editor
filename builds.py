"""Common character build archetypes (as players describe them in Steam guides, on underrail.info and
RPG Codex) and how to tell which one a character follows.

Each build names the weapon families it uses, its main attributes and skills, the feats that define it
(ids from data/knowledge/feats.k) and an armor profile that weighs protection against armor penalty:
  light  – stealth, dodge and evasion builds: armor penalty hurts them most, so keep it low
  medium – ranged builds that fight from cover: balanced
  heavy  – tanks and heavy weapons: protection first, penalty matters little
"""

# armor penalty weight in the rating (protection / (1 + weight * penalty)) and the highest penalty considered
ARMOR_PROFILES = {
    'light': {'weight': 6.0, 'max_penalty': 0.15, 'recipes': ['Leather armor', 'Tactical vest', 'Boots']},
    'medium': {'weight': 2.0, 'max_penalty': 0.40,
               'recipes': ['Tactical vest', 'Leather armor', 'Metal armor', 'Metal helmet', 'Boots']},
    'heavy': {'weight': 0.5, 'max_penalty': None,
              'recipes': ['Metal armor', 'Tactical vest', 'Metal helmet', 'Greaves', 'Boots']},
}

BUILDS = [
    {'id': 'assault', 'name': 'Assault rifle', 'skills': ['Guns'], 'families': ['assault rifle'],
     'attributes': ['Perception', 'Strength', 'Constitution'], 'armor': 'heavy',
     'feats': ['commando', 'concentratedfire', 'fullauto', 'suppressivefire', 'pointshot', 'rapidfire', 'gunnut'],
     'note': 'Bursts from the front line. Rifles need Strength; heavy metal armor with Armor Sloping is common.'},
    {'id': 'sniper', 'name': 'Sniper', 'skills': ['Guns'], 'families': ['sniper rifle'],
     'attributes': ['Perception', 'Dexterity', 'Strength'], 'armor': 'medium',
     'feats': ['as', 's', 'ss', 'shootingspree', 'a', 'ambush', 'gunnut'],
     'note': 'Big single shots from range, often opening from stealth. A tactical vest keeps the penalty moderate.'},
    {'id': 'smg', 'name': 'SMG', 'skills': ['Guns'], 'families': ['smg'],
     'attributes': ['Dexterity', 'Perception', 'Agility'], 'armor': 'medium',
     'feats': ['specops', 'commando', 'fullauto', 'kcs', 'pointshot', 'rapidfire', 'gunnut'],
     'note': 'Cheap bursts, many attacks per turn. Low Strength needs, so light vests are enough.'},
    {'id': 'pistol', 'name': 'Pistol', 'skills': ['Guns'], 'families': ['pistol', 'energy pistol'],
     'attributes': ['Dexterity', 'Perception', 'Agility'], 'armor': 'medium',
     'feats': ['g', 'gunfu', 'im', 'steadfastaim', 'cookedshot', 'bullettime', 'kcs', 'ss'],
     'note': 'Fast, crit-heavy single shots (Gunslinger, Execute); energy pistols use Guns too.'},
    {'id': 'shotgun', 'name': 'Shotgun', 'skills': ['Guns'], 'families': ['shotgun'],
     'attributes': ['Strength', 'Perception', 'Constitution'], 'armor': 'heavy',
     'feats': ['barrelstare', 'pelletmayhem', 'perfectscattering', 'sixthshell', 'fragmentedchaos', 'leadingshot'],
     'note': 'Expedition shotguns: brutal at close range, so it pays to stand in heavy armor.'},
    {'id': 'heavyguns', 'name': 'Heavy guns', 'skills': ['Heavy Guns'],
     'families': ['light machine gun', 'minigun', 'grenade launcher', 'rocket launcher'],
     'attributes': ['Strength', 'Constitution', 'Perception'], 'armor': 'heavy',
     'feats': ['bullettrance', 'gunnershigh', 'magdump', 'shellshock', 'demolitionman', 'practicedparabola',
               'heavymetal', 'suppressivefire'],
     'note': 'Heavy Duty machine guns and launchers: high Strength, heavy armor (Heavy Metal).'},
    {'id': 'crossbow', 'name': 'Crossbow', 'skills': ['Crossbows', 'Traps'], 'families': ['crossbow'],
     'attributes': ['Dexterity', 'Perception', 'Agility'], 'armor': 'light',
     'feats': ['concussiveshots', 'elementalbolts', 'specialtactics', 'ds', 's', 'ss', 'kcs', 'ambush',
               'deadlysnares', 'trapexpert'],
     'note': 'Special bolts and traps, usually played sneaky – keep the armor penalty low for Stealth.'},
    {'id': 'knife', 'name': 'Stealth knife', 'skills': ['Melee', 'Stealth', 'Dodge', 'Evasion'], 'families': ['knife'],
     'attributes': ['Dexterity', 'Agility'], 'armor': 'light',
     'feats': ['o', 'cheapshots', 'cutthroat', 'eviscerate', 'cripplingstrike', 'parry', 'jetandjab', 'hitandrun',
               's2', 'fancyfootwork', 'uncannydodge'],
     'note': 'Crits from stealth and many cheap stabs; relies on Dodge/Evasion, so light armor only.'},
    {'id': 'unarmed', 'name': 'Unarmed / psi monk', 'skills': ['Melee', 'Dodge', 'Evasion', 'Thought Control'],
     'families': ['fist'], 'attributes': ['Dexterity', 'Will', 'Agility'], 'armor': 'light',
     'feats': ['lightningpunches', 'improvedunarmedcombat', 'expertunarmedcombat', 'heavypunch', 'combo',
               'criticalpower', 'dirtykick', 'psychostaticelectricity', 'forceuser', 'pe'],
     'note': 'Fists (often mixed with psi): very cheap attacks, so armor penalty and AP matter a lot.'},
    {'id': 'sledgehammer', 'name': 'Sledgehammer', 'skills': ['Melee'], 'families': ['sledgehammer', 'crowbar'],
     'attributes': ['Strength', 'Constitution', 'Dexterity'], 'armor': 'heavy',
     'feats': ['superslam', 'pummel', 'heavymetal', 'heavyweight', 'brutality', 'bonebreaker', 'juggernaut',
               'armorsloping'],
     'note': 'Slow, crushing hits in the thick of it: heavy metal armor, Juggernaut, Armor Sloping.'},
    {'id': 'spear', 'name': 'Spear', 'skills': ['Melee'], 'families': ['spear'],
     'attributes': ['Strength', 'Dexterity', 'Constitution'], 'armor': 'medium',
     'feats': ['impale', 'sweep', 'fend', 'spearguardian', 'spearthrow', 'irongrip'],
     'note': 'Expedition spears: reach and control; Iron Grip lets you wear more armor.'},
    {'id': 'sword', 'name': 'Sword', 'skills': ['Melee'], 'families': ['sword'],
     'attributes': ['Dexterity', 'Strength', 'Agility'], 'armor': 'medium',
     'feats': ['decapitate', 'flurry', 'onslaught', 'riposte', 'parry'],
     'note': 'Expedition swords and machetes: combos and counters.'},
    {'id': 'throwing', 'name': 'Throwing', 'skills': ['Throwing'], 'families': ['throwing'],
     'attributes': ['Dexterity', 'Perception', 'Agility'], 'armor': 'light',
     'feats': ['improvedthrowing', 'fatalthrow', 'pinning', 'ripper', 'splitspare', 'remotesurgeon',
               'threepointer', 'trickytrajectory', 'o'],
     'note': 'Throwing knives and grenades; mostly a secondary skill, often next to knives or psi.'},
    {'id': 'psi', 'name': 'Psi', 'skills': ['Thought Control', 'Psychokinesis', 'Metathermics', 'Temporal Manipulation'],
     'families': [], 'attributes': ['Will', 'Intelligence'], 'armor': 'light',
     'feats': ['pe', 'advancedpsiempathy', 'premeditation', 'psychosis', 'forcefullinnervation', 'neurology',
               'locusofcontrol', 'td', 'ci', 'pm', 'ct', 'ms', 'tranquility'],
     'note': 'Psi abilities instead of weapons. Psi Empathy costs health; armor penalty slows you, '
             'so light armor or a tactical vest is usual.'},
]
BY_ID = {b['id']: b for b in BUILDS}

GUN_FAMILIES = {0: 'pistol', 1: 'smg', 2: 'assault rifle', 3: 'sniper rifle', 4: 'shotgun', 5: 'crossbow',
                7: 'grenade launcher', 9: 'light machine gun', 10: 'minigun', 11: 'rocket launcher'}
# melee weapons by their visual model prefix (WI:WVM)
MELEE_FAMILIES = {'': 'fist', 'k': 'knife', 's': 'sledgehammer', 'c': 'crowbar', 'xpbls': 'spear',
                  'xpblm': 'sword'}


def weapon_family(wtype, wvm):
    """Weapon family from the weapon type (WI:WT) and visual model (WI:WVM)."""
    if wtype == 6:
        return MELEE_FAMILIES.get(wvm or '', 'melee') if wvm is not None else None  # None = creature weapon
    if wtype == 0 and wvm in ('ep', 'ap'):
        return 'energy pistol'
    return GUN_FAMILIES.get(wtype)


def detect(save):
    """[(build, score)] best first: skill points in the build's skills, owned key feats and the family of
    the equipped weapons."""
    skills = {f.name: f.value for f in save.skills()}
    feats = set(save.feats())
    families = set()
    for it in save.equipped():
        if it.category == 'weapons' and it.slot and it.slot.startswith('Weapon'):
            families.add(item_family(it))
    out = []
    for b in BUILDS:
        main = [skills.get(s, 0) for s in b['skills']]
        score = max(main) + 0.25 * sum(main[1:]) if main else 0
        score += 25 * len(feats & set(b['feats']))
        if families & set(b['families']):
            score += 60
        out.append((b, score))
    out.sort(key=lambda r: -r[1])
    return out


def item_family(it):
    """Weapon family of a save Item (library or crafted)."""
    g = it.save.g
    if it.data is not None:
        wvm = g.val(it.data.get('WI:WVM')) if 'WI:WVM' in it.data else None
        return weapon_family(it.weapon_type, wvm)
    if it.info:
        return library_family(it.info)
    return None


_lib = {}


def library_family(info):
    key = info['path'].lower()
    if key not in _lib:
        if info['cls'] == 'QSI' and 'throwingknife' in key.replace(' ', ''):
            _lib[key] = 'throwing'
        elif info['cls'] != 'WI':
            _lib[key] = None
        else:
            import hints
            try:
                p, o = hints._item_root(info)
                wvm = hints._val(p, o, 'WI:WVM')
            except Exception:
                wvm = None
            _lib[key] = weapon_family(info.get('wtype'), wvm)
    return _lib[key]
