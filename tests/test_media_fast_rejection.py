"""Wrong image URLs must be rejected before a potentially slow remote search."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sparkle_coder.media_library import import_commons_image
from sparkle_coder.workspace import Workspace


class FastMediaRejectTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Workspace(Path(temporary.name))

    def test_invalid_hosts_are_rejected_without_contacting_network(self):
        rejected = [
            'https://other.example/',
            'https://upload.wikimedia.org.attacker.example/image.jpg',
            'https://127.0.0.1/a.jpg',
            'https://user@upload.wikimedia.org/image.jpg',
            'https://upload.wikimedia.org:8080/a.jpg',
            'http://upload.wikimedia.org/a.jpg',
            'https://upload.wikimedia.org/a.jpg#secret',
            'ftp://upload.wikimedia.org/a.jpg',
        ]
        for url in rejected:
            with self.subTest(url=url), \
                 patch('sparkle_coder.media_library.search_public_assets') as search, \
                 patch('sparkle_coder.media_library.download_public_asset') as download:
                with self.assertRaisesRegex(ValueError, 'Search results changed'):
                    import_commons_image(self.workspace, 'landscape', url)
                search.assert_not_called()
                download.assert_not_called()

    def test_valid_host_must_still_appear_in_fresh_results_before_download(self):
        url = 'https://upload.wikimedia.org/wikipedia/commons/photo.jpg'
        with patch('sparkle_coder.media_library.search_public_assets',
                   return_value={'results': []}) as search, \
             patch('sparkle_coder.media_library.download_public_asset') as download:
            with self.assertRaisesRegex(ValueError, 'Search results changed'):
                import_commons_image(self.workspace, 'landscape', url)
            search.assert_called_once_with('landscape', 8)
            download.assert_not_called()


if __name__ == '__main__':
    unittest.main()
