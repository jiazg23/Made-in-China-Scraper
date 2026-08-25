import io
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from main import _write_uploadable_image, image_dimensions, normalize_actor_input  # noqa: E402


class ImagePreparationTests(unittest.TestCase):
    def test_csv_export_defaults_to_enabled(self):
        self.assertTrue(normalize_actor_input({"searchTerms": ["hinge"]})["saveCsvFile"])
        self.assertFalse(
            normalize_actor_input({"searchTerms": ["hinge"], "saveCsvFile": False})["saveCsvFile"]
        )

    def test_selected_search_mode_requires_matching_input(self):
        with self.assertRaisesRegex(ValueError, "at least one product keyword"):
            normalize_actor_input({"searchMode": "keyword", "searchTerms": []})
        with self.assertRaisesRegex(ValueError, "at least one uploaded image"):
            normalize_actor_input({"searchMode": "image", "uploadedImages": [], "imageUrls": []})

    def test_converts_gif_to_supported_jpeg(self):
        source = io.BytesIO()
        Image.new("RGBA", (12, 8), (25, 75, 125, 128)).save(source, format="GIF")

        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(
                _write_uploadable_image(source.getvalue(), Path(temporary_directory), "sample image")
            )
            self.assertEqual(output.suffix, ".jpg")
            self.assertEqual(image_dimensions(output), (12, 8))
            with Image.open(output) as converted:
                self.assertEqual(converted.format, "JPEG")

    def test_preserves_supported_png(self):
        source = io.BytesIO()
        Image.new("RGB", (5, 7), "red").save(source, format="PNG")

        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(_write_uploadable_image(source.getvalue(), Path(temporary_directory), "sample"))
            self.assertEqual(output.suffix, ".png")
            self.assertEqual(output.read_bytes(), source.getvalue())


if __name__ == "__main__":
    unittest.main()
