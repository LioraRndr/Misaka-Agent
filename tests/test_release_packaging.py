"""The release archives cover the architectures the panel ships, and the launcher finds its tree."""

from __future__ import annotations

import importlib.util
import io
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("build_release", ROOT / "scripts" / "build_release.py")
assert _SPEC is not None and _SPEC.loader is not None
build_release = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = build_release
_SPEC.loader.exec_module(build_release)


def test_targets_are_the_panel_library_table():
    text = (ROOT / "misaka" / "ui" / "panel" / "lib" / "README.md").read_text(encoding="utf-8")
    shipped = set(build_release.TARGETS)
    assert shipped == {
        "darwin-arm64",
        "darwin-x86_64",
        "linux-x86_64",
        "linux-arm64",
        "windows-x86_64",
        "windows-arm64",
    }
    for name in shipped:
        assert f"libghostty-vt-{name}." in text


def test_package_workflow_builds_every_target_on_its_runner():
    workflow = (ROOT / ".github" / "workflows" / "package.yml").read_text(encoding="utf-8")
    for name, target in build_release.TARGETS.items():
        assert name in workflow
        assert target.runner in workflow
    assert "pull_request" in (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert 'tags: ["v*"]' in (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")


def test_installers_name_every_archive():
    shell = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")
    powershell = (ROOT / "scripts" / "install.ps1").read_text(encoding="utf-8")
    for name, target in build_release.TARGETS.items():
        script = powershell if name.startswith("windows") else shell
        assert name in script
        assert target.name in script
    assert "Luciole-Studio/Misaka-Agent" in shell
    assert "Luciole-Studio/Misaka-Agent" in powershell
    assert "uv" in shell and "poppler" in shell


def test_checked_in_formula_and_winget_match_the_renderer():
    version = build_release.project_version()
    hashes = build_release.placeholder_hashes()
    formula = (ROOT / "release" / "homebrew" / "misaka.rb").read_text(encoding="utf-8")
    assert formula == build_release.render_homebrew(version, hashes)
    winget = ROOT / "release" / "winget" / "manifests" / "l" / "Luciole-Studio" / "Misaka" / version
    for filename, text in build_release.render_winget(version, hashes).items():
        assert (winget / filename).read_text(encoding="utf-8") == text
    assert "darwin-arm64" in formula and "linux-x86_64" in formula
    installer = (winget / "Luciole-Studio.Misaka.installer.yaml").read_text(encoding="utf-8")
    locale = (winget / "Luciole-Studio.Misaka.locale.en-US.yaml").read_text(encoding="utf-8")
    assert "windows-x86_64" in installer and "windows-arm64" in installer
    assert "pdftotext" in locale


def test_archive_names_round_trip():
    version = "0.18.5"
    for name, target in build_release.TARGETS.items():
        filename = build_release._archive_filename(version, name)
        assert build_release.parse_archive_name(filename) == (version, name)
        assert filename.endswith(".zip" if target.archive == "zip" else ".tar.gz")


def test_pacman_closure_installs_dependencies_first():
    blob = io.BytesIO()
    with tarfile.open(fileobj=blob, mode="w") as archive:
        for name, depends in (("rootpkg", ["liba"]), ("liba", ["libb"]), ("libb", [])):
            text = f"%NAME%\n{name}\n\n%FILENAME%\n{name}.pkg.tar.zst\n\n%VERSION%\n1.0.0-1\n\n%DEPENDS%\n"
            text += "\n".join(depends) + "\n"
            data = text.encode()
            info = tarfile.TarInfo(f"{name}/desc")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    packages = build_release.parse_pacman_db(blob.getvalue())
    assert build_release.dependency_closure(packages, ("rootpkg",)) == ["libb", "liba", "rootpkg"]


def test_tool_discovery_uses_the_bin_directory(tmp_path: Path):
    prefix = tmp_path / "conda"
    (prefix / "bin").mkdir(parents=True)
    (prefix / "libexec" / "git-core").mkdir(parents=True)
    (prefix / "share" / "git-core" / "templates" / "hooks").mkdir(parents=True)
    (prefix / "share" / "poppler").mkdir(parents=True)
    (prefix / "bin" / "git").write_text("git", encoding="utf-8")
    (prefix / "libexec" / "git-core" / "git-add").write_text("add", encoding="utf-8")
    (prefix / "bin" / "pdftotext").write_text("pdf", encoding="utf-8")
    assert build_release._find_program([prefix], "git") == prefix / "bin" / "git"
    assert build_release._find_git_exec(prefix) == prefix / "libexec" / "git-core"
    assert build_release._find_git_templates(prefix) == prefix / "share" / "git-core" / "templates"
    assert build_release._find_poppler_data([prefix]) == prefix / "share" / "poppler"
    assert [path.name for path in build_release._poppler_programs([prefix])] == ["pdftotext"]


def test_launcher_resolves_a_symlink_and_sets_the_tool_path(tmp_path: Path):
    compiler = shutil.which("cc") or shutil.which("gcc")
    if compiler is None:
        pytest.skip("no C compiler")
    binary = tmp_path / "toolwrap"
    subprocess.check_call(
        [compiler, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-o", str(binary), str(ROOT / "scripts" / "toolwrap.c")]
    )
    root = tmp_path / "bundle"
    bindir = root / "bin"
    tools = root / "tools"
    marker = root / "opt" / "marker"
    bindir.mkdir(parents=True)
    tools.mkdir()
    marker.mkdir(parents=True)
    (tools / "rg").write_text("#!/bin/sh\necho rg\n", encoding="utf-8")
    (tools / "rg").chmod(0o755)
    launcher = bindir / "misaka"
    shutil.copy2(binary, launcher)
    launcher.chmod(0o755)
    python = shutil.which("python3")
    assert python is not None
    launcher.with_name("misaka.wrap").write_text(
        "\n".join(
            (
                f"exec={python}",
                "arg=-c",
                "arg=import os; print(os.environ['GIT_EXEC_PATH']); print(os.environ['PATH'].split(':')[0])",
                "env=GIT_EXEC_PATH=../opt/marker",
                "path_prepend=../tools",
                "",
            )
        ),
        encoding="utf-8",
    )
    linked = tmp_path / "linked"
    linked.mkdir()
    link = linked / "misaka"
    link.symlink_to(launcher)
    completed = subprocess.run([str(link)], check=True, text=True, stdout=subprocess.PIPE)
    lines = completed.stdout.splitlines()
    assert lines[0] == str(marker.resolve())
    assert lines[1] == str(tools.resolve())
