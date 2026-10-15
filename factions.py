"""Faction relations stored in a save, the Faceless attitude calculation and faction kill counters.

Relations: global.dat TG:F -> FSW:FS -> FS1:D is a byte[] the game writes with a BinaryWriter (FactionSet,
read from its IL): int32 count, then per faction a string key and the faction: string id, string name,
int32 support level, bool, (int32, double, bool, bool has-float [, float]), int32 relation count, per
relation string target, int32 attitude, int32 support level (-1 = none), then a bool. Strings are .NET
7-bit length-prefixed UTF-8. Unknown fields are kept as read.

Attitude a character has toward a faction (from the game's IL): its personal override (C1:PA1, same
enum) if present, else the relation from its own faction, else Neutral.
"""
import struct

# Attitude enum: 0 is hostile (the Faceless calculation and the commander's "penalty is death" branch test
# for it), 2 is the game's default when no relation exists, 4 is what SGS has toward a member. The names of
# 1 and 3 aren't stored anywhere; they sit between those.
ATTITUDES = ['Hostile', 'Wary', 'Neutral', 'Friendly', 'Allied']
HOSTILE, NEUTRAL = 0, 2
PLAYER = 'player'


class _Reader:
    def __init__(self, b):
        self.b, self.o = b, 0

    def _unpack(self, fmt, n):
        v = struct.unpack_from(fmt, self.b, self.o)[0]
        self.o += n
        return v

    def i32(self):
        return self._unpack('<i', 4)

    def f64(self):
        return self._unpack('<d', 8)

    def f32(self):
        return self._unpack('<f', 4)

    def bool(self):
        return self._unpack('<?', 1)

    def str(self):
        n = shift = 0
        while True:
            c = self.b[self.o]
            self.o += 1
            n |= (c & 0x7f) << shift
            shift += 7
            if c < 0x80:
                break
        v = self.b[self.o:self.o + n].decode('utf-8')
        self.o += n
        return v


def _lps(s):
    b = s.encode('utf-8')
    n, out = len(b), bytearray()
    while n >= 0x80:
        out.append(n & 0x7f | 0x80)
        n >>= 7
    out.append(n)
    return bytes(out) + b


class Faction:
    __slots__ = ('key', 'id', 'name', 'support', 'flag', 'extra', 'relations', 'tail')

    def __init__(self, key, id, name, support, flag, extra, relations, tail):
        self.key, self.id, self.name, self.support, self.flag = key, id, name, support, flag
        self.extra, self.relations, self.tail = extra, relations, tail  # relations: {target: [attitude, support]}


def parse(blob):
    """{key: Faction} in stored order."""
    r = _Reader(blob)
    out = {}
    for _ in range(r.i32()):
        key = r.str()
        fid, name, support, flag = r.str(), r.str(), r.i32(), r.bool()
        extra = (r.i32(), r.f64(), r.bool())
        extra += (r.f32(),) if r.bool() else (None,)
        rels = {}
        for _ in range(r.i32()):
            target = r.str()
            rels[target] = [r.i32(), r.i32()]
        out[key] = Faction(key, fid, name, support, flag, extra, rels, r.bool())
    if r.o != len(blob):
        raise ValueError(f'faction data: {len(blob) - r.o} unread bytes')
    return out


def serialize(factions):
    out = bytearray(struct.pack('<i', len(factions)))
    for f in factions.values():
        out += _lps(f.key) + _lps(f.id) + _lps(f.name) + struct.pack('<i?', f.support, f.flag)
        a, b, c, d = f.extra
        out += struct.pack('<id??', a, b, c, d is not None) + (struct.pack('<f', d) if d is not None else b'')
        out += struct.pack('<i', len(f.relations))
        for target, (att, sup) in f.relations.items():
            out += _lps(target) + struct.pack('<ii', att, sup)
        out += struct.pack('<?', f.tail)
    return bytes(out)


# --- the Faceless at Talos Outpost (Deep Caverns) -------------------------------------------------------------
# Game variables the calculation reads (job run when the Talos commander starts the mindreading)
FACELESS_KILLED = 'global_facelessKilled'
FACELESS_KILLED_SHOP = 'loc_rcshop_deadfaceless'
FACELESS_FLAGS = [
    ('quest_fo_facelessRecon_finished', 'Faceless recon near Foundry finished'),
    ('npc_rcmindreader_removed', 'Rail Crossing mindreader left safely'),
    ('npc_rcmindreader_dead', 'Rail Crossing mindreader died'),
    ('npc_cc16_faceless_released', 'Injured Faceless in Core City released'),
    ('npc_cc16_faceless_killed', 'Injured Faceless in Core City killed'),
    ('npc_cc_injuredFaceless_attacked', 'Injured Faceless in Core City attacked'),
    ('loc_dc_flo_mindreading_passedHighTC', 'Thought Control check at the mindreading passed'),
]
TC_PASSED = 'loc_dc_flo_mindreading_passedHighTC'
SPY_QUEST = 'quest_dc_tch_ReconStarted'
# results the game stores; the commander's dialog branches on the score
SCORE_VAR = 'loc_dc_flo_attitudeCalculation'
SCORE_KILLS_VAR = 'loc_dc_flo_attitudeCalculationKilled'
FOUNDRY_FACELESS = 'faceless_fo'
TCHORTISTS_DC = 'tchortists_deepCaverns'
KILL_LIMIT = 10  # more kills than this (both counters together) set the score to -5


def kills_per_point(difficulty):
    """Faceless kills per penalty point: Easy 6, Normal 4, Hard 3, Dominating (and above) 2."""
    if difficulty is None:
        return 4
    if difficulty >= 3:
        return 2
    if difficulty >= 2:
        return 3
    return 6 if difficulty == 0 else 4


def outcome(score):
    """How the Faceless treat the player after the mindreading (commander's dialog)."""
    if score >= 3:
        return 'ally'
    if score >= 1:
        return 'friendly'
    return 'neutral' if score == 0 else 'hostile'


# Checkpoint guards at the edge of Faceless territory (dc_flcheckpoint.udlg): the first meeting decides once and
# stores the verdict; later meetings only read it. The Talos Outpost entrance guard (dc_flo_entranceguard.udlg)
# lets you in only with the pass, otherwise he attacks.
PASS_ALLOWED = 'faction_faceless_allowPassCaves'
PASS_FORBIDDEN = 'faction_faceless_forbiddenPassCaves'
CHECKPOINT_MET = 'dc_checkpointGuard_met'
CHECKPOINT_STATES = ['open', 'allowed', 'forbidden']


def checkpoint_state(var):
    if var(PASS_ALLOWED):
        return 'allowed'
    return 'forbidden' if var(PASS_FORBIDDEN) else 'open'


def checkpoint_verdict(var, relation):
    """What the guards decide at the first meeting: pass if the Foundry recon quest is finished and the
    Foundry Faceless aren't hostile to you, or if the Rail Crossing mindreader left safely."""
    recon = bool(var('quest_fo_facelessRecon_finished')) and relation(FOUNDRY_FACELESS, PLAYER) != HOSTILE
    return recon or bool(var('npc_rcmindreader_removed'))


def set_checkpoint(save, state):
    """'allowed' / 'forbidden' store a verdict; 'open' lets the next meeting decide again."""
    save.set_var(PASS_ALLOWED, state == 'allowed')
    save.set_var(PASS_FORBIDDEN, state == 'forbidden')
    if state == 'open':
        save.set_var(CHECKPOINT_MET, False)


def faceless_attitude(var, relation, difficulty):
    """The game's calculation (job started by the Talos Outpost commander), step by step.
    var(name) -> value of a game variable (None if unset); relation(src, tgt) -> attitude or None.
    Returns (score, steps, kills, spy) with steps = [(label key, fmt dict, points, kind)],
    kind '+' adds the points, '=' sets the score."""
    flag = lambda n: bool(var(n))
    passed = flag(TC_PASSED)
    kills = (var(FACELESS_KILLED) or 0) + (var(FACELESS_KILLED_SHOP) or 0)
    fo = relation(PLAYER, FOUNDRY_FACELESS)
    fo_hostile = fo == HOSTILE  # the game reads it without a fallback; a missing relation isn't hostile
    released, killed = flag('npc_cc16_faceless_released'), flag('npc_cc16_faceless_killed')
    attacked = flag('npc_cc_injuredFaceless_attacked')
    steps = []
    score = 0

    def add(cond, label, pts, kind='+', **fmt):
        nonlocal score
        if cond:
            score = score + pts if kind == '+' else pts
            steps.append((label, fmt, pts, kind))

    add(not fo_hostile and flag('quest_fo_facelessRecon_finished'),
        'Faceless recon near Foundry finished and you are not hostile to them', 1)
    add(flag('npc_rcmindreader_removed'), 'Rail Crossing mindreader left safely', 1)
    add(released and not killed and not attacked, 'Injured Faceless in Core City released unharmed', 1)
    add(flag('npc_rcmindreader_dead') and not passed, 'Rail Crossing mindreader died', -1)
    add(released and attacked and not passed, 'Injured Faceless in Core City attacked', -5, '=')
    add(killed and not passed, 'Injured Faceless in Core City killed', -5, '=')
    add(fo_hostile and not passed, 'You are hostile to the Faceless near Foundry', -5, '=')
    if not passed:
        if kills > KILL_LIMIT:
            add(True, 'More than {limit} Faceless killed ({n})', -5, '=', limit=KILL_LIMIT, n=kills)
        else:
            per = kills_per_point(difficulty)
            # the game's loop: one point for every `per` kills after the first
            add(kills > per, '{n} Faceless killed (one point per {per} after the first)',
                -((kills - 1) // per) if kills else 0, n=kills, per=per)
    spy = flag(SPY_QUEST) and not passed and relation(TCHORTISTS_DC, PLAYER) != HOSTILE
    return score, steps, kills, spy


# --- other faction kill counters with an effect in the game -----------------------------------------------------
# (variable, label, effect, linked flag set while the count reaches the threshold)
COUNTERS = [
    ('faction_xpbl_pirates_totalPiratesKilled', 'Pirates killed (Expedition)',
     'Dialogs react at 30, 50 and 60; from 50 the game skips the pirates\' attack events.', None),
    ('faction_protectorate_coreCity_jetSkiersKilled', 'Protectorate jet ski patrols killed (Expedition)',
     'From 10 people talk about the decimated patrols; the waterway scripts also check it.', None),
    ('faction_xphw_exoBase_exosoldiers_killed', 'Exosoldiers killed (Heavy Duty)',
     'Above 0 the psi commander answers differently; from 12 the game sets "too many killed".',
     ('faction_xphw_exoBase_exosoldiers_tooManyKilled', 12)),
]
