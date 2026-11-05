"""Unit tests for release ZIP validation; no AWS or npm install required."""
import tempfile
import subprocess
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from package_release import package, validate_release, validate_zip


class ReleaseZipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def make_zip(self, name, entries):
        path = self.root / name
        with zipfile.ZipFile(path, 'w') as archive:
            for entry, content in entries:
                archive.writestr(entry, content)
        return path

    def test_backend_requires_only_root_app(self):
        archive = self.make_zip('backend.zip', [('app.py', 'handler')])
        self.assertEqual(validate_zip(archive, expected_entries=['app.py']), ['app.py'])

    def test_frontend_requires_root_index_and_portable_asset_paths(self):
        archive = self.make_zip('frontend.zip', [
            ('index.html', '<script src="/releases/v1/assets/app.js"></script>'),
            ('assets/app.js', 'compiled'),
        ])
        self.assertEqual(validate_zip(archive, require_index=True), ['index.html', 'assets/app.js'])

    def test_rejects_traversal_backslash_and_environment_files(self):
        for name in ('../escape.js', '.env.production', 'assets/aws-credentials.pem'):
            with self.subTest(name=name):
                archive = self.make_zip('bad.zip', [('index.html', 'ok'), (name, 'bad')])
                with self.assertRaises(ValueError):
                    validate_zip(archive, require_index=True)

    def test_release_requires_versioned_frontend_assets(self):
        release = self.root / 'release'
        release.mkdir()
        self.make_zip('placeholder.zip', [('app.py', 'handler')]).replace(release / 'orbit-backend.zip')
        self.make_zip('frontend.zip', [('index.html', '<script src="/assets/app.js"></script>')]).replace(release / 'orbit-frontend.zip')
        (release / 'orbit-stack.yaml').write_text('Resources: {}\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'versioned'):
            validate_release(release, 'v1')

    def test_failed_build_leaves_no_partial_release_directory(self):
        artifacts = self.root / 'artifacts'
        artifacts.mkdir()
        with patch('package_release.ARTIFACTS', artifacts), patch(
            'package_release.subprocess.run', side_effect=subprocess.CalledProcessError(1, 'npm')
        ):
            with self.assertRaises(subprocess.CalledProcessError):
                package('release-1')
        self.assertEqual(list(artifacts.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
