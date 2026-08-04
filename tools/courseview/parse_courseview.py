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
DEM_UNIT_TO_DEG = 45 / (1 << 29)


# ----------------------------------------------------------------------
# Layer 1: IMG → GMP
# ----------------------------------------------------------------------

def extract_gmp(img: bytes) -> bytes:
    """Pull the complete .GMP subfile out of an IMG container by walking its FAT.

    A FAT record holds at most 240 block pointers (120 KiB with the CourseView
    block size). Larger maps repeat the same 8.3 name in continuation records;
    byte ``0x11`` is their part number. The old parser read only the first
    record and therefore silently cut the DEM off large course packages.
    """
    BS = 512
    FAT_ENTRY_SIZE = 512
    FAT_FIRST_ENTRY = 0x1000

    if len(img) < FAT_FIRST_ENTRY + FAT_ENTRY_SIZE:
        raise ValueError("IMG is too small to contain a FAT")
    fat_size = struct.unpack_from("<I", img, FAT_FIRST_ENTRY + 12)[0]
    if fat_size < FAT_FIRST_ENTRY + FAT_ENTRY_SIZE or fat_size > len(img):
        raise ValueError("IMG FAT size is outside the container")

    entries: list[bytes] = []
    for off in range(FAT_FIRST_ENTRY, fat_size, FAT_ENTRY_SIZE):
        entry = img[off : off + FAT_ENTRY_SIZE]
        if len(entry) != FAT_ENTRY_SIZE or entry[0] != 1:
            continue
        entries.append(entry)

    primary = next(
        (entry for entry in entries if entry[9:12] == b"GMP" and entry[0x11] == 0),
        None,
    )
    if primary is None:
        raise ValueError("IMG FAT has no primary GMP entry")

    name = primary[1:9]
    size = struct.unpack_from("<I", primary, 12)[0]
    parts: dict[int, bytes] = {}
    for entry in entries:
        if entry[1:9] != name or entry[9:12] != b"GMP":
            continue
        part_no = entry[0x11]
        if part_no in parts:
            raise ValueError(f"IMG FAT repeats GMP part {part_no}")
        parts[part_no] = entry
    if sorted(parts) != list(range(max(parts) + 1)):
        raise ValueError("IMG FAT GMP continuation parts are not contiguous")

    chunks: list[bytes] = []
    for part_no in sorted(parts):
        ptrs = struct.unpack_from("<240H", parts[part_no], 0x20)
        for pointer in ptrs:
            if pointer == 0xFFFF:
                break
            start = pointer * BS
            end = start + BS
            if end > len(img):
                raise ValueError(f"IMG FAT GMP block {pointer} is outside the container")
            chunks.append(img[start:end])
    gmp = b"".join(chunks)
    if len(gmp) < size:
        raise ValueError(f"IMG FAT supplies only {len(gmp)} of {size} GMP bytes")
    return gmp[:size]


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


@dataclass
class DemLevel:
    unknown_byte: int
    zoom_level: int
    points_per_lat: int
    points_per_lon: int
    non_standard_height: int
    non_standard_width: int
    shrink_value: int
    tiles_lat: int
    tiles_lon: int
    record_descriptor: int
    tile_descriptor_size: int
    tile_descriptor_offset: int
    tile_data_offset: int
    left: int
    top: int
    point_distance_lat: int
    point_distance_lon: int
    min_elevation: int
    max_elevation: int

    @property
    def rows(self) -> int:
        return (self.tiles_lat - 1) * self.points_per_lat + self.non_standard_height

    @property
    def columns(self) -> int:
        return (self.tiles_lon - 1) * self.points_per_lon + self.non_standard_width

    @property
    def latitude_spacing_degrees(self) -> float:
        return self.point_distance_lat * DEM_UNIT_TO_DEG

    @property
    def longitude_spacing_degrees(self) -> float:
        return self.point_distance_lon * DEM_UNIT_TO_DEG

    @property
    def shrink_factor(self) -> int:
        """Return the odd multiplier represented by the DEM shrink field."""
        return 2 * self.shrink_value + 1


@dataclass
class DemData:
    elevation_unit: str
    section_record_size: int
    section_header_offset: int
    levels: list[DemLevel]


def parse_dem_header(gmp: bytes, dem_off: int) -> DemData:
    """Decode the CourseView DEM header and level geometry.

    CourseView's embedded subfile offsets are absolute within the GMP. Compressed
    samples are decoded separately by :func:`decode_dem_level`.
    """
    if dem_off < 0 or dem_off + 41 > len(gmp):
        raise ValueError("DEM header is outside the GMP")
    header_len = struct.unpack_from("<H", gmp, dem_off)[0]
    file_type = gmp[dem_off + 2 : dem_off + 12].rstrip(b"\0")
    if header_len < 41 or file_type != b"GARMIN DEM":
        raise ValueError("invalid Garmin DEM common header")

    elevation_code, level_count, _unknown, record_size, header_offset, _unknown2 = struct.unpack_from(
        "<IHIHII", gmp, dem_off + 21
    )
    if record_size < 60 or header_offset < dem_off or header_offset > len(gmp):
        raise ValueError("invalid Garmin DEM section table")
    if header_offset + level_count * record_size > len(gmp):
        raise ValueError("Garmin DEM section table is truncated")

    levels: list[DemLevel] = []
    for index in range(level_count):
        off = header_offset + index * record_size
        level = DemLevel(
            unknown_byte=gmp[off],
            zoom_level=gmp[off + 1],
            points_per_lat=struct.unpack_from("<I", gmp, off + 0x02)[0],
            points_per_lon=struct.unpack_from("<I", gmp, off + 0x06)[0],
            non_standard_height=struct.unpack_from("<I", gmp, off + 0x0A)[0] + 1,
            non_standard_width=struct.unpack_from("<I", gmp, off + 0x0E)[0] + 1,
            shrink_value=struct.unpack_from("<H", gmp, off + 0x12)[0],
            tiles_lon=struct.unpack_from("<I", gmp, off + 0x14)[0] + 1,
            tiles_lat=struct.unpack_from("<I", gmp, off + 0x18)[0] + 1,
            record_descriptor=struct.unpack_from("<H", gmp, off + 0x1C)[0],
            tile_descriptor_size=struct.unpack_from("<H", gmp, off + 0x1E)[0],
            tile_descriptor_offset=struct.unpack_from("<I", gmp, off + 0x20)[0],
            tile_data_offset=struct.unpack_from("<I", gmp, off + 0x24)[0],
            left=struct.unpack_from("<i", gmp, off + 0x28)[0],
            top=struct.unpack_from("<i", gmp, off + 0x2C)[0],
            point_distance_lat=struct.unpack_from("<I", gmp, off + 0x30)[0],
            point_distance_lon=struct.unpack_from("<I", gmp, off + 0x34)[0],
            min_elevation=struct.unpack_from("<h", gmp, off + 0x38)[0],
            max_elevation=struct.unpack_from("<h", gmp, off + 0x3A)[0],
        )
        descriptor_bytes = level.tile_data_offset - level.tile_descriptor_offset
        expected_descriptor_bytes = level.tiles_lat * level.tiles_lon * level.tile_descriptor_size
        if descriptor_bytes != expected_descriptor_bytes:
            raise ValueError("Garmin DEM tile descriptor span does not match its grid")
        levels.append(level)
    elevation_unit = "feet" if elevation_code == 1 else "metres" if elevation_code == 0 else f"code-{elevation_code}"
    return DemData(elevation_unit, record_size, header_offset, levels)


@dataclass(frozen=True)
class DemTileDescriptor:
    column: int
    row: int
    width: int
    height: int
    data_offset: int
    base_elevation: int
    max_delta: int
    encoding_type: int


@dataclass(frozen=True)
class DecodedDemTile:
    descriptor: DemTileDescriptor
    normalized_heights: tuple[int, ...]
    elevations: tuple[int | None, ...]
    consumed_bits: int
    padding_bits: int


@dataclass(frozen=True)
class DecodedDemLevel:
    level: DemLevel
    tiles: tuple[DecodedDemTile, ...]
    elevations: tuple[tuple[int | None, ...], ...]

    def elevation_at(self, latitude: float, longitude: float) -> float | None:
        """Bilinearly sample the decoded grid in its native feet/metres unit."""
        column = (
            longitude - self.level.left * DEM_UNIT_TO_DEG
        ) / self.level.longitude_spacing_degrees
        row = (
            self.level.top * DEM_UNIT_TO_DEG - latitude
        ) / self.level.latitude_spacing_degrees
        if not (
            0.0 <= column <= self.level.columns - 1
            and 0.0 <= row <= self.level.rows - 1
        ):
            return None
        left = min(int(column), self.level.columns - 2)
        top = min(int(row), self.level.rows - 2)
        horizontal = column - left
        vertical = row - top
        values = (
            self.elevations[top][left],
            self.elevations[top][left + 1],
            self.elevations[top + 1][left],
            self.elevations[top + 1][left + 1],
        )
        if any(value is None for value in values):
            return None
        north_west, north_east, south_west, south_east = values
        assert north_west is not None
        assert north_east is not None
        assert south_west is not None
        assert south_east is not None
        return (
            north_west * (1 - horizontal) * (1 - vertical)
            + north_east * horizontal * (1 - vertical)
            + south_west * (1 - horizontal) * vertical
            + south_east * horizontal * vertical
        )


class _DemBitReader:
    """MSB-first reader for the Garmin DEM sample stream."""

    def __init__(self, data: bytes):
        self.data = data
        self.bit_pos = 0

    @property
    def remaining(self) -> int:
        return len(self.data) * 8 - self.bit_pos

    def bit(self) -> int:
        if self.bit_pos >= len(self.data) * 8:
            raise ValueError("Garmin DEM sample stream is truncated")
        value = (self.data[self.bit_pos // 8] >> (7 - self.bit_pos % 8)) & 1
        self.bit_pos += 1
        return value

    def unsigned(self, count: int) -> int:
        value = 0
        for _ in range(count):
            value = (value << 1) | self.bit()
        return value

    def zero_run(self, maximum: int) -> int:
        count = 0
        while self.bit() == 0:
            count += 1
            if count > maximum:
                raise ValueError("Garmin DEM code has an overlong zero run")
        return count


_DEM_PLATEAU_UNITS = (
    1, 1, 1, 1, 2, 2, 2, 2, 4, 4, 4, 4, 8, 8, 8, 8,
    16, 16, 32, 32, 64, 64, 128,
)
_DEM_PLATEAU_BINARY_BITS = (
    0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4,
    4, 5, 5, 6, 6, 7, 8,
)


def _java_div(numerator: int, denominator: int) -> int:
    """Integer division toward zero, matching the documented Garmin state machine."""
    if denominator <= 0:
        raise ValueError("denominator must be positive")
    quotient = abs(numerator) // denominator
    return -quotient if numerator < 0 else quotient


def _dem_max_zero_bits(max_delta: int) -> int:
    bounds = (
        (2, 15), (4, 16), (8, 17), (16, 18), (32, 19),
        (64, 20), (128, 21), (256, 22), (512, 25),
        (1024, 28), (2048, 31), (4096, 34), (8192, 37),
        (16384, 40),
    )
    for upper, bits in bounds:
        if max_delta < upper:
            return bits
    return 43


def _dem_start_hunit(max_delta: int) -> int:
    for upper, unit in (
        (0x9F, 1), (0x11F, 2), (0x21F, 4), (0x41F, 8),
        (0x81F, 16), (0x101F, 32), (0x201F, 64), (0x401F, 128),
    ):
        if max_delta < upper:
            return unit
    return 256


def _dem_big_binary_bits(max_delta: int) -> int:
    return max(1, max_delta.bit_length()) if max_delta < 16384 else 15


def _dem_evaluate(old_sum: int, count: int, value: int, region: int) -> int:
    if region == 0:
        return -1 - old_sum - count
    if region == 1:
        return 2 * (value + count) + 3
    if region == 2:
        return 2 * value - 1
    if region == 3:
        return 2 * (value - count) - 5
    return 1 - old_sum + count


def _dem_evaluate_region(old_sum: int, count: int, value: int) -> int:
    if value < -2 - ((old_sum + 3 * count) >> 1):
        return 0
    boundary = -((old_sum + count) >> 1) - (1 if count >= 63 else 0)
    if value < boundary:
        return 1
    if value < 2 - ((old_sum - count) >> 1):
        return 2
    if value < 4 - ((old_sum - 3 * count) >> 1):
        return 3
    return 4


class _DemValuePredictor:
    """Adaptive value-code state defined by the public Garmin DEM format research."""

    STANDARD = "standard"
    PLATEAU_ZERO = "plateau-zero"
    PLATEAU_NON_ZERO = "plateau-non-zero"

    HYBRID = "hybrid"
    LENGTH = "length"

    def __init__(self, kind: str, max_delta: int):
        self.kind = kind
        self.max_delta = max_delta
        self.max_zero_bits = _dem_max_zero_bits(max_delta) - (kind != self.STANDARD)
        self.unit_delta = max(0, max_delta - 0x5F) // 0x40
        self.encoding = self.HYBRID
        self.wrap_type = 0
        self.sum_h = 0
        self.sum_l = 0
        self.element_count = 0
        self.hunit = _dem_start_hunit(max_delta)
        self.diagonal_difference = 0

        if max_delta % 2 == 0:
            self.length_wrap_down = (
                max_delta // 2, (max_delta + 2) // 2, max_delta // 2,
            )
            self.length_wrap_up = (
                -max_delta // 2, -max_delta // 2, -max_delta // 2,
            )
        else:
            self.length_wrap_down = (
                (max_delta + 1) // 2,
                (max_delta + 1) // 2,
                (max_delta - 1) // 2,
            )
            self.length_wrap_up = (
                -(max_delta - 1) // 2,
                -(max_delta - 1) // 2,
                -(max_delta + 1) // 2,
            )
        self.hybrid_wrap_down = (max_delta + 1) // 2
        self.hybrid_wrap_up = -(max_delta - 1) // 2

    def wrap(self, value: int) -> int:
        if self.encoding == self.HYBRID:
            lower = self.hybrid_wrap_up
            upper = self.hybrid_wrap_down
        else:
            lower = self.length_wrap_up[self.wrap_type]
            upper = self.length_wrap_down[self.wrap_type]
        if value > upper:
            value -= self.max_delta + 1
        if value < lower:
            value += self.max_delta + 1
        return value

    def current_max_zero_bits(self, plateau_table_position: int) -> int:
        if self.kind == self.STANDARD:
            return self.max_zero_bits
        if not 0 <= plateau_table_position < len(_DEM_PLATEAU_BINARY_BITS):
            raise ValueError("Garmin DEM plateau table position is outside the format table")
        return self.max_zero_bits - _DEM_PLATEAU_BINARY_BITS[plateau_table_position]

    @staticmethod
    def _normal_hunit(value: int) -> int:
        return 1 << (value.bit_length() - 1) if value > 0 else 0

    def process(self, delta: int) -> None:
        if self.kind == self.STANDARD:
            self.sum_h += abs(delta)
            if self.sum_h + self.unit_delta + 1 >= 0xFFFF:
                self.sum_h -= 0x10000

            work = delta
            region = -1
            if self.element_count == 63:
                region = _dem_evaluate_region(self.sum_l, self.element_count, delta)
                even_delta = delta % 2 == 0
                sum_minus_one_multiple_of_four = (self.sum_l - 1) % 4 == 0
                if region in (0, 2, 4):
                    if sum_minus_one_multiple_of_four != even_delta:
                        work += 1
                elif region == 1:
                    work += 1
                    if sum_minus_one_multiple_of_four != even_delta:
                        work += 1
                elif region == 3:
                    if sum_minus_one_multiple_of_four == even_delta:
                        work -= 1
            if region < 0:
                region = _dem_evaluate_region(self.sum_l, self.element_count, work)
            self.sum_l += _dem_evaluate(
                self.sum_l, self.element_count, work, region
            )
            self.element_count += 1
            if self.element_count == 64:
                self.element_count = 32
                self.sum_h = ((self.sum_h - self.unit_delta) >> 1) - 1
                self.sum_l = _java_div(self.sum_l, 2)
            self.hunit = self._normal_hunit(
                _java_div(
                    self.unit_delta + self.sum_h + 1,
                    self.element_count + 1,
                )
            )
            self.wrap_type = 0
            if self.hunit > 0:
                self.encoding = self.HYBRID
            else:
                self.encoding = self.LENGTH
                if self.sum_l > 0:
                    self.wrap_type = 1
            return

        if self.kind == self.PLATEAU_ZERO:
            self.sum_h += delta if delta > 0 else 1 - delta
        else:
            self.sum_h += abs(delta)
        if self.sum_h + self.unit_delta + 1 >= 0xFFFF:
            self.sum_h -= 0x10000
        self.sum_l += -1 if delta <= 0 else 1
        self.element_count += 1
        if self.element_count == 64:
            self.element_count = 32
            self.sum_h = ((self.sum_h - self.unit_delta) >> 1) - 1
            self.sum_l = _java_div(self.sum_l, 2)
            if self.sum_l % 2 != 0:
                self.sum_l += 1 if self.kind == self.PLATEAU_ZERO else -1

        numerator = self.unit_delta + self.sum_h + 1
        if self.kind == self.PLATEAU_ZERO:
            numerator -= self.element_count // 2
        self.hunit = self._normal_hunit(
            _java_div(numerator, self.element_count + 1)
        )
        self.wrap_type = 0
        if self.hunit > 0:
            self.encoding = self.HYBRID
        else:
            self.encoding = self.LENGTH
            if self.kind == self.PLATEAU_ZERO and self.sum_l >= 0:
                self.wrap_type = 1
            elif self.kind == self.PLATEAU_NON_ZERO and self.sum_l <= 0:
                self.wrap_type = 2


def _decode_dem_coded_value(
    reader: _DemBitReader,
    predictor: _DemValuePredictor,
    plateau_table_position: int,
) -> int:
    maximum = predictor.current_max_zero_bits(plateau_table_position)
    zeroes = reader.zero_run(maximum + 1)
    if zeroes <= maximum:
        if predictor.encoding == predictor.HYBRID:
            if predictor.hunit <= 0 or predictor.hunit & (predictor.hunit - 1):
                raise ValueError("Garmin DEM hybrid hunit is invalid")
            binary_bits = predictor.hunit.bit_length() - 1
            binary = reader.unsigned(binary_bits)
            positive = reader.bit() == 1
            return zeroes * predictor.hunit + binary + 1 if positive else -(
                zeroes * predictor.hunit + binary
            )
        if zeroes % 2:
            return (zeroes + 1) // 2
        return -(zeroes // 2)

    magnitude = reader.unsigned(_dem_big_binary_bits(predictor.max_delta) - 1)
    non_positive = reader.bit() == 1
    return -(magnitude + 1) if non_positive else magnitude + 1


def _decode_dem_plateau_length(
    reader: _DemBitReader,
    table_position: int,
    column: int,
    width: int,
) -> tuple[int, int]:
    length = 0
    cursor = column
    while True:
        if table_position >= len(_DEM_PLATEAU_UNITS):
            raise ValueError("Garmin DEM plateau length exceeds the supported table")
        if reader.bit() == 0:
            if table_position > 0:
                table_position -= 1
            length += reader.unsigned(_DEM_PLATEAU_BINARY_BITS[table_position])
            if column + length >= width:
                raise ValueError("Garmin DEM terminated plateau reaches the row boundary")
            return length, table_position

        unit = _DEM_PLATEAU_UNITS[table_position]
        table_position += 1
        length += unit
        cursor += unit
        if cursor >= width:
            if cursor != width:
                table_position -= 1
            return width - column, table_position


def _dem_height_at(heights: list[int], width: int, column: int, row: int) -> int:
    if row < 0:
        return 0
    if column < 0:
        return 0 if row == 0 else heights[(row - 1) * width]
    return heights[row * width + column]


def _decode_dem_height(
    encoded_delta: int,
    predictor: _DemValuePredictor,
    *,
    upper: int,
    left: int,
    upper_left: int,
) -> tuple[int, int]:
    if predictor.wrap_type == 0:
        state_delta = encoded_delta
    elif predictor.wrap_type == 1:
        state_delta = 1 - encoded_delta
    else:
        state_delta = -encoded_delta

    if predictor.kind == predictor.PLATEAU_ZERO:
        wrapped_candidates = []
        # The public format derivation uses integer division toward zero here:
        # wrapped zero stays zero; only a negative follower is shifted by one.
        if state_delta >= 0:
            wrapped_candidates.append(state_delta)
        if state_delta <= 0:
            wrapped_candidates.append(state_delta - 1)
    elif predictor.kind == predictor.PLATEAU_NON_ZERO:
        # Garmin applies the ddiff sign before deciding whether wrapping saves
        # bits. This ordering matters at the min/max boundary (for example a
        # +2 vertical delta in a max-delta-3 tile encodes as wrapped +2).
        wrapped_candidates = [state_delta]
    else:
        wrapped_candidates = [state_delta]

    prediction = 0
    if predictor.kind == predictor.STANDARD:
        upper_difference = upper - upper_left
        if upper_difference >= predictor.max_delta - left:
            prediction = -1
        elif upper_difference <= -left:
            prediction = 0
        else:
            prediction = left + upper_difference

    candidates: set[int] = set()
    modulus = predictor.max_delta + 1
    for wrapped in wrapped_candidates:
        for raw_delta in (wrapped - modulus, wrapped, wrapped + modulus):
            if predictor.wrap(raw_delta) != wrapped:
                continue
            if predictor.kind == predictor.STANDARD:
                if predictor.diagonal_difference > 0:
                    height = prediction - raw_delta
                else:
                    height = prediction + raw_delta
            elif predictor.kind == predictor.PLATEAU_NON_ZERO:
                vertical_delta = (
                    -raw_delta
                    if predictor.diagonal_difference > 0
                    else raw_delta
                )
                height = upper + vertical_delta
            else:
                height = upper + raw_delta
            if not 0 <= height <= predictor.max_delta:
                continue
            candidates.add(height)
    # A plateau follower normally differs from the plateau. Some Garmin-authored
    # streams nevertheless emit an explicit zero follower at a row boundary; use
    # it only when the code has no non-equal interpretation.
    if (
        predictor.kind == predictor.PLATEAU_ZERO
        and upper in candidates
        and len(candidates) > 1
    ):
        candidates.remove(upper)
    if len(candidates) != 1:
        raise ValueError(
            "Garmin DEM value does not resolve to exactly one valid height "
            f"(encoded={encoded_delta}, state={state_delta}, candidates={sorted(candidates)}, "
            f"kind={predictor.kind}, coding={predictor.encoding}, wrap={predictor.wrap_type}, "
            f"ddiff={predictor.diagonal_difference}, upper={upper}, left={left}, "
            f"upperLeft={upper_left}, prediction={prediction}, max={predictor.max_delta})"
        )
    return candidates.pop(), state_delta


def _dem_is_void(normalized_height: int, max_delta: int, encoding_type: int) -> bool:
    """Apply Garmin's documented undefined-value bands without discarding raw heights."""
    if encoding_type == 0:
        return False
    undefined_bands = {
        1: 1, 2: 1, 4: 1, 8: 1,
        3: 2, 5: 2, 6: 2, 9: 2,
        7: 3,
    }
    count = undefined_bands.get(encoding_type)
    if count is None:
        raise ValueError(f"unsupported Garmin DEM encoding type {encoding_type}")
    return normalized_height > max_delta - count


def decode_dem_tile(
    bitstream: bytes,
    descriptor: DemTileDescriptor,
    *,
    shrink_factor: int = 1,
) -> DecodedDemTile:
    """Decode one Garmin DEM tile into normalized and absolute elevations.

    The implementation follows Frank Stinner's public 2018 DEM format research;
    it is checked against that document's known bitstream and an independently
    built mkgmap encoder corpus in the test suite.
    """
    if descriptor.width <= 0 or descriptor.height <= 0:
        raise ValueError("Garmin DEM tile dimensions must be positive")
    if descriptor.max_delta < 0:
        raise ValueError("Garmin DEM tile max delta must be non-negative")
    if shrink_factor <= 0 or shrink_factor % 2 == 0:
        raise ValueError("Garmin DEM shrink factor must be a positive odd number")
    if shrink_factor != 1:
        raise ValueError("non-default Garmin DEM shrink coding is not decoded yet")

    if descriptor.max_delta == 0:
        if bitstream:
            raise ValueError("flat Garmin DEM tile unexpectedly contains sample data")
        count = descriptor.width * descriptor.height
        normalized = (0,) * count
        elevations = (descriptor.base_elevation,) * count
        return DecodedDemTile(descriptor, normalized, elevations, 0, 0)

    reader = _DemBitReader(bitstream)
    heights: list[int] = []
    plateau_table_position = 0
    plateau_follower = False
    standard = _DemValuePredictor(_DemValuePredictor.STANDARD, descriptor.max_delta)
    plateau_zero = _DemValuePredictor(
        _DemValuePredictor.PLATEAU_ZERO, descriptor.max_delta
    )
    plateau_non_zero = _DemValuePredictor(
        _DemValuePredictor.PLATEAU_NON_ZERO, descriptor.max_delta
    )

    total = descriptor.width * descriptor.height
    position = 0
    while position < total:
        column = position % descriptor.width
        row = position // descriptor.width
        upper = _dem_height_at(heights, descriptor.width, column, row - 1)
        left = _dem_height_at(heights, descriptor.width, column - 1, row)
        diagonal_difference = upper - left

        if not plateau_follower and diagonal_difference == 0:
            length, plateau_table_position = _decode_dem_plateau_length(
                reader,
                plateau_table_position,
                column,
                descriptor.width,
            )
            heights.extend([left] * length)
            position += length
            plateau_follower = position % descriptor.width != 0 or length == 0
            continue

        predictor = standard
        if plateau_follower:
            predictor = plateau_zero if diagonal_difference == 0 else plateau_non_zero
            plateau_follower = False
        predictor.diagonal_difference = diagonal_difference
        encoded = _decode_dem_coded_value(reader, predictor, plateau_table_position)
        upper_left = _dem_height_at(
            heights, descriptor.width, column - 1, row - 1
        )
        try:
            height, state_delta = _decode_dem_height(
                encoded,
                predictor,
                upper=upper,
                left=left,
                upper_left=upper_left,
            )
        except ValueError as exc:
            raise ValueError(
                f"Garmin DEM tile ({descriptor.column},{descriptor.row}) sample "
                f"({column},{row}) cannot be decoded: {exc}"
            ) from exc
        heights.append(height)
        predictor.process(state_delta)
        position += 1

    if reader.remaining >= 8:
        raise ValueError(
            f"Garmin DEM tile leaves {reader.remaining} non-padding bits after decoding"
        )
    normalized = tuple(heights)
    elevations = tuple(
        None
        if _dem_is_void(height, descriptor.max_delta, descriptor.encoding_type)
        else descriptor.base_elevation + height * shrink_factor
        for height in normalized
    )
    return DecodedDemTile(
        descriptor,
        normalized,
        elevations,
        reader.bit_pos,
        reader.remaining,
    )


def decode_dem_level(gmp: bytes, dem: DemData, level_index: int = 0) -> DecodedDemLevel:
    """Decode every tile of one DEM level and assemble its north-to-south grid."""
    if not 0 <= level_index < len(dem.levels):
        raise ValueError("Garmin DEM level index is outside the header")
    level = dem.levels[level_index]
    if level.record_descriptor & ~0x1F:
        raise ValueError("Garmin DEM tile descriptor has unsupported flag bits")
    offset_size = (level.record_descriptor & 0x03) + 1
    base_size = ((level.record_descriptor & 0x04) >> 2) + 1
    delta_size = ((level.record_descriptor & 0x08) >> 3) + 1
    has_encoding_type = bool(level.record_descriptor & 0x10)
    expected_size = offset_size + base_size + delta_size + has_encoding_type
    if level.tile_descriptor_size != expected_size:
        raise ValueError("Garmin DEM tile descriptor size does not match its flags")

    level_data_end = (
        dem.levels[level_index + 1].tile_descriptor_offset
        if level_index + 1 < len(dem.levels)
        else dem.section_header_offset
    )
    if not level.tile_data_offset <= level_data_end <= len(gmp):
        raise ValueError("Garmin DEM tile data span is outside the GMP")
    data_size = level_data_end - level.tile_data_offset

    descriptors: list[DemTileDescriptor] = []
    count = level.tiles_lon * level.tiles_lat
    for index in range(count):
        start = level.tile_descriptor_offset + index * level.tile_descriptor_size
        record = gmp[start : start + level.tile_descriptor_size]
        if len(record) != level.tile_descriptor_size:
            raise ValueError("Garmin DEM tile descriptor table is truncated")
        cursor = 0
        data_offset = int.from_bytes(record[cursor : cursor + offset_size], "little")
        cursor += offset_size
        base_elevation = int.from_bytes(
            record[cursor : cursor + base_size], "little", signed=True
        )
        cursor += base_size
        max_delta = int.from_bytes(record[cursor : cursor + delta_size], "little")
        cursor += delta_size
        encoding_type = record[cursor] if has_encoding_type else 0
        row, column = divmod(index, level.tiles_lon)
        width = (
            level.non_standard_width
            if column + 1 == level.tiles_lon
            else level.points_per_lon
        )
        height = (
            level.non_standard_height
            if row + 1 == level.tiles_lat
            else level.points_per_lat
        )
        descriptors.append(
            DemTileDescriptor(
                column,
                row,
                width,
                height,
                data_offset,
                base_elevation,
                max_delta,
                encoding_type,
            )
        )

    active = [index for index, item in enumerate(descriptors) if item.max_delta > 0]
    offsets = [descriptors[index].data_offset for index in active]
    if offsets != sorted(offsets) or len(set(offsets)) != len(offsets):
        raise ValueError("Garmin DEM active tile offsets are not strictly increasing")
    if any(offset < 0 or offset >= data_size for offset in offsets):
        raise ValueError("Garmin DEM tile offset is outside its data span")

    next_active_offset: dict[int, int] = {}
    for active_position, descriptor_index in enumerate(active):
        next_active_offset[descriptor_index] = (
            descriptors[active[active_position + 1]].data_offset
            if active_position + 1 < len(active)
            else data_size
        )

    decoded_tiles: list[DecodedDemTile] = []
    grid: list[list[int | None]] = [
        [None] * level.columns for _ in range(level.rows)
    ]
    for index, descriptor in enumerate(descriptors):
        if descriptor.max_delta == 0:
            payload = b""
        else:
            end = next_active_offset[index]
            if end <= descriptor.data_offset:
                raise ValueError("Garmin DEM tile has an empty or reversed data span")
            payload = gmp[
                level.tile_data_offset + descriptor.data_offset :
                level.tile_data_offset + end
            ]
        decoded = decode_dem_tile(
            payload,
            descriptor,
            shrink_factor=level.shrink_factor,
        )
        decoded_tiles.append(decoded)
        left = descriptor.column * level.points_per_lon
        top = descriptor.row * level.points_per_lat
        for tile_row in range(descriptor.height):
            tile_start = tile_row * descriptor.width
            grid[top + tile_row][left : left + descriptor.width] = decoded.elevations[
                tile_start : tile_start + descriptor.width
            ]

    return DecodedDemLevel(
        level,
        tuple(decoded_tiles),
        tuple(tuple(row) for row in grid),
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

    raw = path.read_bytes()
    if raw[0x10:0x16] != b"DSKIMG":
        raw = _unwrap_pb_img(raw)
    gmp = extract_gmp(raw)
    dem = parse_dem_header(gmp, parse_gmp_header(gmp).dem)
    for level in dem.levels:
        print(
            f"DEM z{level.zoom_level}: {level.columns}x{level.rows} samples, "
            f"spacing={level.longitude_spacing_degrees:.8f}°x{level.latitude_spacing_degrees:.8f}°, "
            f"elevation={level.min_elevation}..{level.max_elevation} {dem.elevation_unit}"
        )


if __name__ == "__main__":
    import sys
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/courseview/31795.img")
    smoke(target)
