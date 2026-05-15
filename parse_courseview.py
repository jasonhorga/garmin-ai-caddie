"""Parse a Garmin CourseView IMG file → polygons (fairway, green, bunker, water) in lat/lon.

Pipeline:
  IMG container → GMP subfile → TRE (subdivision tree) + RGN (geometry) + LBL (labels)
  TRE extended-type offset records give per-subdivision cumulative offsets into
  the extended polygon/polyline/point sections
  RGN ext-type polygon records have bit-packed vertex deltas relative to subdivision center

Format spec sources:
  - Garmin IMG/RGN format (OSM wiki, Memotech PDF, imgdecode-mb decode_rgn.cc lines 462-525)
  - GMP-embedded subfile offsets are absolute positions in the GMP container

Output: parse_img(path) → list[Polygon] with type/subtype/lat-lon vertices.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

SEMI_TO_DEG = 360 / (1 << 24)  # 24-bit semicircle → degrees


# ----------------------------------------------------------------------
# Layer 1: IMG → GMP
# ----------------------------------------------------------------------

def extract_gmp(img: bytes) -> bytes:
    """Pull the .GMP subfile out of an IMG container by walking the FAT."""
    BS = 512
    GMP_ENTRY = 0x1200  # second FAT entry — the first describes the FAT itself
    size = struct.unpack("<I", img[GMP_ENTRY + 12 : GMP_ENTRY + 16])[0]
    ptrs = struct.unpack("<240H", img[GMP_ENTRY + 0x20 : GMP_ENTRY + 0x200])
    blocks = []
    for p in ptrs:
        if p == 0xFFFF or (p == 0 and blocks):
            break
        blocks.append(p)
    return b"".join(img[p * BS : (p + 1) * BS] for p in blocks)[:size]


# ----------------------------------------------------------------------
# Layer 2: GMP header → sub-subfile absolute offsets
# ----------------------------------------------------------------------

@dataclass
class GmpOffsets:
    tre: int
    rgn: int
    lbl: int
    dem: int


def parse_gmp_header(gmp: bytes) -> GmpOffsets:
    return GmpOffsets(
        tre=struct.unpack("<I", gmp[0x19:0x1D])[0],
        rgn=struct.unpack("<I", gmp[0x1D:0x21])[0],
        lbl=struct.unpack("<I", gmp[0x21:0x25])[0],
        dem=struct.unpack("<I", gmp[0x2D:0x31])[0],
    )


# ----------------------------------------------------------------------
# Layer 3: TRE — bbox, subdivisions, extended-type offsets
# ----------------------------------------------------------------------

def _s24(buf: bytes, off: int) -> int:
    v = buf[off] | (buf[off + 1] << 8) | (buf[off + 2] << 16)
    return v - 0x1000000 if v & 0x800000 else v


@dataclass
class Bbox:
    north: float
    east: float
    south: float
    west: float


@dataclass
class Subdivision:
    """One geographic tile. `bits` controls coord precision (lower = bigger units)."""
    rgn_off: int   # raw 3 bytes from sd record; 0 in CourseView (data indexed via object_groups)
    types: int     # flag byte; also 0 in CourseView
    center_lat: float  # degrees
    center_lon: float  # degrees
    width: int     # half-width in coord units, high bit stripped
    height: int    # half-height in coord units
    bits: int      # bits-per-coord for this level (set after parse)


@dataclass
class ObjectGroup:
    """Cumulative offsets into the bulk polygon/polyline/point data sections.

    Span for subdivision N = [record[N], record[N + 1]). CourseView stores
    these records only for the detailed level; the overview subdivision has no
    extended geometry record.
    """
    poly_off: int
    polyl_off: int
    point_off: int


@dataclass
class TreData:
    bbox: Bbox
    subdivisions: list[Subdivision]
    object_groups: list[ObjectGroup]
    ext_first_subdiv_index: int = 0
    ext_line_types: set[int] = field(default_factory=set)
    ext_area_types: set[int] = field(default_factory=set)
    ext_point_types: set[int] = field(default_factory=set)


def parse_tre(gmp: bytes, tre_off: int) -> TreData:
    base = tre_off
    bbox = Bbox(
        north=_s24(gmp, base + 0x15) * SEMI_TO_DEG,
        east=_s24(gmp, base + 0x18) * SEMI_TO_DEG,
        south=_s24(gmp, base + 0x1B) * SEMI_TO_DEG,
        west=_s24(gmp, base + 0x1E) * SEMI_TO_DEG,
    )

    # Section pointers here are absolute in the GMP container for this
    # CourseView flavor.
    ml_off = struct.unpack("<I", gmp[base + 0x21 : base + 0x25])[0]
    ml_len = struct.unpack("<I", gmp[base + 0x25 : base + 0x29])[0]
    sd_off = struct.unpack("<I", gmp[base + 0x29 : base + 0x2D])[0]
    sd_len = struct.unpack("<I", gmp[base + 0x2D : base + 0x31])[0]
    ext_off = struct.unpack("<I", gmp[base + 0x7C : base + 0x80])[0]
    ext_len = struct.unpack("<I", gmp[base + 0x80 : base + 0x84])[0]
    ext_rsize = struct.unpack("<H", gmp[base + 0x84 : base + 0x86])[0]
    ext_magic = struct.unpack("<I", gmp[base + 0x86 : base + 0x8A])[0]
    ext_overview_off = struct.unpack("<I", gmp[base + 0x8A : base + 0x8E])[0]
    ext_overview_len = struct.unpack("<I", gmp[base + 0x8E : base + 0x92])[0]
    # Section.writeSectionInfo() also emits itemSize when it is nonzero, even
    # when called without withItemSize=true. So the counts start two bytes later.
    ext_overview_rsize = struct.unpack("<H", gmp[base + 0x92 : base + 0x94])[0]
    n_ext_lines, n_ext_areas, n_ext_points = struct.unpack("<HHH", gmp[base + 0x94 : base + 0x9A])

    # Map levels — 4 bytes each: zoom, bits-per-coord, n_subdivisions (u16)
    levels: list[tuple[int, int, int]] = []
    for i in range(ml_len // 4):
        o = ml_off + i * 4
        levels.append((gmp[o] & 0x0F, gmp[o + 1], struct.unpack("<H", gmp[o + 2 : o + 4])[0]))

    # Subdivisions — non-last-level records are 16 bytes, last-level are 14
    subdivisions: list[Subdivision] = []
    cursor = 0
    for li, (zoom, bits, nsd) in enumerate(levels):
        rec_size = 14 if li == len(levels) - 1 else 16
        for _ in range(nsd):
            o = sd_off + cursor
            rgn_o = gmp[o] | (gmp[o + 1] << 8) | (gmp[o + 2] << 16)
            types = gmp[o + 3]
            lon = _s24(gmp, o + 4)
            lat = _s24(gmp, o + 7)
            w_raw = struct.unpack("<H", gmp[o + 10 : o + 12])[0]
            h = struct.unpack("<H", gmp[o + 12 : o + 14])[0]
            subdivisions.append(Subdivision(
                rgn_off=rgn_o, types=types,
                center_lat=lat * SEMI_TO_DEG, center_lon=lon * SEMI_TO_DEG,
                width=w_raw & 0x7FFF, height=h, bits=bits,
            ))
            cursor += rec_size

    # Extended-type offset records. This is the TRE7 section mkgmap calls
    # extTypeOffsets. Record count = detailed subdivisions + one final total
    # record; overview levels may have no corresponding record.
    n_records = ext_len // ext_rsize if ext_rsize else 0
    available = n_records
    first_level_index = 0
    for idx in range(len(levels) - 1, -1, -1):
        available -= levels[idx][2]
        if available < 0:
            raise ValueError("TRE7 extended-type offset record count is inconsistent with levels")
        if available == 1:
            first_level_index = idx
            break
    ext_first_subdiv_index = sum(nsd for _zoom, _bits, nsd in levels[:first_level_index])

    object_groups: list[ObjectGroup] = []
    for i in range(n_records):
        o = ext_off + i * ext_rsize
        poly_off = polyl_off = point_off = 0
        if ext_magic & 0x1:
            poly_off = struct.unpack("<I", gmp[o : o + 4])[0]
            o += 4
        if ext_magic & 0x2:
            polyl_off = struct.unpack("<I", gmp[o : o + 4])[0]
            o += 4
        if ext_magic & 0x4:
            point_off = struct.unpack("<I", gmp[o : o + 4])[0]
        object_groups.append(ObjectGroup(poly_off=poly_off, polyl_off=polyl_off, point_off=point_off))

    ext_records: list[int] = []
    for i in range(ext_overview_len // ext_overview_rsize):
        o = ext_overview_off + i * ext_overview_rsize
        ext_records.append(0x10000 | (gmp[o] << 8) | gmp[o + 2])
    ext_line_types = set(ext_records[:n_ext_lines])
    ext_area_types = set(ext_records[n_ext_lines : n_ext_lines + n_ext_areas])
    ext_point_types = set(ext_records[n_ext_lines + n_ext_areas : n_ext_lines + n_ext_areas + n_ext_points])

    return TreData(
        bbox=bbox,
        subdivisions=subdivisions,
        object_groups=object_groups,
        ext_first_subdiv_index=ext_first_subdiv_index,
        ext_line_types=ext_line_types,
        ext_area_types=ext_area_types,
        ext_point_types=ext_point_types,
    )


# ----------------------------------------------------------------------
# Layer 4: RGN — extended-type polygon decoder
# ----------------------------------------------------------------------

@dataclass
class RgnHeader:
    """Extended geometry section addresses."""
    ext_poly_off: int
    ext_poly_len: int
    ext_line_off: int
    ext_line_len: int
    ext_point_off: int
    ext_point_len: int


def parse_rgn_header(gmp: bytes, rgn_off: int) -> RgnHeader:
    # +0x1D = ext-type polygon section base offset (absolute in GMP for this
    # CourseView flavor).
    # +0x21 = ext-type polygon section length
    return RgnHeader(
        ext_poly_off=struct.unpack("<I", gmp[rgn_off + 0x1D : rgn_off + 0x21])[0],
        ext_poly_len=struct.unpack("<I", gmp[rgn_off + 0x21 : rgn_off + 0x25])[0],
        ext_line_off=struct.unpack("<I", gmp[rgn_off + 0x39 : rgn_off + 0x3D])[0],
        ext_line_len=struct.unpack("<I", gmp[rgn_off + 0x3D : rgn_off + 0x41])[0],
        ext_point_off=struct.unpack("<I", gmp[rgn_off + 0x55 : rgn_off + 0x59])[0],
        ext_point_len=struct.unpack("<I", gmp[rgn_off + 0x59 : rgn_off + 0x5D])[0],
    )


# Bitstream coord unpacking (Python port of imgdecode-mb rgn.cc)

def _bits_per_coord(base: int, is_signed: bool, extra_bit: bool) -> int:
    n = 2
    n += base if base <= 9 else (2 * base - 9)
    if is_signed:
        n += 1
    if extra_bit:
        n += 1
    return n


def bits_per_coord(base: int, bfirst: int, extra_bit: bool) -> tuple[int, int, int]:
    """Returns (bits_per_lon, bits_per_lat, setup_bits). Reads first byte of bitstream."""
    sbits = 2  # always: 1 bit for x_sign_same flag + 1 bit for y_sign_same flag

    x_sign_same = bool(bfirst & 0x1)
    if x_sign_same:
        x_signed = False
        sbits += 1  # one extra bit holds the actual sign
    else:
        x_signed = True
    blon = _bits_per_coord(base & 0x0F, x_signed, extra_bit)

    y_sign_same = bool(bfirst & (0x4 if x_sign_same else 0x2))
    if y_sign_same:
        y_signed = False
        sbits += 1
    else:
        y_signed = True
    blat = _bits_per_coord((base >> 4) & 0x0F, y_signed, extra_bit)

    return blon, blat, sbits


class BitReader:
    """LSB-first bit reader over a bytes buffer. Bits within each byte are consumed LSB→MSB."""
    def __init__(self, data: bytes):
        self.data = data
        self.bit_pos = 0
        self.n_bits = len(data) * 8

    def read(self, n: int) -> int:
        v = 0
        for i in range(n):
            if self.bit_pos >= self.n_bits:
                return v  # exhausted
            byte_idx = self.bit_pos >> 3
            bit_idx = self.bit_pos & 7
            v |= ((self.data[byte_idx] >> bit_idx) & 1) << i
            self.bit_pos += 1
        return v

    def has_next(self, n: int) -> bool:
        return self.bit_pos + n <= self.n_bits


def coord_bits(base: int, sign: int, extra_bit: int) -> int:
    """Total bits per delta. sign==0 means per-vertex sign bit included; else constant sign (±1)."""
    n = 2
    n += base if base <= 9 else (2 * base - 9)
    if sign == 0:
        n += 1
    n += extra_bit
    return n


def read_coord_offset(reader: BitReader, n_bits: int, sign: int, extra_bit: int) -> int:
    """Decode one signed delta from the bitstream.

    Ported from asamm/garmin-img-parser BitStreamReader.readCoordOffset.
    Handles the "negative-zero stretch" recursion: a value with sign bit set but zero magnitude
    means the actual delta exceeds n_bits range — read another n_bits and combine.
    """
    if sign == 0:
        value = reader.read(n_bits)
        sign_mask = 1 << (n_bits - 1)
        if value & sign_mask:
            comp = value ^ sign_mask
            if extra_bit == 0:
                if comp != 0:
                    return comp - sign_mask
                # stretch: recurse with same n_bits
                other = read_coord_offset(reader, n_bits, sign, extra_bit)
                return (1 - value + other) if other < 0 else (value - 1 + other)
            # extra_bit branch — keeps LSB of value as a flag
            if (comp & 0xFFFFFE) != 0:
                return (comp & 0xFFFFFE) - sign_mask
            other = read_coord_offset(reader, n_bits - 1, sign, 0)
            return (1 - sign_mask + 1 + (other << 1)) if other < 0 else (sign_mask - 1 - 1 + (other << 1))
        # positive
        return (value & 0xFFFFFE) if extra_bit > 0 else value
    # constant sign
    val = reader.read(n_bits)
    return ((val >> 1) * sign) << 1 if extra_bit > 0 else val * sign


def skip_ext_extra_bytes(buf: memoryview, off: int) -> int:
    """Skip mkgmap-style extended-type extra bytes."""
    b = buf[off]
    off += 1
    if b & 0xE0:
        while b != 0x01:
            b = buf[off]
            off += 1
    return off


@dataclass
class Polygon:
    """One closed polygon feature."""
    type: int     # Garmin type byte
    subtype: int  # subtype (5 bits)
    ext_type: int # 0x10000 | (type << 8) | subtype — combined "extended" code
    lats: list[float]
    lons: list[float]
    has_label: bool
    label_off: int  # 24-bit offset into LBL strings, or 0
    long_extra_bit: int = 0  # debug — which extra-bit branch was used


@dataclass
class Point:
    """One extended point feature."""
    type: int
    subtype: int
    ext_type: int
    lat: float
    lon: float
    has_label: bool
    label_off: int


def decode_ext_poly_record(
    buf: memoryview,
    off: int,
    subdiv: Subdivision,
    *,
    consume_unk_trailer: bool,
) -> tuple[Polygon, int]:
    """Decode one extended polygon/polyline record starting at `off`.

    Port of asamm/garmin-img-parser parseExtPoly (RgnSubFile.java:390-).
    """
    type_b = buf[off]; off += 1
    subtype_b = buf[off]; off += 1

    has_label = bool(subtype_b & 0x20)
    has_unk = bool(subtype_b & 0x40)        # direction flag for lines; ignored for polygons
    has_extra_byte = bool(subtype_b & 0x80)
    subtype = subtype_b & 0x1F
    # asamm fullTipo: ((tipo + 0x100) << 8) + subtype = 0x10000 | (type << 8) | subtype
    ext_type = 0x10000 | (type_b << 8) | subtype

    lon_delta = struct.unpack_from("<h", buf, off)[0]; off += 2
    lat_delta = struct.unpack_from("<h", buf, off)[0]; off += 2

    # Bitstream length: byte 0 LSB=1 → 1-byte; LSB=0 → 2-byte
    b0 = buf[off]; off += 1
    if b0 & 1:
        bstream_len = (b0 >> 1) - 1
    else:
        b1 = buf[off]; off += 1
        bstream_len = ((b0 + b1 * 256) >> 2) - 1

    bstream_info = buf[off]; off += 1
    bitstream = bytes(buf[off : off + bstream_len])
    off += bstream_len

    reader = BitReader(bitstream)

    # Setup bits — order matters: lon-sign, lat-sign, then a lon-extra-bit (ext polygons only)
    long_sign = 0
    if reader.read(1) != 0:
        long_sign = +1 if reader.read(1) == 0 else -1
    lat_sign = 0
    if reader.read(1) != 0:
        lat_sign = +1 if reader.read(1) == 0 else -1
    long_extra_bit = reader.read(1)  # ext polygons only; latExtra is always 0

    long_bits = coord_bits(bstream_info & 0x0F, long_sign, long_extra_bit)
    lat_bits = coord_bits((bstream_info >> 4) & 0x0F, lat_sign, 0)

    # First vertex: subdivision center + (lon_delta, lat_delta) in this level's coord units
    cur_lon = lon_delta
    cur_lat = lat_delta

    def to_lon_deg(delta: int, extra: int) -> float:
        shift = 24 - subdiv.bits - extra
        c24 = int(subdiv.center_lon / SEMI_TO_DEG)
        return (c24 + (delta << shift if shift >= 0 else delta >> -shift)) * SEMI_TO_DEG

    def to_lat_deg(delta: int, extra: int) -> float:
        shift = 24 - subdiv.bits - extra
        c24 = int(subdiv.center_lat / SEMI_TO_DEG)
        return (c24 + (delta << shift if shift >= 0 else delta >> -shift)) * SEMI_TO_DEG

    lons = [to_lon_deg(cur_lon, 0)]
    lats = [to_lat_deg(cur_lat, 0)]

    # If extraBit is set for longitude, first delta gets shifted up to gain precision
    cur_lon <<= long_extra_bit

    # Decode vertex deltas until bitstream exhausted
    while reader.has_next(long_bits + lat_bits):
        d_lon = read_coord_offset(reader, long_bits, long_sign, long_extra_bit)
        d_lat = read_coord_offset(reader, lat_bits, lat_sign, 0)
        cur_lon += d_lon
        cur_lat += d_lat
        lons.append(to_lon_deg(cur_lon, long_extra_bit))
        lats.append(to_lat_deg(cur_lat, 0))

    label_off = 0
    if has_label:
        label_off = buf[off] | (buf[off + 1] << 8) | (buf[off + 2] << 16)
        off += 3
    if has_extra_byte:
        off = skip_ext_extra_bytes(buf, off)

    return Polygon(
        type=type_b, subtype=subtype, ext_type=ext_type,
        lats=lats, lons=lons, has_label=has_label, label_off=label_off,
        long_extra_bit=long_extra_bit,
    ), off


def decode_polygon(buf: memoryview, off: int, subdiv: Subdivision) -> tuple[Polygon, int]:
    """Decode one extended-type polygon record starting at `off`. Returns (polygon, new_off)."""
    poly, new_off = decode_ext_poly_record(buf, off, subdiv, consume_unk_trailer=True)
    if poly.lats and (poly.lats[0] != poly.lats[-1] or poly.lons[0] != poly.lons[-1]):
        poly.lats.append(poly.lats[0])
        poly.lons.append(poly.lons[0])
    return poly, new_off


def decode_polyline(buf: memoryview, off: int, subdiv: Subdivision) -> tuple[Polygon, int]:
    """Decode one extended-type polyline record.

    In the CourseView line section, subtype bit 6 is common and does not behave
    like the polygon trailer flag, so we deliberately do not consume it here.
    """
    return decode_ext_poly_record(buf, off, subdiv, consume_unk_trailer=False)


def decode_point(buf: memoryview, off: int, subdiv: Subdivision) -> tuple[Point, int]:
    type_b = buf[off]; off += 1
    subtype_b = buf[off]; off += 1
    has_label = bool(subtype_b & 0x20)
    has_extra_byte = bool(subtype_b & 0x80)
    subtype = subtype_b & 0x1F
    ext_type = 0x10000 | (type_b << 8) | subtype
    lon_delta = struct.unpack_from("<h", buf, off)[0]; off += 2
    lat_delta = struct.unpack_from("<h", buf, off)[0]; off += 2

    def to_lon_deg(delta: int) -> float:
        shift = 24 - subdiv.bits
        c24 = int(subdiv.center_lon / SEMI_TO_DEG)
        return (c24 + (delta << shift if shift >= 0 else delta >> -shift)) * SEMI_TO_DEG

    def to_lat_deg(delta: int) -> float:
        shift = 24 - subdiv.bits
        c24 = int(subdiv.center_lat / SEMI_TO_DEG)
        return (c24 + (delta << shift if shift >= 0 else delta >> -shift)) * SEMI_TO_DEG

    label_off = 0
    if has_label:
        label_off = buf[off] | (buf[off + 1] << 8) | (buf[off + 2] << 16)
        off += 3
    if has_extra_byte:
        off = skip_ext_extra_bytes(buf, off)

    return Point(
        type=type_b, subtype=subtype, ext_type=ext_type,
        lat=to_lat_deg(lat_delta), lon=to_lon_deg(lon_delta),
        has_label=has_label, label_off=label_off,
    ), off


def parse_polygons(gmp: bytes, rgn: RgnHeader, tre: TreData) -> list[Polygon]:
    """Decode every polygon in every subdivision, anchored to that subdivision's center."""
    buf = memoryview(gmp)
    base = rgn.ext_poly_off
    polys: list[Polygon] = []
    ogs = tre.object_groups
    for i, og in enumerate(ogs[:-1]):
        # Span for detailed subdivision i: [og.poly_off, next_og.poly_off)
        next_off = ogs[i + 1].poly_off
        span_start = base + og.poly_off
        span_end = base + next_off
        subdiv_index = tre.ext_first_subdiv_index + i
        if span_end <= span_start or subdiv_index >= len(tre.subdivisions):
            continue
        subdiv = tre.subdivisions[subdiv_index]
        off = span_start
        while off < span_end:
            try:
                poly, off = decode_polygon(buf, off, subdiv)
                if not tre.ext_area_types or poly.ext_type in tre.ext_area_types:
                    polys.append(poly)
            except Exception as e:
                # Decoder went off the rails — bail this subdivision rather than corrupt
                print(f"  [warn] subdiv {subdiv_index} parse aborted at offset 0x{off:x}: {e}")
                break
    return polys


def parse_polylines(gmp: bytes, rgn: RgnHeader, tre: TreData) -> list[Polygon]:
    """Decode every extended polyline in every subdivision."""
    buf = memoryview(gmp)
    base = rgn.ext_line_off
    lines: list[Polygon] = []
    ogs = tre.object_groups
    for i, og in enumerate(ogs[:-1]):
        next_off = ogs[i + 1].polyl_off
        span_start = base + og.polyl_off
        span_end = base + next_off
        subdiv_index = tre.ext_first_subdiv_index + i
        if span_end <= span_start or subdiv_index >= len(tre.subdivisions):
            continue
        subdiv = tre.subdivisions[subdiv_index]
        off = span_start
        while off < span_end:
            try:
                line, off = decode_polyline(buf, off, subdiv)
                if not tre.ext_line_types or line.ext_type in tre.ext_line_types:
                    lines.append(line)
            except Exception as e:
                print(f"  [warn] subdiv {subdiv_index} polyline parse aborted at offset 0x{off:x}: {e}")
                break
    return lines


def parse_points(gmp: bytes, rgn: RgnHeader, tre: TreData) -> list[Point]:
    """Decode every extended point in every subdivision."""
    buf = memoryview(gmp)
    base = rgn.ext_point_off
    points: list[Point] = []
    ogs = tre.object_groups
    for i, og in enumerate(ogs[:-1]):
        next_off = ogs[i + 1].point_off
        span_start = base + og.point_off
        span_end = base + next_off
        subdiv_index = tre.ext_first_subdiv_index + i
        if span_end <= span_start or subdiv_index >= len(tre.subdivisions):
            continue
        subdiv = tre.subdivisions[subdiv_index]
        off = span_start
        while off < span_end:
            try:
                point, off = decode_point(buf, off, subdiv)
                if not tre.ext_point_types or point.ext_type in tre.ext_point_types:
                    points.append(point)
            except Exception as e:
                print(f"  [warn] subdiv {subdiv_index} point parse aborted at offset 0x{off:x}: {e}")
                break
    return points


# ----------------------------------------------------------------------
# CLI / smoke test
# ----------------------------------------------------------------------

def _read_varint(buf: bytes, i: int) -> tuple[int, int]:
    n = s = 0
    while True:
        b = buf[i]
        i += 1
        n |= (b & 0x7F) << s
        if not (b & 0x80):
            return n, i
        s += 7


def _unwrap_pb_img(pb: bytes) -> bytes:
    """coursedata.pb wraps the .img bytes in field 3 of an outer protobuf message."""
    i = 0
    while i < len(pb):
        tag, i = _read_varint(pb, i)
        fn, wt = tag >> 3, tag & 7
        if wt == 0:
            _, i = _read_varint(pb, i)
        elif wt == 2:
            L, i = _read_varint(pb, i)
            if fn == 3:
                return pb[i : i + L]
            i += L
        else:
            raise ValueError(f"unexpected wire type {wt}")
    raise ValueError("no field-3 IMG bytes found in protobuf")


def parse_img(path: Path) -> tuple[TreData, list[Polygon]]:
    """Accept either a raw .img file or a .pb wrapper (as returned by fetch_courseview.py).
    If the file extension is .pb (or content lacks IMG magic at expected offset), unwrap first."""
    raw = path.read_bytes()
    # IMG files have 'DSKIMG' magic at offset 0x10; protobuf-wrapped IMG has the magic
    # several bytes in, after the outer-protobuf header
    if raw[0x10:0x16] != b"DSKIMG":
        # Auto-detect: try unwrapping
        try:
            raw = _unwrap_pb_img(raw)
        except Exception:
            pass
    img = raw
    gmp = extract_gmp(img)
    offsets = parse_gmp_header(gmp)
    tre = parse_tre(gmp, offsets.tre)
    rgn = parse_rgn_header(gmp, offsets.rgn)
    polys = parse_polygons(gmp, rgn, tre)
    return tre, polys


def parse_img_all(path: Path) -> tuple[TreData, list[Polygon], list[Polygon], list[Point]]:
    """Accept either a raw .img file or a .pb wrapper and return all decoded extended geometry."""
    raw = path.read_bytes()
    if raw[0x10:0x16] != b"DSKIMG":
        try:
            raw = _unwrap_pb_img(raw)
        except Exception:
            pass
    gmp = extract_gmp(raw)
    offsets = parse_gmp_header(gmp)
    tre = parse_tre(gmp, offsets.tre)
    rgn = parse_rgn_header(gmp, offsets.rgn)
    return tre, parse_polygons(gmp, rgn, tre), parse_polylines(gmp, rgn, tre), parse_points(gmp, rgn, tre)


def smoke(path: Path) -> None:
    tre, polys = parse_img(path)
    print(f"=== {path.name} ===")
    b = tre.bbox
    print(f"Bbox: ({b.south:.5f}, {b.west:.5f}) → ({b.north:.5f}, {b.east:.5f})")
    print(f"Subdivisions: {len(tre.subdivisions)}  ObjectGroups: {len(tre.object_groups)}")
    print(f"\nDecoded {len(polys)} polygons")
    _, _polys, lines, points = parse_img_all(path)
    print(f"Decoded {len(lines)} polylines")
    print(f"Decoded {len(points)} points")

    # Frequency of ext_type codes — these will need to be mapped to fairway/green/etc visually
    from collections import Counter
    types = Counter(p.ext_type for p in polys)
    print(f"\nType-code histogram (ext_type: count, mean_vertices):")
    for et, n in types.most_common():
        avg_v = sum(len(p.lats) for p in polys if p.ext_type == et) / n
        print(f"  0x{et:06x}  n={n:>3}  avg_vertices={avg_v:.1f}")

    # Sanity: vertex coords should fall within the course bbox
    out_of_bbox = 0
    for p in polys:
        for la, lo in zip(p.lats, p.lons):
            if not (b.south - 0.001 <= la <= b.north + 0.001 and b.west - 0.001 <= lo <= b.east + 0.001):
                out_of_bbox += 1
                break
    print(f"\nPolygons with >=1 vertex outside bbox: {out_of_bbox} / {len(polys)}")


if __name__ == "__main__":
    import sys
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/courseview/31795.img")
    smoke(target)
