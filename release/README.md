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

`.github/workflows/release.yml` runs when a GitHub Release is published as a
prerelease (`release` event type `prereleased`). Pushing a `v*` tag does not
publish a release and does not start this workflow. The tag on that prerelease
must be `v` plus `project.version` in `pyproject.toml`. The workflow builds the
six archives and uploads them onto that same prerelease, together with
`SHA256SUMS`, `misaka.rb`, `NOTES.md` and the filled winget manifests. Hashes
in those files come from the archives just built. The release stays a
prerelease. When `HOMEBREW_TAP_TOKEN` is set, the tap is updated at the end of
this build. Promoting the release later does not run the workflow again, so the
tap is not updated a second time.

To ship a version:

1. On the GitHub releases page, publish a release for tag `v` plus `project.version` and check **Set as a pre-release**. That publish is what starts the build.
2. Wait until the Release workflow has uploaded the archives and the checksum, formula, and winget files onto that prerelease.
3. When the assets look right, edit the release and uncheck **Set as a pre-release**. That promotion does not rebuild the archives and does not replace the assets.

Install scripts ask GitHub for `/releases/latest`, which omits prereleases, so
`curl | sh` and `irm | iex` pick the version up only after that promotion.

Build an archive locally on a machine of that architecture:

```sh
python scripts/build_release.py
```

## Install test

`.github/workflows/install.yml` runs only when someone starts it by hand:
**Actions → Install → Run workflow**. It does not run on a pull request, on a
push to `main`, or when a prerelease is published. The packaging workflow
still syntax-checks `scripts/install.sh` with `sh -n`. This one runs the
installers.

Pick the branch that contains the scripts you want to test, then fill in:

| Input | Default | What to enter |
|---|---|---|
| `repo` | this repository | `owner/name` of the GitHub release. Leave it empty to use the repository that contains the workflow. |
| `tag` | required | `v0.18.5` or `0.18.5`. A prerelease tag works. A tag with no release does not. |
| `targets` | `all` | `all`, or a comma-separated list of `darwin-arm64`, `darwin-x86_64`, `linux-x86_64`, `linux-arm64`, `windows-x86_64`, `windows-arm64`. |

Each selected target runs on that target's runner. The job checks out this
branch and runs `scripts/install.sh` (macOS and Linux) or `scripts/install.ps1`
(Windows). The script downloads the archive for that machine from the release,
checks `SHA256SUMS`, and installs under `MISAKA_PREFIX`. The job then runs
`misaka --version`, `uv`, `rg`, `fd`, `git`, and `pdftotext` from that install.

If the release has no assets, the workflow stops before those runners and says
so. Publish the prerelease and wait until the Release workflow has uploaded
the archives.

## GitHub secrets

`.github/workflows/ci.yml` and `.github/workflows/package.yml` use no secrets
and no Actions variables. Pull requests and `main` build the archives with the
default `contents: read` permission.

Uploading those archives onto a prerelease also needs no secret a person
creates. `.github/workflows/release.yml` sets `permissions: contents: write`
and passes the automatic `GITHUB_TOKEN` (`github.token`) to `gh`. That token
can view the triggering release and upload assets onto it. Creating a
repository secret named `GITHUB_TOKEN` is not required, and a secret of that
name would not replace the automatic token.

One repository secret and one Actions variable exist, both for the Homebrew
tap push. Set them on the repository that runs the workflow: **Settings →
Secrets and variables → Actions**. Secrets go on the Secrets tab. Variables go
on the Variables tab. They are repository settings, not environment settings,
because the workflow reads `secrets.*` and `vars.*` with no environment.

### `HOMEBREW_TAP_TOKEN`

Repository secret. A fine-grained personal access token that clones the tap
and pushes `Formula/misaka.rb`.

Create the token on the account that can push to the tap. Repository access is
only that tap. Permission is **Contents: Read and write**. The token does not
need access to this Misaka repository. Metadata read comes with a fine-grained
token.

Until this secret exists, the release workflow still builds the six archives
and still uploads the archives, `SHA256SUMS`, `misaka.rb`, `NOTES.md`, and the
winget manifests onto the prerelease. The tap step prints that the token is
missing and exits successfully. It does not clone or push the tap, so
`brew install` from the tap does not see the new formula.

### `HOMEBREW_TAP_REPO`

Actions variable, not a secret. Value is `owner/name` of the tap repository.
`HOMEBREW_TAP_TOKEN` must have Contents write on that repository.

Until this variable exists, the workflow uses `Luciole-Studio/homebrew-tap`.
Nothing else changes.

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

1. Create `https://github.com/Luciole-Studio/homebrew-tap` with a `Formula/` directory. A different `owner/name` can be set as the Actions variable `HOMEBREW_TAP_REPO` (see [GitHub secrets](#github-secrets)).
2. Add the fine-grained personal access token described under [GitHub secrets](#github-secrets) as the Actions secret `HOMEBREW_TAP_TOKEN`.
3. Publish a prerelease for tag `v` plus `project.version`, as described above. The release workflow copies the rewritten formula to `Formula/misaka.rb` and pushes it while the release is still a prerelease.

Without the secret, the workflow still uploads `misaka.rb` onto the prerelease. After
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
