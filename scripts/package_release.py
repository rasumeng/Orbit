"""Create and validate deterministic, versioned Orbit release artifacts."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / 'artifacts' / 'releases'
RELEASE_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')
FIXED_TIME = (1980, 1, 1, 0, 0, 0)


def validate_zip(path, require_index=False, expected_entries=None):
    with zipfile.ZipFile(path) as archive:
        bad_file = archive.testzip()
        if bad_file:
            raise ValueError(f'{path.name}: corrupt ZIP entry {bad_file}')
        names = [entry.filename for entry in archive.infolist() if not entry.is_dir()]
        if len(names) != len(set(names)):
            raise ValueError(f'{path.name}: duplicate ZIP entry')
        for name in names:
            item = PurePosixPath(name)
            if not name or chr(92) in name or item.is_absolute() or item.as_posix() != name or any(part in {'', '.', '..'} for part in item.parts):
                raise ValueError(f'{path.name}: unsafe or non-portable ZIP path {name!r}')
            if any(part.startswith('.') or part.lower() in {'credentials', 'aws-credentials', 'node_modules', '__pycache__'} or part.lower().endswith(('.pem', '.key')) for part in item.parts):
                raise ValueError(f'{path.name}: development or credential file in ZIP: {name}')
        if require_index and 'index.html' not in names:
            raise ValueError(f'{path.name}: index.html must be at ZIP root')
        if expected_entries is not None and names != expected_entries:
            raise ValueError(f'{path.name}: expected entries {expected_entries}, got {names}')
        return names


def add_file(archive, source, arcname):
    info = zipfile.ZipInfo(arcname, FIXED_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, source.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def validate_release(release_dir, release_id=None):
    backend = release_dir / 'orbit-backend.zip'
    frontend = release_dir / 'orbit-frontend.zip'
    template = release_dir / 'orbit-stack.yaml'
    for path in (backend, frontend, template):
        if not path.is_file():
            raise ValueError(f'Missing release file: {path}')
    validate_zip(backend, expected_entries=['app.py'])
    validate_zip(frontend, require_index=True)
    with zipfile.ZipFile(frontend) as archive:
        html = archive.read('index.html').decode('utf-8')
        expected_base = f'/releases/{release_id}/' if release_id else '/releases/'
        if expected_base not in html:
            raise ValueError('Frontend index.html must reference versioned /releases/ assets')
    return backend, frontend, template


def package(release_id):
    if not RELEASE_PATTERN.fullmatch(release_id):
        raise ValueError('Release ID must start with a letter or number and contain only letters, numbers, dot, underscore, or hyphen (up to 64 characters).')
    final_dir = ARTIFACTS / release_id
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    if final_dir.exists():
        raise FileExistsError(f'Release directory already exists: {final_dir}')
    release_dir = Path(tempfile.mkdtemp(prefix=f'.{release_id}.', dir=ARTIFACTS))
    try:
        frontend_dir = ROOT / 'frontend'
        env = os.environ.copy()
        for key in list(env):
            if key.upper().startswith('VITE_'):
                env.pop(key)
        env['VITE_ASSET_BASE'] = f'/releases/{release_id}/'
        env['VITE_API_URL'] = '/api'
        env['VITE_ENV_DIR'] = str(release_dir)
        npm = 'npm.cmd' if os.name == 'nt' else 'npm'
        subprocess.run([npm, 'ci', '--no-audit', '--no-fund'], cwd=frontend_dir, env=env, check=True)
        subprocess.run([npm, 'run', 'build'], cwd=frontend_dir, env=env, check=True)

        backend_zip = release_dir / 'orbit-backend.zip'
        with zipfile.ZipFile(backend_zip, 'w') as archive:
            add_file(archive, ROOT / 'backend' / 'app.py', 'app.py')

        frontend_zip = release_dir / 'orbit-frontend.zip'
        dist = frontend_dir / 'dist'
        files = sorted(path for path in dist.rglob('*') if path.is_file())
        if any(path.is_symlink() for path in files):
            raise ValueError('Frontend build contains a symlink; refusing to package a file outside dist')
        with zipfile.ZipFile(frontend_zip, 'w') as archive:
            for source in files:
                add_file(archive, source, source.relative_to(dist).as_posix())

        template = release_dir / 'orbit-stack.yaml'
        shutil.copyfile(ROOT / 'orbit-stack.yaml', template)
        backend, frontend, template = validate_release(release_dir, release_id)
        manifest = {
            'releaseId': release_id,
            'artifactBucketPrefix': f'releases/{release_id}/',
            'backendZipKey': f'releases/{release_id}/{backend.name}',
            'frontendZipKey': f'releases/{release_id}/{frontend.name}',
            'templateKey': f'releases/{release_id}/{template.name}',
            'sha256': {backend.name: sha256(backend), frontend.name: sha256(frontend), template.name: sha256(template)},
        }
        (release_dir / 'release.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        release_dir.rename(final_dir)
        print(f'Release package: {final_dir}')
        print(f'Validated: {backend.name}, {frontend.name}, {template.name}')
    finally:
        if release_dir.exists():
            shutil.rmtree(release_dir)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-id')
    parser.add_argument('--validate-only', action='store_true')
    parser.add_argument('--release-dir', type=Path)
    args = parser.parse_args()
    try:
        if args.validate_only:
            directory = args.release_dir.resolve() if args.release_dir else None
            if directory is None:
                parser.error('--validate-only requires --release-dir')
            if not args.release_id or not RELEASE_PATTERN.fullmatch(args.release_id):
                parser.error('--validate-only requires a valid --release-id')
            expected_parent = ARTIFACTS.resolve()
            if directory.parent != expected_parent or directory.name != args.release_id:
                raise ValueError('Release directory must be the versioned artifact directory for the specified release ID')
            backend, frontend, template = validate_release(directory, args.release_id)
            manifest = json.loads((directory / 'release.json').read_text(encoding='utf-8'))
            expected_manifest = {
                'releaseId': args.release_id,
                'artifactBucketPrefix': f'releases/{args.release_id}/',
                'backendZipKey': f'releases/{args.release_id}/{backend.name}',
                'frontendZipKey': f'releases/{args.release_id}/{frontend.name}',
                'templateKey': f'releases/{args.release_id}/{template.name}',
                'sha256': {backend.name: sha256(backend), frontend.name: sha256(frontend), template.name: sha256(template)},
            }
            if manifest != expected_manifest:
                raise ValueError('Release manifest does not match the artifacts or release ID')
            print(f'Release validated: {directory}')
        elif args.release_id:
            package(args.release_id)
        else:
            parser.error('--release-id is required')
    except (OSError, ValueError, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        print(f'Release packaging failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
