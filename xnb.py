"""Minimal XNB reader for Texture2D assets (LZX-compressed or plain), with DXT1/3/5 decoding.
LZX decoder ported from MonoGame's LzxDecoder (itself based on libmspack)."""
import struct

MIN_MATCH = 2
NUM_CHARS = 256
PRETREE_NUM_ELEMENTS = 20
ALIGNED_NUM_ELEMENTS = 8
NUM_SECONDARY_LENGTHS = 249
VERBATIM, ALIGNED, UNCOMPRESSED = 1, 2, 3

EXTRA_BITS = []
_j = 0
for _i in range(0, 52, 2):
    EXTRA_BITS += [_j, _j]
    if _i != 0 and _j < 17:
        _j += 1
POSITION_BASE = []
_j = 0
for _i in range(51):
    POSITION_BASE.append(_j)
    _j += 1 << EXTRA_BITS[_i]


class _Bits:
    def __init__(self, data, pos):
        self.d, self.pos, self.buf, self.left = data, pos, 0, 0

    def reset(self):
        self.buf, self.left = 0, 0

    def ensure(self, n):
        while self.left < n:
            lo = self.d[self.pos] if self.pos < len(self.d) else 0
            hi = self.d[self.pos + 1] if self.pos + 1 < len(self.d) else 0
            self.pos += 2
            self.buf = (self.buf << 16) | (hi << 8) | lo
            self.left += 16

    def peek(self, n):
        self.ensure(n)
        return (self.buf >> (self.left - n)) & ((1 << n) - 1)

    def read(self, n):
        if n == 0:
            return 0
        v = self.peek(n)
        self.left -= n
        self.buf &= (1 << self.left) - 1
        return v


class _Huff:
    """Canonical Huffman decoder from code lengths."""

    def __init__(self, lens):
        self.codes = {}
        code = 0
        for length in range(1, 17):
            for sym, l in enumerate(lens):
                if l == length:
                    self.codes[(length, code)] = sym
                    code += 1
            code <<= 1
        self.maxlen = max(lens) if any(lens) else 0

    def read(self, bits):
        code = 0
        for length in range(1, self.maxlen + 1):
            code = (code << 1) | bits.read(1)
            sym = self.codes.get((length, code))
            if sym is not None:
                return sym
        raise ValueError('bad huffman code')


class Lzx:
    def __init__(self, window_bits=16):
        self.wsize = 1 << window_bits
        self.window = bytearray(self.wsize)
        self.wpos = 0
        self.r = [1, 1, 1]
        posn_slots = {15: 30, 16: 32, 17: 34, 18: 36, 19: 38, 20: 42, 21: 50}[window_bits]
        self.main_elements = NUM_CHARS + (posn_slots << 3)
        self.main_len = [0] * self.main_elements
        self.length_len = [0] * (NUM_SECONDARY_LENGTHS + 1)
        self.header_read = False
        self.block_remaining = 0
        self.block_length = 0
        self.block_type = 0

    def _read_lengths(self, bits, lens, first, last):
        pre = _Huff([bits.read(4) for _ in range(PRETREE_NUM_ELEMENTS)])
        x = first
        while x < last:
            z = pre.read(bits)
            if z == 17:
                for _ in range(bits.read(4) + 4):
                    lens[x] = 0; x += 1
            elif z == 18:
                for _ in range(bits.read(5) + 20):
                    lens[x] = 0; x += 1
            elif z == 19:
                y = bits.read(1) + 4
                z = pre.read(bits)
                z = lens[x] - z
                if z < 0:
                    z += 17
                for _ in range(y):
                    lens[x] = z; x += 1
            else:
                z = lens[x] - z
                if z < 0:
                    z += 17
                lens[x] = z; x += 1

    def decompress(self, data, pos, in_len, out_len):
        bits = _Bits(data, pos)
        end = pos + in_len
        if not self.header_read:
            if bits.read(1):
                bits.read(16); bits.read(16)
            self.header_read = True
        togo = out_len
        win, wsize, r = self.window, self.wsize, self.r
        while togo > 0:
            if self.block_remaining == 0:
                if self.block_type == UNCOMPRESSED:
                    if self.block_length & 1:
                        bits.pos += 1
                    bits.reset()
                self.block_type = bits.read(3)
                i = bits.read(16); j = bits.read(8)
                self.block_remaining = self.block_length = (i << 8) | j
                if self.block_type == ALIGNED:
                    self.aligned = _Huff([bits.read(3) for _ in range(ALIGNED_NUM_ELEMENTS)])
                if self.block_type in (VERBATIM, ALIGNED):
                    self._read_lengths(bits, self.main_len, 0, 256)
                    self._read_lengths(bits, self.main_len, 256, self.main_elements)
                    self.main = _Huff(self.main_len)
                    self._read_lengths(bits, self.length_len, 0, NUM_SECONDARY_LENGTHS)
                    self.length = _Huff(self.length_len)
                elif self.block_type == UNCOMPRESSED:
                    bits.ensure(16)
                    if bits.left > 16:
                        bits.pos -= 2
                    bits.reset()
                    r[0], r[1], r[2] = struct.unpack_from('<III', data, bits.pos)
                    bits.pos += 12
                else:
                    raise ValueError(f'bad LZX block type {self.block_type}')
            this_run = min(self.block_remaining, togo)
            togo -= this_run
            self.block_remaining -= this_run
            self.wpos &= wsize - 1
            if self.block_type in (VERBATIM, ALIGNED):
                while this_run > 0:
                    main = self.main.read(bits)
                    if main < NUM_CHARS:
                        win[self.wpos] = main; self.wpos += 1; this_run -= 1
                        continue
                    main -= NUM_CHARS
                    mlen = main & 7
                    if mlen == 7:
                        mlen += self.length.read(bits)
                    mlen += MIN_MATCH
                    moff = main >> 3
                    if moff > 2:
                        extra = EXTRA_BITS[moff]
                        if self.block_type == VERBATIM:
                            moff = POSITION_BASE[moff] - 2 + bits.read(extra) if moff != 3 else 1
                        else:
                            moff = POSITION_BASE[moff] - 2
                            if extra > 3:
                                moff += bits.read(extra - 3) << 3
                                moff += self.aligned.read(bits)
                            elif extra == 3:
                                moff += self.aligned.read(bits)
                            elif extra > 0:
                                moff += bits.read(extra)
                            else:
                                moff = 1
                        r[2], r[1], r[0] = r[1], r[0], moff
                    elif moff == 0:
                        moff = r[0]
                    elif moff == 1:
                        moff = r[1]; r[1] = r[0]; r[0] = moff
                    else:
                        moff = r[2]; r[2] = r[0]; r[0] = moff
                    this_run -= mlen
                    dst = self.wpos
                    src = (dst - moff) & (wsize - 1)
                    for _ in range(mlen):
                        win[dst] = win[src]
                        dst += 1; src = (src + 1) & (wsize - 1)
                    self.wpos += mlen
                if this_run < 0:
                    self.block_remaining -= -this_run
                    togo -= -this_run
            else:
                win[self.wpos:self.wpos + this_run] = data[bits.pos:bits.pos + this_run]
                bits.pos += this_run
                self.wpos += this_run
        start = (self.wpos or wsize) - out_len
        return bytes(win[start:start + out_len])


def decompress_xnb(raw):
    """Returns the decompressed XNB payload (everything after the 10-byte header)."""
    if raw[:3] != b'XNB':
        raise ValueError('not an XNB file')
    flags = raw[5]
    size = struct.unpack_from('<I', raw, 6)[0]
    if not flags & 0x80:
        return raw[10:size]
    dsize = struct.unpack_from('<I', raw, 10)[0]
    pos, end = 14, size
    out = bytearray()
    lzx = Lzx(16)
    while pos < end:
        hi, lo = raw[pos], raw[pos + 1]
        block, frame = (hi << 8) | lo, 0x8000
        if hi == 0xFF:
            frame = (lo << 8) | raw[pos + 2]
            block = (raw[pos + 3] << 8) | raw[pos + 4]
            pos += 5
        else:
            pos += 2
        if block == 0 or frame == 0:
            break
        out += lzx.decompress(raw, pos, block, frame)
        pos += block
    return bytes(out[:dsize])


def _7bit(d, p):
    n = shift = 0
    while True:
        b = d[p]; p += 1
        n |= (b & 0x7f) << shift; shift += 7
        if not b & 0x80:
            return n, p


def read_texture(path):
    """Returns (width, height, RGBA bytes) of the first mip level."""
    d = decompress_xnb(open(path, 'rb').read())
    n, p = _7bit(d, 0)
    for _ in range(n):
        l, p = _7bit(d, p); p += l + 4
    _, p = _7bit(d, p)  # shared resources
    _, p = _7bit(d, p)  # type reader index
    fmt, w, h, mips = struct.unpack_from('<iIII', d, p); p += 16
    size = struct.unpack_from('<I', d, p)[0]; p += 4
    pix = d[p:p + size]
    if fmt == 0:
        return w, h, pix
    if fmt in (4, 5, 6):
        return w, h, _dxt(pix, w, h, fmt)
    raise ValueError(f'unsupported surface format {fmt}')


def _c565(c):
    return ((c >> 11) & 31) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31


def _dxt(src, w, h, fmt):
    out = bytearray(w * h * 4)
    bsize = 8 if fmt == 4 else 16
    p = 0
    for by in range((h + 3) // 4):
        for bx in range((w + 3) // 4):
            alpha = [255] * 16
            if fmt == 5:  # DXT3: explicit 4-bit alpha
                a = int.from_bytes(src[p:p + 8], 'little')
                alpha = [((a >> (4 * i)) & 15) * 17 for i in range(16)]
                p += 8
            elif fmt == 6:  # DXT5: interpolated alpha
                a0, a1 = src[p], src[p + 1]
                idx = int.from_bytes(src[p + 2:p + 8], 'little')
                if a0 > a1:
                    pal = [a0, a1] + [((7 - i) * a0 + i * a1) // 7 for i in range(1, 7)]
                else:
                    pal = [a0, a1] + [((5 - i) * a0 + i * a1) // 5 for i in range(1, 5)] + [0, 255]
                alpha = [pal[(idx >> (3 * i)) & 7] for i in range(16)]
                p += 8
            c0, c1, lut = struct.unpack_from('<HHI', src, p); p += 8
            a, b = _c565(c0), _c565(c1)
            if c0 > c1 or fmt != 4:
                cols = [a, b, tuple((2 * x + y) // 3 for x, y in zip(a, b)), tuple((x + 2 * y) // 3 for x, y in zip(a, b))]
                trans = False
            else:
                cols = [a, b, tuple((x + y) // 2 for x, y in zip(a, b)), (0, 0, 0)]
                trans = True
            for i in range(16):
                x, y = bx * 4 + (i & 3), by * 4 + (i >> 2)
                if x >= w or y >= h:
                    continue
                ci = (lut >> (2 * i)) & 3
                o = (y * w + x) * 4
                out[o:o + 3] = bytes(cols[ci])
                out[o + 3] = 0 if trans and ci == 3 else alpha[i]
    return bytes(out)
