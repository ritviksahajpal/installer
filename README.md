# geocif + geoprepare + octvi installer (pixi)

Cross-platform installer that provisions a self-contained
[pixi](https://pixi.sh) environment for the `geocif` crop-yield model, its
`geoprepare` preprocessor, and the `octvi` NDVI/GCVI downloader.

**No conda, no uv, no system GDAL module, no CUDA, no compiler gymnastics.**
conda-forge ships its own libgdal + a CPU PyTorch build + every binary dep, so a
single `pixi install` does the whole job. One lockfile reproduces the *identical*
environment on every platform.

Supported platforms (auto-detected):

| | Windows | UMD HPC (gsapp) | Generic / managed Linux | Linux ARM (aarch64) |
|---|---|---|---|---|
| GDAL / torch | conda-forge | conda-forge | conda-forge | conda-forge |
| module load? | — | **no** | — | — |
| special handling | — | cache → `/gpfs` | writable `TMPDIR` | ydf/treeple/rbeast handled |

macOS is **not** a supported target: the generated workspace declares
`linux-64`, `linux-aarch64` and `win-64` only. See the macOS tab under
[Installing pixi](#installing-pixi).

---

## Quick start

```bash
git clone https://github.com/ritviksahajpal/installer.git
cd installer
python install.py --yes
```

`install.py` (stdlib-only, needs Python 3.8+ to bootstrap) will:

1. Install pixi if it's not already on PATH.
2. Write a validated `pixi.toml` into `<install-base>/geo-stack/`
   (see [Where it installs](#where-it-installs) — `<install-base>` defaults
   per platform and is overridable).
3. Run `pixi install` — conda-forge binaries + geocif/geoprepare from PyPI +
   octvi/pygeoutil from git + the PyPI-only ML libs.
4. Write an `activate` helper and verify the imports.

First run downloads a few hundred MB (once; cached afterwards).

### Enter the environment

```bash
# Linux / HPC
source <install-base>/geo-stack/activate.sh        # drops you into `pixi shell`

# Windows PowerShell
. <install-base>\geo-stack\activate.ps1
```

Or run one-off commands without a subshell:

```bash
pixi run --manifest-path <install-base>/geo-stack/pixi.toml python -c "import geocif"
```

### Where it installs

`<install-base>` is the **parent** directory; the environment itself goes into a
`geo-stack/` subdirectory inside it. `install.py` prints the resolved location as
`Install dir:` in its banner before it does any work, so you always see exactly
where things are going.

| Platform | Default `<install-base>` | Environment ends up in |
|---|---|---|
| UMD HPC | `/gpfs/data1/cmongp1/$USER` | `/gpfs/data1/cmongp1/$USER/geo-stack` |
| Windows | `%USERPROFILE%\geo-stack-env` | `C:\Users\<you>\geo-stack-env\geo-stack` |
| Linux | `~/geo-stack-env` | `~/geo-stack-env/geo-stack` |

On the HPC that default applies only when `/gpfs/data1/cmongp1` actually exists;
otherwise it falls back to `~/geo-stack-env`.

What ends up on disk:

```text
<install-base>/
├── geo-stack/                 <- everything the installer manages
│   ├── pixi.toml              <- generated manifest (rewritten on every run)
│   ├── pixi.lock              <- resolved versions
│   ├── activate.sh            <- Linux/HPC (activate.ps1 + activate.bat on Windows)
│   └── .pixi/envs/default/    <- the actual environment: python, gdal, geocif, ...
├── .pixi-cache/               <- HPC only: pixi package cache, kept off the quota'd /home
├── .pixi-home/                <- HPC only: the pixi binary itself
└── .tmp/                      <- only created if pixi had to be installed here
```

Apart from that tree, the only things touched outside `<install-base>` come from
pixi's own bootstrap the first time it runs: the pixi binary (`~/.pixi/bin`, or
`.pixi-home/` on the HPC) and a PATH line appended to your shell profile.

### Choosing a different location

Override the parent directory with `--install-base DIR`:

```bash
# HPC: put it in a project subdirectory instead of your $USER root
python install.py --install-base /gpfs/data1/cmongp1/$USER/envs --yes
#   -> /gpfs/data1/cmongp1/$USER/envs/geo-stack

# a big local disk rather than $HOME
python install.py --install-base /data/envs --yes
#   -> /data/envs/geo-stack

# right here, in the current directory
python install.py --install-base . --yes
#   -> ./geo-stack
```

```powershell
# Windows: a different drive
python install.py --install-base D:\envs --yes
#   -> D:\envs\geo-stack
```

The path is expanded and resolved before use, so `~`, relative paths, and
shell-expanded variables like `$USER` all work. The directory is created if it
doesn't exist. Re-running with the same `--install-base` is safe — the manifest
is rewritten and the environment updated in place, not duplicated.

---

## Installing pixi

`install.py` installs pixi for you when it isn't already on `PATH`, so you can
normally skip this section. Do it by hand if you want pixi in place beforehand,
or if the bootstrap failed.

<details open>
<summary><b>Linux</b> — including the UMD HPC and ARM / aarch64 boxes</summary>

```bash
curl -fsSL https://pixi.sh/install.sh | bash
exec $SHELL                 # or: export PATH="$HOME/.pixi/bin:$PATH"
pixi --version
```

Installs to `~/.pixi/bin` and appends the PATH line to your shell profile.

**On the UMD HPC, redirect pixi off `/home` first** — it is quota'd, and a
default install fails with `Disk quota exceeded`:

```bash
export PIXI_HOME=/gpfs/data1/cmongp1/$USER/.pixi-home
export PIXI_CACHE_DIR=/gpfs/data1/cmongp1/$USER/.pixi-cache
mkdir -p "$PIXI_HOME" "$PIXI_CACHE_DIR"
curl -fsSL https://pixi.sh/install.sh | bash
```

`install.py` does exactly this on HPC hosts and bakes both exports into the
generated `activate.sh`. On managed boxes that force a read-only `TMPDIR`
(pixi's installer then dies with `mktemp ... Permission denied`), it also points
`TMPDIR` at a writable directory first.

</details>

<details>
<summary><b>Windows</b></summary>

```powershell
powershell -ExecutionPolicy ByPass -NoProfile -Command "irm -useb https://pixi.sh/install.ps1 | iex"
```

Installs to `%USERPROFILE%\.pixi\bin`. Open a new terminal, then:

```powershell
pixi --version
```

If `pixi` still isn't found, add it for the current session:

```powershell
$env:PATH = "$env:USERPROFILE\.pixi\bin;$env:PATH"
```

</details>

<details>
<summary><b>macOS</b></summary>

```bash
curl -fsSL https://pixi.sh/install.sh | bash
exec $SHELL
pixi --version
```

Works on both Apple Silicon (`osx-arm64`) and Intel (`osx-64`).

> **`install.py` does not support macOS.** The workspace it generates declares
> `linux-64`, `linux-aarch64` and `win-64` only, so `pixi install` stops with
> *"The workspace does not support 'osx-arm64' on this machine."* pixi itself
> installs fine — the environment does not. Open an issue if you need a Mac
> build and the conda-forge deps can be checked against `osx-*`.

</details>

### Minimum version

`install.py` requires **pixi ≥ 0.43.0** — the release that renamed the manifest's
`[project]` table to `[workspace]`. An older pixi already on `PATH` fails on the
generated manifest with an opaque parse error, so the installer checks first and
stops with instructions. To upgrade:

```bash
pixi self-update
```

---

## Per-platform notes

### UMD HPC (gsapp)
```bash
ssh gsapp
cd /gpfs/data1/cmongp1/$USER
git clone https://github.com/ritviksahajpal/installer.git && cd installer
python install.py --yes
```
- The pixi package cache is redirected to `<install-base>/.pixi-cache` (keeps it
  off the quota'd `/home`).
- No `module load` — conda-forge's libgdal replaces `rh9/gdal/3.11.0`.

### Managed Linux / Jupyter boxes (e.g. AWS, often ARM)
These frequently force `TMPDIR` to a read-only path, which breaks pixi's own
installer (`mktemp ... Permission denied`). `install.py` sets a writable
`TMPDIR` (`<install-base>/.tmp`) before installing pixi, so it just works. If
`pixi` isn't found afterwards, add it to PATH:
```bash
export PATH="$HOME/.pixi/bin:$PATH"
```
On aarch64, three compiled backends are handled automatically:
`ydf`/`treeple` were removed from geocif; `rbeast`, `scikit-misc`, `pymupdf`,
`sklearn-genetic-opt` are taken from PyPI (which has ARM wheels); `cubist`
compiles from source with the box's gcc.

### Windows / generic Linux
Just `python install.py --yes`. pixi downloads its own Python 3.11 and all
conda-forge binaries — nothing needs to pre-exist.

---

## Developer (editable) install

Working on the source? Point the installer at your local clones:

```bash
python install.py \
    --editable-geocif      /path/to/geocif \
    --editable-geoprepare  /path/to/geoprepare \
    --editable-octvi       /path/to/octvi \
    --yes
```

Edits in those repos are live immediately (no reinstall). Anything not passed
`--editable-*` comes from PyPI (geocif, geoprepare) or git (octvi, pygeoutil).

---

## CLI reference

```text
--install-base DIR         Parent dir for the geo-stack env (default per platform).
--editable-geocif PATH     Install geocif editable from a local clone.
--editable-geoprepare PATH Install geoprepare editable from a local clone.
--editable-octvi PATH      Install octvi editable from a local clone.
--octvi-git URL            octvi git URL when not editable
                             (default: https://github.com/ritviksahajpal/octvi.git).
--platform NAME            Override detection: windows|umd_hpc|linux|macos|auto.
--yes / -y                 Skip the confirmation prompt (required for batch jobs).
```

---

## Day-to-day

```bash
pixi add <pkg>                 # add a conda-forge package to the env
pixi add --pypi <pkg>          # add a PyPI-only package
pixi update                    # bump within constraints, refresh the lock
pixi run <cmd>                 # run in the env without a subshell
```

You only re-run `install.py` to rebuild from scratch (it overwrites the manifest
and re-solves).

---

## What's installed

The generated `pixi.toml` pins the whole stack, validated to resolve across
`win-64`, `linux-64`, and `linux-aarch64`:

- **conda-forge** (`[dependencies]`): the geospatial stack (gdal, rasterio,
  fiona, pyproj, shapely, rtree, cartopy, geopandas, rioxarray, netcdf4, pyhdf,
  pyresample), numerics (numpy, pandas, scipy, xarray, matplotlib), compiled ML
  (catboost, scikit-learn, numba, statsmodels, shap, pytorch-cpu), pysal, GMT
  + PyGMT (so geocif's pygmt plot backend renders in-process), openpyxl (pandas'
  .xlsx engine), the dashboard/gee/spatial/narrative extras, and download
  clients (cdsapi, pymodis, earthaccess, pydap).
- **PyPI** (`[pypi-dependencies]`): `geocif` (≥0.4.933) and `geoprepare`
  (≥0.6.286), plus PyPI-only / no-conda-ARM-wheel libs (tabpfn, tabicl, cubist,
  merf, Rbeast, sklearn-genetic-opt, aquacrop, pymupdf, …).
- **git**: `octvi` (the fork carrying the GCVI Int32 fix), `pygeoutil`, and
  `tabpfn-gsa` (ruid7181/TabPFN-GSA — not on PyPI; backs geocif's
  `model="tabpfn_gsa"`).

> **octvi note:** the default `--octvi-git` is `ritviksahajpal/octvi`. Make sure
> that fork has the GCVI Int32 fix; upstream `nasaharvest/octvi` does not, and an
> unfixed octvi produces wrong GCVI output.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `mktemp: … Permission denied` while installing pixi | Handled automatically (writable `TMPDIR`); if it still fails, `export TMPDIR=$HOME/tmp` and re-run |
| `pixi: command not found` after install | `export PATH="$HOME/.pixi/bin:$PATH"` (add to `~/.bashrc`) |
| `libcurl.so.4: no version information available` | Harmless warning from a base-conda libcurl — ignore |
| Home quota fills during install | Handled on HPC (cache on `/gpfs`); elsewhere set `PIXI_CACHE_DIR=<big-disk>` |
| `cubist` build fails on ARM | Report it — it can be gated off aarch64 like ydf/treeple were |
| GCVI output looks wrong | You're on an unfixed octvi — use the fork with the Int32 fix |

---

## License

MIT — see LICENSE.
