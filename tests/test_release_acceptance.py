"""Release readiness invariants: version drift, integrity, parity and performance."""
import json
import shutil
import tempfile
from pathlib import Path
import unittest

from scripts.release_acceptance import (
    AcceptanceError, create_artifact_manifest, performance_smoke,
    verify_release, verify_source,
)

ROOT = Path(__file__).resolve().parents[1]


class ReleaseAcceptanceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='sparkle-release-test-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        files = ['pyproject.toml', 'package.json', 'sparkle_coder/__init__.py',
                 'sparkle_coder/distribution.json', 'sparkle_coder/ui/app.js',
                 'sparkle_coder/ui/app.css', 'gateway/public/agent.js',
                 'gateway/public/agent.css', 'gateway/src/worker.mjs', 'packaging/windows.iss']
        for name in files:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)

    def test_current_versions_and_exact_cloud_assets_match(self):
        result = verify_source(self.root, tag='v0.8.0')
        self.assertEqual(result['version'], '0.8.0')
        self.assertTrue(result['cloud_ui_synchronized'])

    def test_source_mismatch_and_wrong_release_tag_fail_closed(self):
        with self.assertRaisesRegex(AcceptanceError, 'Tag'):
            verify_source(self.root, tag='v0.7.0')
        for name, original, wrong in [
            ('packaging/windows.iss', 'AppVersion "0.8.0"', 'AppVersion "0.7.0"'),
            ('sparkle_coder/__init__.py', '__version__ = "0.8.0"', '__version__ = "0.7.0"'),
            ('package.json', '"version": "0.8.0"', '"version": "0.7.0"'),
            ('gateway/src/worker.mjs', "version:'0.8.0'", "version:'0.7.0'"),
        ]:
            with self.subTest(name=name):
                target = self.root / name
                old = target.read_text('utf-8')
                self.assertIn(original, old)
                target.write_text(old.replace(original, wrong), 'utf-8')
                with self.assertRaises(AcceptanceError):
                    verify_source(self.root)
                target.write_text(old, 'utf-8')

    def test_source_refuses_stale_bundled_cloud_javascript_and_css(self):
        for name in ('gateway/public/agent.js', 'gateway/public/agent.css'):
            with self.subTest(name=name):
                target = self.root / name
                before = target.read_bytes()
                target.write_bytes(before + b'\n// stale bundle\n')
                with self.assertRaisesRegex(AcceptanceError, 'stale'):
                    verify_source(self.root)
                target.write_bytes(before)

    def build_fixture(self):
        dist = self.root / 'dist'
        (dist / 'runtime/python').mkdir(parents=True)
        (dist / 'SparkleCoder.exe').write_bytes(b'win')
        (dist / 'SparkleCoder').write_bytes(b'unix')
        output = self.root / 'out'
        output.mkdir()
        (output / 'EDITION.txt').write_text('personal edition\n\n', 'utf-8')
        for platform, arch, filename in [
            ('Windows', 'X64', 'SPARKLE-CODER-Windows-Setup.exe'),
            ('Linux', 'X64', 'SPARKLE-CODER-Linux-X64.tar.gz'),
            ('macOS', 'ARM64', 'SPARKLE-CODER-macOS-ARM64.tar.gz'),
        ]:
            (output / filename).write_bytes((platform + '-archive').encode() * 30)
            create_artifact_manifest(self.root, platform=platform, arch=arch)
        return output

    def test_three_platform_artifact_hashes_edition_version_and_bundled_python(self):
        output = self.build_fixture()
        result = verify_release(output, root=self.root)
        self.assertEqual(result['artifacts_verified'], 3)
        self.assertEqual(result['mode'], 'personal')
        with self.assertRaisesRegex(AcceptanceError, 'tester'):
            verify_release(output, root=self.root, require_pilot=True)

    def test_corrupted_artifact_and_mixed_edition_are_rejected(self):
        output = self.build_fixture()
        target = output / 'SPARKLE-CODER-Linux-X64.tar.gz'
        target.write_bytes(target.read_bytes() + b'attack')
        with self.assertRaisesRegex(AcceptanceError, 'hash/size'):
            verify_release(output, root=self.root)
        target.write_bytes(target.read_bytes()[:-6])
        manifest = output / 'ACCEPTANCE-macOS-ARM64.json'
        data = json.loads(manifest.read_text('utf-8'))
        data['mode'] = 'pilot'
        data['gateway_url'] = 'https://example.workers.dev'
        manifest.write_text(json.dumps(data), 'utf-8')
        with self.assertRaisesRegex(AcceptanceError, 'disagree'):
            verify_release(output, root=self.root)

    def test_missing_platform_or_persisted_runtime_never_marks_release_ready(self):
        output = self.build_fixture()
        (output / 'ACCEPTANCE-Windows-X64.json').unlink()
        with self.assertRaisesRegex(AcceptanceError, 'missing'):
            verify_release(output, root=self.root)
        shutil.rmtree(self.root / 'dist/runtime/python')
        with self.assertRaisesRegex(AcceptanceError, 'Bundled project Python'):
            create_artifact_manifest(self.root, platform='Windows', arch='X64')

    def test_main_build_checks_all_platform_manifests_before_release(self):
        workflow = (ROOT / '.github/workflows/build-installers.yml').read_text('utf-8')
        self.assertIn('verify-distribution:', workflow)
        self.assertIn('needs: [build, verify-distribution]', workflow)
        self.assertIn('python scripts/release_acceptance.py aggregate --directory release', workflow)
        self.assertIn('pattern: SPARKLE-CODER-*', workflow)
        self.assertIn('python scripts/release_acceptance.py aggregate --directory release --require-pilot', workflow)

    def test_perf_smoke_detects_actual_edits_and_reports_measured_latency(self):
        result = performance_smoke(count=24, file_bytes=1024,
                                   cold_limit_ms=5000, warm_limit_ms=5000)
        self.assertTrue(result['external_edit_detected'])
        self.assertTrue(result['delete_accepted'])
        self.assertGreaterEqual(result['warm_median_ms'], 0)
        self.assertIn('fingerprint', result['scope'])


if __name__ == '__main__':
    unittest.main()
