#!/usr/bin/env python3
"""Focused regression tests for the same-day screenshot check (stdlib only)."""
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from validate import (
    drive_file_id,
    exif_date,
    judge,
    mask_name,
    parse_hu_ts,
    parse_km,
)


def jpeg_with_exif(dt_str=None):
    from PIL import Image

    img = Image.new("RGB", (8, 8), "white")
    buf = io.BytesIO()
    if dt_str is None:
        img.save(buf, format="JPEG")
    else:
        ex = Image.Exif()
        ex[36867] = dt_str
        img.save(buf, format="JPEG", exif=ex)
    return buf.getvalue()


def png_plain():
    from PIL import Image

    img = Image.new("RGB", (8, 8), "white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestSameDay(unittest.TestCase):
    def test_exif_same_day(self):
        sub = parse_hu_ts("2026.09.16. 12:03:30")
        self.assertEqual(exif_date(jpeg_with_exif("2026:09:16 09:41:00")), sub.date())

    def test_exif_other_day(self):
        sub = parse_hu_ts("2026.09.16. 12:03:30")
        self.assertNotEqual(exif_date(jpeg_with_exif("2026:09:10 09:41:00")), sub.date())

    def test_png_has_no_exif(self):
        self.assertIsNone(exif_date(png_plain()))

    def test_jpeg_without_exif(self):
        self.assertIsNone(exif_date(jpeg_with_exif(None)))

    def test_hu_timestamps(self):
        self.assertIsNotNone(parse_hu_ts("2026.09.16. 12:03:30"))
        self.assertIsNotNone(parse_hu_ts("2026-09-16 12:03:30"))
        self.assertIsNone(parse_hu_ts("nonsense"))

    def test_km_values(self):
        self.assertEqual(parse_km("50"), 50)
        self.assertEqual(parse_km("3,2 km"), 3.2)
        self.assertEqual(parse_km("10 km"), 10)
        self.assertIsNone(parse_km("abc"))
        self.assertIsNone(parse_km("-5"))

    def test_drive_ids(self):
        self.assertEqual(
            drive_file_id("https://drive.google.com/open?id=ABC123_-x"), "ABC123_-x"
        )
        self.assertEqual(
            drive_file_id("https://drive.google.com/file/d/DEF456/view"), "DEF456"
        )
        self.assertIsNone(drive_file_id("not a link"))

    def test_name_masking(self):
        self.assertEqual(mask_name("Gábor Csaba"), "Gábor C.")
        self.assertEqual(mask_name("Bene"), "Bene")

    def test_judge_pending_paths(self):
        sub = parse_hu_ts("2026.09.16. 12:03:30")
        self.assertEqual(judge("", sub, "K", "K")[0], "pending")  # no image
        self.assertEqual(judge("FID", None, "K", "K")[0], "pending")  # no date
        st, ev = judge("FID", sub, "", "")  # no service account
        self.assertEqual((st, ev), ("pending", "no-drive-access"))


if __name__ == "__main__":
    unittest.main()
