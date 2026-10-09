"""Deterministic release checks, bounded performance smoke and artifact provenance.

No network calls, paid services, credentials, builds or deployment. Usage:
  python scripts/release_acceptance.py source [--tag v0.8.0]
  python scripts/release_acceptance.py performance [--output PATH]
  python scripts/release_acceptance.py artifact --platform Windows --arch X64
  python scripts/release_acceptance.py aggregate --directory release [--require-pilot]
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import tempfile
import time
import tomllib


ROOT = Path(__file__).resolve().parents[1]
PLATFORMS = {'Windows': 'Windows-X64', 'Linux': 'Linux-X64', 'macOS': 'macOS-ARM64'}
RELEASE_SCHEMA = 1


class AcceptanceError(ValueError):
    """Fail closed on incomplete or inconsistent release evidence."""


def source_version(root=ROOT):
    project = tomllib.loads((root / 'pyproject.toml').read_text('utf-8'))
    version = project['project']['version']
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise AcceptanceError('The release version must be semantic major.minor.patch.')
    return version


def verify_source(root=ROOT, *, tag=''):
    version = source_version(root)
    sources = {
        'desktop Python': re.search(
            r'^__version__\s*=\s*["\x27]([^"\x27]+)', (root / 'sparkle_coder/__init__.py').read_text('utf-8'), re.M),
        'web package': json.loads((root / 'package.json').read_text('utf-8')).get('version'),
        'Windows installer': re.search(
            r'^#define AppVersion "([^"]+)"', (root / 'packaging/windows.iss').read_text('utf-8'), re.M),
    }
    for name, value in sources.items():
        actual = value.group(1) if hasattr(value, 'group') else value
        if actual != version:
            raise AcceptanceError(f'{name} version {actual!r} does not match {version!r}.')
    for src, target in [('app.js', 'agent.js'), ('app.css', 'agent.css')]:
        if (root / 'sparkle_coder/ui' / src).read_bytes() != (root / 'gateway/public' / target).read_bytes():
            raise AcceptanceError(f'Cloud {target} is stale. Run npm run build:gateway and commit its output.')
    if tag and tag != 'v' + version:
        raise AcceptanceError(f'Tag {tag!r} does not match version v{version}. No release is permitted.')
    return {'version': version, 'version_sources': list(sources),
            'cloud_ui_synchronized': True, 'tag': tag or None}


def file_hash(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def performance_smoke(*, count=160, file_bytes=4096,
                      cold_limit_ms=5000.0, warm_limit_ms=1500.0):
    """A reproducible bounded smoke, not a production SLA or model benchmark.

    This measures the actual project fingerprint API in a disposable workspace.
    The warmed operation must still enumerate files and detect external edits.
    """
    from sparkle_coder.workspace import Workspace
    if not 1 <= count <= 1000 or not 1 <= file_bytes <= 32768:
        raise AcceptanceError('Invalid bounded performance fixture.')
    with tempfile.TemporaryDirectory(prefix='sparkle-acceptance-') as temporary:
        workspace = Workspace(Path(temporary))
        for i in range(count):
            (workspace.root / f'source-{i:04d}.py').write_bytes(
                (f'# source {i}\n'.encode() + b'x' * file_bytes)[:file_bytes])
        durations = []
        for _ in range(7):
            began = time.perf_counter_ns()
            fingerprint = workspace.fingerprint()
            durations.append((time.perf_counter_ns() - began) / 1e6)
            if fingerprint is None:
                raise AcceptanceError('Fingerprint failed during performance smoke.')
        cold_ms = durations[0]
        warm_ms = statistics.median(durations[1:])
        # A warm cache is never permitted to mask a real external modification.
        path = workspace.root / 'source-0000.py'
        payload = path.read_bytes()
        path.write_bytes(b'Y' + payload[1:])
        if workspace.fingerprint() == fingerprint:
            raise AcceptanceError('Fingerprint failed to detect a same-size external source edit.')
        path.unlink()
        if workspace.fingerprint() is None:
            raise AcceptanceError('Fingerprint failed after source deletion.')
    result = {'files': count, 'bytes_per_file': file_bytes,
              'cold_ms': round(cold_ms, 3), 'warm_median_ms': round(warm_ms, 3),
              'warm_max_ms': round(max(durations[1:]), 3),
              'cold_budget_ms': cold_limit_ms, 'warm_budget_ms': warm_limit_ms,
              'external_edit_detected': True, 'delete_accepted': True,
              'scope': 'disposable workspace fingerprint; not model/VM throughput'}
    if cold_ms > cold_limit_ms or warm_ms > warm_limit_ms:
        raise AcceptanceError('Fingerprint performance smoke exceeded conservative CI limits: ' + json.dumps(result))
    return result


def edition_info(root=ROOT):
    data = json.loads((root / 'sparkle_coder/distribution.json').read_text('utf-8'))
    mode, url = data.get('mode'), data.get('gateway_url')
    if mode not in ('personal', 'pilot'):
        raise AcceptanceError('Unknown edition. Refuse packaging.')
    if mode == 'personal' and url:
        raise AcceptanceError('Personal edition must not embed a gateway.')
    if mode == 'pilot':
        from urllib.parse import urlsplit
        parsed = urlsplit(str(url or ''))
        if parsed.scheme != 'https' or not parsed.hostname or parsed.path not in ('', '/') or (
                parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise AcceptanceError('Tester edition must use a public root HTTPS gateway origin.')
    return mode, url


def create_artifact_manifest(root=ROOT, *, platform, arch):
    version = source_version(root)
    mode, url = edition_info(root)
    if platform not in PLATFORMS or PLATFORMS[platform] != f'{platform}-{arch}':
        raise AcceptanceError(f'Unsupported build target {platform}/{arch}.')
    output = root / 'out'
    expected = 'SPARKLE-CODER-Windows-Setup.exe' if platform == 'Windows' else (
        f'SPARKLE-CODER-{platform}-{arch}.tar.gz')
    asset = output / expected
    if not asset.is_file() or asset.stat().st_size < 100:
        raise AcceptanceError(f'Required installer/archive is missing or empty: {expected}')
    if not (root / 'dist/runtime/python').is_dir():
        raise AcceptanceError('Bundled project Python is missing; refuse to mark build distributable.')
    if not (root / 'dist' / ('SparkleCoder.exe' if platform == 'Windows' else 'SparkleCoder')).is_file():
        raise AcceptanceError('Packaged app is missing.')
    edition = output / 'EDITION.txt'
    expected_edition = f'{mode} edition\n{url}\n'
    if not edition.is_file() or edition.read_text('utf-8') != expected_edition:
        raise AcceptanceError('EDITION.txt disagrees with the validated build configuration.')
    manifest = {'schema': RELEASE_SCHEMA, 'version': version, 'target': PLATFORMS[platform],
                'mode': mode, 'gateway_url': url, 'filename': expected,
                'size_bytes': asset.stat().st_size, 'sha256': file_hash(asset),
                'packaged_python': True,
                'packaged_smoke': 'must pass earlier CI step',
                'windows_installer_data_preservation': platform == 'Windows'}
    manifest_path = output / f'ACCEPTANCE-{PLATFORMS[platform]}.json'
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', 'utf-8')
    return manifest


def verify_release(directory, *, root=ROOT, require_pilot=False):
    folder = Path(directory)
    version = source_version(root)
    manifests = []
    for target in PLATFORMS.values():
        manifest_path = folder / f'ACCEPTANCE-{target}.json'
        if not manifest_path.is_file():
            raise AcceptanceError(f'Acceptance manifest missing: {manifest_path.name}')
        data = json.loads(manifest_path.read_text('utf-8'))
        if data.get('schema') != RELEASE_SCHEMA or data.get('version') != version or data.get('target') != target:
            raise AcceptanceError(f'Inconsistent version/schema/target in {manifest_path.name}')
        if data.get('mode') not in ('personal', 'pilot'):
            raise AcceptanceError('Invalid edition in '+manifest_path.name)
        filename = data.get('filename')
        expected = 'SPARKLE-CODER-Windows-Setup.exe' if target == 'Windows-X64' else f'SPARKLE-CODER-{target}.tar.gz'
        if filename != expected:
            raise AcceptanceError(f'Unexpected filename for {target}')
        asset = folder / filename
        if not asset.is_file() or asset.stat().st_size != data.get('size_bytes') or file_hash(asset) != data.get('sha256'):
            raise AcceptanceError(f'Artifact hash/size mismatch: {filename}')
        if data.get('packaged_python') is not True:
            raise AcceptanceError(f'Bundled Python was not verified for {target}')
        if target == 'Windows-X64' and data.get('windows_installer_data_preservation') is not True:
            raise AcceptanceError('Windows installer data preservation was not verified.')
        manifests.append(data)
    editions = {(row['mode'], row['gateway_url']) for row in manifests}
    if len(editions) != 1:
        raise AcceptanceError('Release platforms disagree on edition or gateway URL.')
    if require_pilot and manifests[0]['mode'] != 'pilot':
        raise AcceptanceError('Tagged tester release cannot publish a personal edition.')
    return {'version': version, 'targets': sorted(PLATFORMS.values()),
            'mode': manifests[0]['mode'], 'gateway_url': manifests[0]['gateway_url'],
            'artifacts_verified': len(manifests)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('source', 'performance', 'artifact', 'aggregate'))
    parser.add_argument('--tag', default='')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--platform', choices=tuple(PLATFORMS))
    parser.add_argument('--arch', default='')
    parser.add_argument('--directory', type=Path, default=Path('release'))
    parser.add_argument('--require-pilot', action='store_true')
    args = parser.parse_args()
    try:
        if args.action == 'source':
            result = verify_source(tag=args.tag)
        elif args.action == 'performance':
            result = performance_smoke()
        elif args.action == 'artifact':
            if not args.platform:
                parser.error('artifact requires --platform.')
            result = create_artifact_manifest(platform=args.platform, arch=args.arch)
        else:
            result = verify_release(args.directory, require_pilot=args.require_pilot)
    except (AcceptanceError, OSError, ValueError, KeyError) as exc:
        parser.exit(1, 'Release acceptance FAILED: ' + str(exc) + '\n')
    output = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + '\n', 'utf-8')
    print(output)


if __name__ == '__main__':
    main()
