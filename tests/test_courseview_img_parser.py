import struct
import unittest

from tools.courseview.parse_courseview import DEM_UNIT_TO_DEG, extract_gmp, parse_dem_header


class CourseViewImgContainerTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
