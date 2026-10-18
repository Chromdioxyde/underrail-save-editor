"""Solvers for the puzzles the game generates anew for every playthrough, following the solution methods of the
Underrail wiki. Each solver takes the clues as the player sees them in the game; the save already holds the
generated values, so they can also be filled in from there (read from underrail.exe: e5t, euk/agn, c17, c9s)."""
import re
from collections import deque

WIKI = 'https://www.stygiansoftware.com/wiki/index.php?title='


# --- Note Cipher Puzzle (Expedition, Nexus of Technology) --------------------------------------------------
# The game picks three intervals and encrypts lines with a substitution table: the letters a-l, m-x and
# y-z 0-9 fill an octave each (the first three digits of every octave key), shifted right by the first
# interval, the first + second and the first + third. A line is a series of notes; its octave key holds
# one octave digit per note after those three digits.
INTERVALS = ['perfect unison', 'minor second', 'major second', 'minor third', 'major third', 'perfect fourth',
             'diminished fifth', 'perfect fifth', 'minor sixth', 'major sixth', 'minor seventh', 'major seventh',
             'perfect octave']
NOTES = {'C': 0, 'C#': 1, 'Db': 1, 'D': 2, 'D#': 3, 'Eb': 3, 'E': 4, 'F': 5, 'F#': 6, 'Gb': 6, 'G': 7,
         'G#': 8, 'Ab': 8, 'A': 9, 'A#': 10, 'Bb': 10, 'B': 11}
ALPHABET = 'abcdefghijklmnopqrstuvwxyz0123456789'
DIGIT_WORDS = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine']
_NOTE = re.compile(r'[A-G][#b]?')
_CIPHER_LINE = re.compile(r"(?:[A-G][#b]?|[\s\-'.,:;!?*])+")


def parse_intervals(text):
    """The three interval names in the order they appear, e.g. from 'Interval key: major sixth, ...'."""
    names = sorted(INTERVALS, key=len, reverse=True)
    found = re.findall('|'.join(re.escape(n) for n in names), text.lower())
    return [INTERVALS.index(n) for n in found]


def parse_octave_keys(text):
    """Every octave key (runs of digits, '?' = corrupted digit); the 'Key 1:' labels are skipped."""
    return re.findall(r'[0-9?*]{4,}', text)


def parse_cipher_lines(text):
    """The lines of notes from a pasted text; other lines (mail headers, greetings) are ignored."""
    return [ln.strip() for ln in text.splitlines()
            if ln.strip() and _CIPHER_LINE.fullmatch(ln.strip()) and _NOTE.search(ln)]


def cipher_table(octaves, intervals):
    """{absolute note (octave*12 + note): character} – the wiki's key table."""
    i1, i2, i3 = intervals
    table = {}
    for group, (octave, shift) in enumerate(zip(octaves, (i1, i1 + i2, i1 + i3))):
        for k in range(12):
            table[octave * 12 + shift + k] = ALPHABET[group * 12 + k]
    return table


def decipher(line, key, intervals):
    """Plain text of one line of notes with its octave key. '*' = corrupted character, '¿' = the key is too
    short or the note doesn't fit the table."""
    if len(key) < 3 or len(intervals) != 3 or not key[:3].isdigit():
        raise ValueError('an octave key starts with three digits and three intervals are needed')
    table = cipher_table([int(c) for c in key[:3]], intervals)
    digits = iter(key[3:])
    out = []
    for tok in re.findall(r'[A-G][#b]?|.', line):
        if tok not in NOTES:
            out.append(tok)
            continue
        d = next(digits, None)
        out.append('*' if d in ('?', '*') else '¿' if d is None else table.get(int(d) * 12 + NOTES[tok], '¿'))
    return ''.join(out)


def code_parts(text):
    """Digits of the vault code hidden in a deciphered line: digits, or digit words standing on their own."""
    parts = re.findall(r'\d', text)
    if parts:
        return parts
    words = re.findall(r'[a-z]+', text.lower())
    return [str(DIGIT_WORDS.index(w)) for w in words if w in DIGIT_WORDS]


def cipher_from_save(save):
    """{'lines', 'keys', 'intervals' (text), 'keypad', 'keypad_key'} as the game generated them, or None."""
    if not save.var('global_xpbl_encryptedText_intervalKey'):
        return None
    lines, keys = [], []
    i = 0
    while save.var(f'global_xpbl_encryptedString{i}') is not None:
        lines.append(save.var(f'global_xpbl_encryptedString{i}'))
        keys.append(save.var(f'global_xpbl_encryptedString{i}_key') or '')
        i += 1
    return {'lines': lines, 'keys': keys, 'intervals': save.var('global_xpbl_encryptedText_intervalKey'),
            'keypad': save.var('global_xpbl_encryptedKeypadCode'),
            'keypad_key': save.var('global_xpbl_encryptedKeypadCode_key')}


# --- Mutagen Puzzle (Deep Caverns, Mutagen Tanks B) --------------------------------------------------------
# Adding a reagent to the compound appends its positive atoms that aren't in it yet and removes the atoms it
# has as negative ones. The goal is the sequence of Exitus-1, atoms in the same order. The game builds
# Exitus-1 by adding 5-7 random reagents to an empty compound, so a solution of that length always exists.
def parse_atoms(text):
    """Atoms like 'GP' or '-DW'; other words ('Unreadable sequence' from the scanner) are skipped."""
    return re.findall(r'(?<!\S)-?[A-Za-z0-9]{2}(?!\S)', text)


def parse_reagents(text):
    """[(name, atoms)] from the Mutagen Scanner's output ('Reagent name: Io-1' / 'Sequence: GP S2 -DW') or
    lines like 'Io-1: GP S2 -DW'."""
    out, name = [], None
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r'(?i)reagent name:\s*(.+)', line)
        if m:
            name = m.group(1).strip()
            continue
        m = re.match(r'(?i)sequence:\s*(.*)', line)
        if m and name:
            atoms = parse_atoms(m.group(1))
            if atoms:
                out.append((name, atoms))
            name = None
            continue
        m = re.match(r'([^:]+):\s*(.+)', line)
        if m and parse_atoms(m.group(2)):
            out.append((m.group(1).strip(), parse_atoms(m.group(2))))
    return out


def add_reagent(compound, atoms):
    """The combinator's rule (agn.a in the game)."""
    out = list(compound)
    for a in atoms:
        if a.startswith('-'):
            if a[1:] in out:
                out.remove(a[1:])
        elif a not in out:
            out.append(a)
    return tuple(out)


def solve_mutagen(target, reagents, max_steps=12):
    """Shortest list of reagents that turns an empty compound into `target`, as [(name, compound after)], or
    None if none exists with up to `max_steps` reagents. Exitus reagents are left out.

    IDA* with a lower bound from the combinator's rule: atoms only get removed or appended at the end, so the
    atoms a compound keeps form a prefix of the target, and the rest of the target has to be appended in
    blocks, each in the order of one reagent's positive atoms."""
    target = tuple(target)
    usable = [(n, a) for n, a in reagents if not n.lower().startswith('exitus')]
    n = len(target)
    # blocks[i]: fewest reagents that can append target[i:]
    inf = float('inf')
    blocks = [inf] * n + [0]
    for i in range(n - 1, -1, -1):
        for _, atoms in usable:
            k = i
            for a in atoms:
                if k < n and a == target[k]:
                    k += 1
            if k > i:
                blocks[i] = min(blocks[i], 1 + blocks[k])

    def bound(state):
        k = 0
        for a in state:
            if k < n and a == target[k]:
                k += 1
        return max(blocks[k], 0 if state == target else 1)

    path = []

    def search(state, depth, limit, seen):
        if state == target:
            return True
        if depth + bound(state) > limit:
            return False
        for name, atoms in usable:
            nxt = add_reagent(state, atoms)
            if seen.get(nxt, inf) <= depth + 1:
                continue
            seen[nxt] = depth + 1
            path.append((name, nxt))
            if search(nxt, depth + 1, limit, seen):
                return True
            path.pop()
        return False

    if blocks[0] == inf:
        return None
    for limit in range(int(blocks[0]), max_steps + 1):
        if search((), 0, limit, {(): 0}):
            return path
    return None


def reagent_names():
    """MutagenReagentIndex -> reagent name ('Echo-1', …) from the reagent items in the game data."""
    import gamedata
    import hints
    import nrbf
    out = {}
    for path, info in gamedata.items().items():
        if not path.lower().startswith('plot\\mutagenreagents\\'):
            continue
        try:
            p, _ = hints._item_root(info)
        except Exception:
            continue
        props = {}
        for o in p.objects.values():
            if isinstance(o, nrbf.Obj) and o.cls == 'P':
                n, v = o.get('P:N'), o.get('P:V')
                props[getattr(nrbf.resolve(p, n), 'value', None)] = getattr(nrbf.resolve(p, v), 'value', None)
        if isinstance(props.get('MutagenReagentIndex'), int) and props.get('MutagenName'):
            out[props['MutagenReagentIndex']] = props['MutagenName']
    return out


def mutagen_from_save(save):
    """(Exitus-1 atoms, [(reagent name, atoms)]) as the game generated them, or None (the game creates them
    with the Deep Caverns)."""
    import nrbf
    mcx = next((o for o in save.g.p.objects.values() if isinstance(o, nrbf.Obj) and o.cls == 'MCX'), None)
    if mcx is None:
        return None

    def items(o, prefix):
        return [save.val(o.get(f'{prefix}:{i}')) for i in range(save.val(o.get(f'{prefix}:Count')))]

    atoms = items(mcx, 'MCX:A')

    def sequence(ref):
        return [('-' if a < 0 else '') + atoms[abs(a)] for a in items(save.obj(ref), 'MCY:C')]

    names = reagent_names()
    reagents = [(names.get(i, f'#{i}'), sequence(mcx.get(f'MCX:R:{i}')))
                for i in range(save.val(mcx.get('MCX:R:Count')))]
    return sequence(mcx.get('MCX:T')), reagents


# --- Emergency phones (Upper Underrail, Phreak's hideouts) ------------------------------------------------
# Every button plays a sound that the game numbers 1-6 at random once per playthrough; all phones share it.
# With 12 Perception the dialog spells out a sequence as those numbers.
PHONE_BUTTONS = [('redCross', 'Red Cross'), ('rat', 'Red Rathound'), ('security', 'Green Shield'),
                 ('wrench', 'Yellow Wrench'), ('hazard', 'Red Exclamation Mark'), ('info', 'Blue Exclamation Mark')]


def phone_numbers_from_save(save):
    """{button key: sound number} or None before the first emergency phone."""
    nums = {k: save.var(f'loc_up_emergencyPhoneNumber_{k}') for k, _ in PHONE_BUTTONS}
    return nums if all(isinstance(v, int) for v in nums.values()) else None


def phone_sequences_from_save(save):
    """[(hideout number, number sequence)] the phones currently ask for."""
    out = []
    for n, key in ((1, 'One'), (2, 'Two')):
        seq = save.var(f'loc_up_emergencyPhoneHideout{key}CurrentSequenceString')
        if seq:
            out.append((n, seq))
    return out


def phone_buttons(sequence, numbers):
    """Button keys to press for a number sequence ('3 1 4' or '314'); None for numbers no button has."""
    by_number = {n: k for k, n in numbers.items()}
    return [by_number.get(int(d)) for d in re.findall(r'\d', sequence)]


# --- L/S console (Core City Office Building) --------------------------------------------------------------
# The maintenance robot in the basement beeps five times in the west, east and south: three fixed blocks in
# one of three orders, picked when the console is first used (c9s).
CONSOLE_BLOCKS = ['LLSLL', 'SSSLS', 'LSLSL']
CONSOLE_SEQUENCES = ['LLSLLSSSLSLSLSL', 'SSSLSLSLSLLLSLL', 'LSLSLLLSLLSSSLS']


def console_from_save(save):
    seq = save.var('loc_dun_ccResOffice_actualSequence')
    return seq if isinstance(seq, str) and seq else None
