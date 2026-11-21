"""Fetch the competition-pinned SQLGlot source at Docker build time.

GitHub's source archives can legitimately contain symbolic links. The previous
extractor rejected every link and prevented the Docker image from building.
This version preserves *safe in-repository* links, skips unsafe links, and uses
Python's tarfile data filter to prevent extraction outside the staging folder.
"""
from __future__ import annotations

import io
import os
import posixpath
import tarfile
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath

COMMIT = 'eb11aec4be8cb2122afe713a4816662c3f0fb2fa'
URL = f'https://github.com/tobymao/sqlglot/archive/{COMMIT}.tar.gz'
PREFIX = f'sqlglot-{COMMIT}'
DEST = Path('/opt/sqlglot')


def extract_pinned_archive(body: bytes, dest: Path = DEST) -> None:
    """Extract just the pinned repo, including safe internal symlinks.

    Extract to a temporary directory first, then move it into place only after
    the pinned package file is verified. Never trust archive entry paths.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() or dest.is_symlink():
        raise FileExistsError(f'Extraction destination already exists: {dest}')

    skipped_links: list[str] = []
    with tempfile.TemporaryDirectory(prefix='sqlglot-extract-', dir=dest.parent) as tmp:
        stage = Path(tmp)

        def safe_filter(member: tarfile.TarInfo, target_directory: str) -> tarfile.TarInfo | None:
            name = PurePosixPath(member.name)
            if not name.parts or name.parts[0] != PREFIX or '..' in name.parts or name.is_absolute():
                return None
            if member.isdev():
                raise ValueError(f'Device in archive: {member.name}')
            if member.issym() or member.islnk():
                # Symbolic link targets are relative to the link's directory;
                # hard link targets are relative to the archive root.
                if member.linkname.startswith('/'):
                    skipped_links.append(member.name)
                    return None
                if member.issym():
                    link_target = posixpath.normpath(posixpath.join(posixpath.dirname(member.name), member.linkname))
                else:
                    link_target = posixpath.normpath(member.linkname)
                parts = PurePosixPath(link_target).parts
                if not parts or parts[0] != PREFIX:
                    skipped_links.append(member.name)
                    return None
            try:
                # Python 3.13's built-in data filter validates destinations,
                # symlink escapes, and unsafe metadata before extraction.
                return tarfile.data_filter(member, target_directory)
            except tarfile.FilterError:
                if member.issym() or member.islnk():
                    skipped_links.append(member.name)
                    return None
                raise

        with tarfile.open(fileobj=io.BytesIO(body), mode='r:gz') as archive:
            archive.extractall(path=stage, filter=safe_filter)

        root = stage / PREFIX
        if not (root / 'sqlglot' / '__init__.py').is_file():
            raise RuntimeError('The pinned SQLGlot package was missing from its source archive')
        root.rename(dest)

    if skipped_links:
        print(f'Skipped {len(skipped_links)} archive links pointing outside the pinned source tree', flush=True)


def main() -> None:
    request = urllib.request.Request(URL, headers={'User-Agent': 'Bizz01-build/1.1'})
    with urllib.request.urlopen(request, timeout=180) as response:
        body = response.read()
    extract_pinned_archive(body)
    print(f'Fetched pinned sqlglot at {COMMIT}', flush=True)


if __name__ == '__main__':
    main()
