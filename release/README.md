# Release archives

Each GitHub release ships one archive per architecture the panel supports
(`misaka/ui/panel/lib/README.md`). macOS and Linux archives are `.tar.gz`.
Windows archives are `.zip`. The top-level directory has the same name as the
file, `misaka-<version>-<target>`.

```text
bin/misaka            launcher (bin/misaka.exe on Windows) and misaka.wrap
python/               CPython from python-build-standalone
tools/uv              uv
tools/rg              ripgrep
tools/fd              fd
tools/git             git; GIT_EXEC_PATH and GIT_TEMPLATE_DIR point inside the bundle
tools/pdftotext       poppler, plus the other poppler command-line tools
opt/conda             libraries for git and, except on Windows ARM64, poppler
opt/poppler           Windows ARM64 only (MSYS2 clangarm64)
LICENSE
NOTICE
THIRD_PARTY_NOTICES.md
BUNDLED.txt
tools/LICENSES/
```

`bin/misaka` runs `python -m misaka` with the bundled interpreter and puts
`tools/` on `PATH` for that process and its children. A Homebrew or WinGet
link still finds `python/` and `tools/`, because the launcher resolves its own
path after symlinks.

| Target | Built on | Archive |
|---|---|---|
| `darwin-arm64` | `macos-15` | `.tar.gz` |
| `darwin-x86_64` | `macos-15-intel` | `.tar.gz` |
| `linux-x86_64` | `ubuntu-24.04` | `.tar.gz` |
| `linux-arm64` | `ubuntu-24.04-arm` | `.tar.gz` |
| `windows-x86_64` | `windows-2025` | `.zip` |
| `windows-arm64` | `windows-11-arm` | `.zip` |

## What is bundled

The README quick start requires uv, git, ripgrep, fd and poppler. Those are in
every archive, under the names the app looks up: `uv`, `git`, `rg`, `fd` and
`pdftotext`. The rest of the poppler tools (`pdfinfo`, `pdftoppm`, and the
others) are on `PATH` too.

uv, ripgrep and fd are the upstream release binaries. On Linux those are the
musl builds. git comes from conda-forge. poppler comes from conda-forge as
well, except on Windows ARM64, where conda-forge has git and does not publish
poppler: that poppler build is the MSYS2 clangarm64 package.

ocrmypdf, DjVuLibre and LibreOffice stay optional and are not in the archive.
Pinned versions of Python, uv, ripgrep and fd are in `tool-versions.json`.
conda-forge package versions are recorded in `BUNDLED.txt` when the archive is
built.

The checked-in Homebrew formula and winget manifests use a sha256 of 64 zeros.
A release rewrites them from the archives it just built. `brew install` and
`winget install` need those rewritten files, published as below.

## CI

`.github/workflows/ci.yml` runs on pull requests and on pushes to `main`. It
calls `.github/workflows/package.yml`, which runs the packaging tests and then
builds one archive per target on that target's runner.

`.github/workflows/release.yml` runs when a tag `v*` is pushed. The tag must
be `v` plus `project.version` in `pyproject.toml`. The workflow builds the six
archives, attaches them to a GitHub release with `SHA256SUMS`, `misaka.rb`,
`NOTES.md` and the filled winget manifests, and updates the Homebrew tap when
the token below is set.

Build an archive locally on a machine of that architecture:

```sh
python scripts/build_release.py
```

## Install scripts

macOS and Linux pick the archive for `uname` and check it against `SHA256SUMS`:

```sh
curl -fsSL https://raw.githubusercontent.com/Luciole-Studio/Misaka-Agent/main/scripts/install.sh | sh
```

Windows (PowerShell):

```powershell
irm https://raw.githubusercontent.com/Luciole-Studio/Misaka-Agent/main/scripts/install.ps1 | iex
```

The default install root is `~/.local/share/misaka` (Windows: `%LOCALAPPDATA%\misaka`).
The shell script links `misaka` into `~/.local/bin`. The PowerShell script adds
the archive's `bin` directory to the user `PATH`.

`MISAKA_VERSION` selects a release (`0.18.5` or `v0.18.5`; the default is the
latest GitHub release). `MISAKA_PREFIX` changes the install root. `MISAKA_REPO`
changes `owner/name`. The shell script also reads `MISAKA_BIN`.

## Homebrew tap

`release/homebrew/misaka.rb` is a formula (a CLI binary, not a cask). It
installs the `.tar.gz` for macOS or Linux, arm64 or x86_64, into `libexec` and
symlinks `bin/misaka`. Windows is distributed with winget.

This repository cannot create the tap. To publish it:

1. Create `https://github.com/Luciole-Studio/homebrew-tap` with a `Formula/` directory. A different `owner/name` can be set as the Actions variable `HOMEBREW_TAP_REPO`.
2. Add a fine-grained personal access token as the Actions secret `HOMEBREW_TAP_TOKEN`, with contents write on that repository.
3. Push a `v*` tag. The release workflow copies the rewritten formula to `Formula/misaka.rb` and pushes it.

Without the secret, the release still publishes and attaches `misaka.rb`. After
the tap exists:

```sh
brew install luciole-studio/tap/misaka
```

## winget

`release/winget/` holds the three manifests for `Luciole-Studio.Misaka`
(schema 1.10.0): a zip installer, portable nested installer, command alias
`misaka`, and `ArchiveBinariesDependOnPath` so the install location is on
`PATH`. x64 asks for Windows 10 1809 (`10.0.17763.0`). arm64 asks for Windows
11 (`10.0.22000.0`).

The release attaches manifests whose sha256 values match the zip files. Submit
those files to [microsoft/winget-pkgs](https://github.com/microsoft/winget-pkgs).
This repository does not open that pull request. After it is merged:

```powershell
winget install Luciole-Studio.Misaka
```
