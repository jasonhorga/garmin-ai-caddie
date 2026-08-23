import struct
import unittest

from tools.courseview.parse_courseview import (
    DEM_UNIT_TO_DEG,
    DemData,
    DemLevel,
    DemTileDescriptor,
    _skip_courseview_line_trailer,
    _skip_courseview_polygon_trailer,
    decode_dem_level,
    decode_dem_tile,
    extract_gmp,
    parse_dem_header,
    parse_lbl_header,
)


MKG_ORACLE_STREAM = bytes.fromhex(
    "6ae5d4b895a4b4969514ad25a4b44b4ad25a48d25a5692c125a4b4b695a4b4"
    "969514ad25a4b44b4ad25b80"
)


class CourseViewImgContainerTests(unittest.TestCase):
    def test_resolves_absolute_courseview_lbl_text_with_declared_code_page(self) -> None:
        gmp = bytearray(260)
        lbl = 10
        label_start = 220
        struct.pack_into("<H", gmp, lbl, 196)
        gmp[lbl + 2 : lbl + 12] = b"GARMIN LBL"
        struct.pack_into("<II", gmp, lbl + 0x15, label_start, 6)
        gmp[lbl + 0x1D] = 0
        gmp[lbl + 0x1E] = 9
        struct.pack_into("<H", gmp, lbl + 0xAA, 1252)
        gmp[label_start : label_start + 7] = b"\0Caf\xe9\0\0"

        parsed = parse_lbl_header(bytes(gmp), lbl)

        self.assertEqual(parsed.text_at(bytes(gmp), 1), "Café")
        self.assertEqual(parsed.text_at(bytes(gmp), 0), "")
        with self.assertRaisesRegex(ValueError, "outside the label pool"):
            parsed.text_at(bytes(gmp), 100)

    def test_consumes_only_proven_courseview_polygon_trailers(self) -> None:
        self.assertEqual(
            _skip_courseview_polygon_trailer(memoryview(b"\x02\x02\x03\x11"), 0),
            4,
        )
        self.assertEqual(
            _skip_courseview_polygon_trailer(
                memoryview(b"x\x02\x02\x07\x11\xaa\xbb"), 1
            ),
            7,
        )
        self.assertEqual(
            _skip_courseview_polygon_trailer(
                memoryview(b"\x02\x02\x0d\x11\xaa\xbb\xcc\xdd\xee"), 0
            ),
            9,
        )
        with self.assertRaisesRegex(ValueError, "unsupported length code"):
            _skip_courseview_polygon_trailer(memoryview(b"\x02\x02\x04\x11"), 0)
        self.assertEqual(
            _skip_courseview_line_trailer(memoryview(b"\x41\x03\x05"), 0),
            3,
        )
        self.assertEqual(
            _skip_courseview_line_trailer(memoryview(b"x\x41\x05\xc5\x00"), 1),
            5,
        )

    def test_extracts_gmp_continuation_fat_records_in_part_order(self) -> None:
        block_size = 512
        img = bytearray(24 * block_size)

        # The first FAT row describes the FAT itself, which spans rows at
        # 0x1000, 0x1200 and 0x1400.
        img[0x1000] = 1
        struct.pack_into("<I", img, 0x1000 + 12, 0x1600)

        def fat_row(offset: int, part: int, size: int, pointers: list[int]) -> None:
            img[offset] = 1
            img[offset + 1 : offset + 9] = b"TESTMAP "
            img[offset + 9 : offset + 12] = b"GMP"
            struct.pack_into("<I", img, offset + 12, size)
            img[offset + 0x11] = part
            struct.pack_into("<240H", img, offset + 0x20, *(pointers + [0xFFFF] * (240 - len(pointers))))

        fat_row(0x1200, part=0, size=1_200, pointers=[20, 22])
        fat_row(0x1400, part=1, size=0, pointers=[21])
        img[20 * block_size : 21 * block_size] = b"A" * block_size
        img[22 * block_size : 23 * block_size] = b"B" * block_size
        img[21 * block_size : 22 * block_size] = b"C" * block_size

        self.assertEqual(extract_gmp(bytes(img)), (b"A" * 512 + b"B" * 512 + b"C" * 176))

    def test_parses_dem_grid_resolution_without_decoding_tile_heights(self) -> None:
        gmp = bytearray(220)
        dem_offset = 16
        struct.pack_into("<H", gmp, dem_offset, 41)
        gmp[dem_offset + 2 : dem_offset + 12] = b"GARMIN DEM"
        struct.pack_into("<IHIHII", gmp, dem_offset + 21, 1, 1, 0, 64, 140, 4)

        level = 140
        gmp[level + 1] = 0
        struct.pack_into("<I", gmp, level + 0x02, 64)
        struct.pack_into("<I", gmp, level + 0x06, 64)
        struct.pack_into("<I", gmp, level + 0x0A, 62)  # actual final height = 63
        struct.pack_into("<I", gmp, level + 0x0E, 33)  # actual final width = 34
        struct.pack_into("<I", gmp, level + 0x14, 4)   # actual tiles wide = 5
        struct.pack_into("<I", gmp, level + 0x18, 2)   # actual tiles high = 3
        struct.pack_into("<H", gmp, level + 0x1E, 4)
        struct.pack_into("<I", gmp, level + 0x20, 60)
        struct.pack_into("<I", gmp, level + 0x24, 120)  # 5 * 3 * 4 descriptor bytes
        struct.pack_into("<i", gmp, level + 0x28, -1_455_327_024)
        struct.pack_into("<i", gmp, level + 0x2C, 436_519_392)
        struct.pack_into("<I", gmp, level + 0x30, 1_104)
        struct.pack_into("<I", gmp, level + 0x34, 1_104)
        struct.pack_into("<hh", gmp, level + 0x38, 0, 282)

        dem = parse_dem_header(bytes(gmp), dem_offset)
        parsed = dem.levels[0]
        self.assertEqual(dem.elevation_unit, "feet")
        self.assertEqual((parsed.columns, parsed.rows), (290, 191))
        self.assertAlmostEqual(parsed.latitude_spacing_degrees, 1_104 * DEM_UNIT_TO_DEG)
        self.assertEqual((parsed.min_elevation, parsed.max_elevation), (0, 282))

    def test_decodes_public_garmin_dem_reference_bitstream(self) -> None:
        # Frank Stinner's DEM-Daten.pdf reference: a 64x64 tile of zeroes with
        # only the lower-left sample set to 3. mkgmap independently reproduces
        # this exact 12-byte stream in DemTileTest.testKnownBitstream.
        descriptor = DemTileDescriptor(
            column=0,
            row=0,
            width=64,
            height=64,
            data_offset=0,
            base_elevation=90,
            max_delta=3,
            encoding_type=0,
        )
        decoded = decode_dem_tile(
            bytes.fromhex("ff ff ff ff ff ff ff ff ff ff c0 2e"),
            descriptor,
        )

        self.assertEqual(len(decoded.normalized_heights), 64 * 64)
        self.assertEqual(decoded.normalized_heights[63 * 64], 3)
        self.assertEqual(sum(decoded.normalized_heights), 3)
        self.assertEqual(decoded.elevations[63 * 64], 93)
        self.assertEqual(decoded.elevations[0], 90)
        self.assertLess(decoded.padding_bits, 8)

    def test_decodes_independent_mkgmap_oracle_stream(self) -> None:
        # Generated on the homeserver by the unmodified mkgmap r4924 DEMTile
        # encoder from the deterministic matrix below. This crosses the 64-value
        # adaptive-state boundary and exercises standard, plateau and follower
        # codes without sharing implementation code with this decoder.
        width, height = 17, 9
        expected = tuple(
            row * 2
            + column // 3
            + (1 if (column + row * 2) % 5 == 0 else 0)
            for row in range(height)
            for column in range(width)
        )
        descriptor = DemTileDescriptor(
            column=0,
            row=0,
            width=width,
            height=height,
            data_offset=0,
            base_elevation=0,
            max_delta=21,
            encoding_type=0,
        )
        decoded = decode_dem_tile(MKG_ORACLE_STREAM, descriptor)

        self.assertEqual(decoded.normalized_heights, expected)
        self.assertEqual(decoded.consumed_bits, 337)
        self.assertEqual(decoded.padding_bits, 7)

    def test_decodes_descriptor_stream_into_grid_and_samples_boundaries(self) -> None:
        descriptor = bytes((0, 0, 21))
        gmp = descriptor + MKG_ORACLE_STREAM
        level = DemLevel(
            unknown_byte=0,
            zoom_level=0,
            points_per_lat=64,
            points_per_lon=64,
            non_standard_height=9,
            non_standard_width=17,
            shrink_value=0,
            tiles_lat=1,
            tiles_lon=1,
            record_descriptor=0,
            tile_descriptor_size=3,
            tile_descriptor_offset=0,
            tile_data_offset=len(descriptor),
            left=1_000_000,
            top=2_000_000,
            point_distance_lat=1_000,
            point_distance_lon=1_000,
            min_elevation=0,
            max_elevation=21,
        )
        decoded = decode_dem_level(
            gmp,
            DemData("metres", 60, len(gmp), [level]),
        )
        expected = tuple(
            tuple(
                row * 2
                + column // 3
                + (1 if (column + row * 2) % 5 == 0 else 0)
                for column in range(17)
            )
            for row in range(9)
        )

        self.assertEqual(decoded.elevations, expected)
        west = level.left * DEM_UNIT_TO_DEG
        north = level.top * DEM_UNIT_TO_DEG
        east = west + (level.columns - 1) * level.longitude_spacing_degrees
        south = north - (level.rows - 1) * level.latitude_spacing_degrees
        self.assertEqual(decoded.elevation_at(north, west), expected[0][0])
        self.assertEqual(decoded.elevation_at(south, east), expected[-1][-1])
        self.assertAlmostEqual(
            decoded.elevation_at(
                north - 0.5 * level.latitude_spacing_degrees,
                west + 0.5 * level.longitude_spacing_degrees,
            ),
            sum((expected[0][0], expected[0][1], expected[1][0], expected[1][1]))
            / 4,
        )
        self.assertIsNone(
            decoded.elevation_at(north, west - level.longitude_spacing_degrees)
        )

    def test_rejects_malformed_tile_offsets_and_overlong_streams(self) -> None:
        level = DemLevel(
            unknown_byte=0,
            zoom_level=0,
            points_per_lat=1,
            points_per_lon=1,
            non_standard_height=1,
            non_standard_width=1,
            shrink_value=0,
            tiles_lat=1,
            tiles_lon=2,
            record_descriptor=0,
            tile_descriptor_size=3,
            tile_descriptor_offset=0,
            tile_data_offset=6,
            left=0,
            top=0,
            point_distance_lat=1,
            point_distance_lon=1,
            min_elevation=0,
            max_elevation=1,
        )
        repeated_offsets = bytes((0, 0, 1, 0, 0, 1, 0xFF))
        with self.assertRaisesRegex(ValueError, "offsets are not strictly increasing"):
            decode_dem_level(
                repeated_offsets,
                DemData("metres", 60, len(repeated_offsets), [level]),
            )

        descriptor = DemTileDescriptor(0, 0, 17, 9, 0, 0, 21, 0)
        with self.assertRaisesRegex(ValueError, "non-padding bits"):
            decode_dem_tile(MKG_ORACLE_STREAM + b"\x00", descriptor)


if __name__ == "__main__":
    unittest.main()
