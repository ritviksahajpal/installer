# geocif + geoprepare + octvi installer (pixi)

Cross-platform installer that provisions a self-contained
[pixi](https://pixi.sh) environment for the `geocif` crop-yield model, its
`geoprepare` preprocessor, and the `octvi` NDVI/GCVI downloader.

**No conda, no uv, no system GDAL module, no CUDA, no compiler gymnastics.**
conda-forge ships its own libgdal + a CPU PyTorch build + every binary dep, so a
single `pixi install` does the whole job. One lockfile reproduces the *identical*
environment on every platform.

Supported platforms (auto-detected):

| | Windows | UMD HPC (gsapp) | Generic / managed Linux | Linux ARM (aarch64) | macOS |
|---|---|---|---|---|---|
| GDAL / torch | conda-forge | conda-forge | conda-forge | conda-forge | conda-forge |
| module load? | — | **no** | — | — | — |
| special handling | — | cache → `/gpfs` | writable `TMPDIR` | ydf/treeple/rbeast handled | best-effort |

---

## Quick start

```bash
git clone https://github.com/ritviksahajpal/installer.git
cd installer
python install.py --yes
```

`install.py` (stdlib-only, needs Python 3.8+ to bootstrap) will:

1. Install pixi if it's not already on PATH.
2. Write a validated `pixi.toml` into `<install-base>/geo-stack/`.
3. Run `pixi install` — conda-forge binaries + geocif/geoprepare from PyPI +
   octvi/pygeoutil from git + the PyPI-only ML libs.
4. Write an `activate` helper and verify the imports.

First run downloads a few hundred MB (once; cached afterwards).

### Enter the environment

```bash
# Linux / macOS / HPC
source <install-base>/geo-stack/activate.sh        # drops you into `pixi shell`

# Windows PowerShell
. <install-base>\geo-stack\activate.ps1
```

Or run one-off commands without a subshell:

```bash
pixi run --manifest-path <install-base>/geo-stack/pixi.toml python -c "import geocif"
```

### Default install locations

| Platform | `<install-base>` |
|---|---|
| UMD HPC | `/gpfs/data1/cmongp1/$USER` |
| Windows | `%USERPROFILE%\geo-stack-env` |
| Linux / macOS | `~/geo-stack-env` |

Override with `--install-base DIR`.

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

### Managed Linux / Jupyter boxes (e.g. AWS "terrahub", often ARM)
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

### Windows / generic Linux / macOS
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
  (catboost, scikit-learn, numba, statsmodels, shap, pytorch-cpu), pysal, the
  dashboard/gee/spatial/narrative extras, and download clients (cdsapi, pymodis,
  earthaccess, pydap).
- **PyPI** (`[pypi-dependencies]`): `geocif` (≥0.4.880) and `geoprepare`
  (≥0.6.286), plus PyPI-only / no-conda-ARM-wheel libs (tabpfn, tabicl, cubist,
  merf, pyeogpr, Rbeast, sklearn-genetic-opt, aquacrop, pymupdf, …).
- **git**: `octvi` (the fork carrying the GCVI Int32 fix) and `pygeoutil`.

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

## Legacy installer

`install_geo_environment.sh` is the previous **uv + Lmod-module + GDAL-source-build**
HPC installer. It is superseded by this pixi `install.py` and kept only for
historical reference. New installs should use `install.py`.

---

## License

MIT — see LICENSE.
