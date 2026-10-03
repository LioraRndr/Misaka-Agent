"""Stage Windows ARM64 poppler from the MSYS2 clangarm64 repository.

conda-forge publishes git for win-arm64 and does not publish poppler. The
clangarm64 repository does. This downloads that package plus the runtime
DEPENDS closure (not the build dependencies) and extracts bin/, share/ and
etc/ into the destination prefix so pdftotext.exe sits next to its DLLs.
"""

from __future__ import annotations

import io
import sys
import tarfile
import urllib.request
from pathlib import Path

import zstandard
from build_release import dependency_closure, parse_pacman_db

MIRROR = "https://repo.msys2.org/mingw/clangarm64"
ROOT_PACKAGES = ("mingw-w64-clang-aarch64-poppler", "mingw-w64-clang-aarch64-poppler-data")
KEEP = {"bin", "share", "etc"}


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 0:
        return
    request = urllib.request.Request(url, headers={"User-Agent": "misaka-release"})
    partial = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(request, timeout=180) as response, partial.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
    partial.replace(dest)


def _decompress(path: Path) -> bytes:
    with path.open("rb") as handle:
        reader = zstandard.ZstdDecompressor().stream_reader(handle)
        return reader.read()


def _extract_runtime(blob: bytes, dest: Path) -> None:
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            parts = Path(member.name).parts
            if len(parts) < 2 or parts[1] not in KEEP:
                continue
            target = dest.joinpath(*parts[1:])
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                continue
            target.write_bytes(source.read())


def stage(dest: Path, cache: Path) -> str:
    """Extract poppler into ``dest``. Returns the poppler package version."""
    database = cache / "clangarm64.db.tar.zst"
    _download(f"{MIRROR}/clangarm64.db.tar.zst", database)
    packages = parse_pacman_db(_decompress(database))
    selected = dependency_closure(packages, ROOT_PACKAGES)
    version = ""
    dest.mkdir(parents=True, exist_ok=True)
    for name in selected:
        package = packages[name]
        filename = package["filename"]
        archive = cache / filename
        print(f"msys2 {name} {package['version']}", flush=True)
        _download(f"{MIRROR}/{filename}", archive)
        _extract_runtime(_decompress(archive), dest)
        if name == "mingw-w64-clang-aarch64-poppler":
            version = package["version"]
    if not version:
        raise SystemExit("MSYS2 poppler package was not in the dependency closure")
    (dest / "VERSION").write_text(version + "\n", encoding="utf-8")
    return version


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        raise SystemExit("usage: msys2_poppler.py DEST CACHE")
    stage(Path(argv[1]), Path(argv[2]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
