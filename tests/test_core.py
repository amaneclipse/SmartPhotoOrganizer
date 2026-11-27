from pathlib import Path
import tempfile
import unittest
from app.sorting.engine import unique_destination

class TestCore(unittest.TestCase):
    def test_unique_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "image.jpg"; original.write_bytes(b"x")
            self.assertEqual(unique_destination(original).name, "image (1).jpg")
