from unittest.mock import patch
import unittest

from ai_caddie.geometry import inspect_courseview_release as release


class CourseViewReleaseRequestTests(unittest.TestCase):
    def test_live_release_requests_garmin_simplified_chinese(self) -> None:
        with patch.object(release, "fetch_bytes", return_value=b"release") as fetch:
            self.assertEqual(
                release.load_release_pb(32842, True),
                b"release",
            )

        fetch.assert_called_once_with(
            "https://omt.garmin.cn/CourseViewData/course-layouts/32842/releases/"
            "?languageCode=zh_CHS"
        )


if __name__ == "__main__":
    unittest.main()
