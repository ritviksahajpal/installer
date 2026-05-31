# geocif + geoprepare Installer

Cross-platform installer for the `geocif` ML crop-yield model and its
`geoprepare` preprocessing dependency. Detects the platform at runtime and
provisions a Python virtual environment with all dependencies resolved via
`uv` and `geocif`'s `pyproject.toml`.

Supported platforms:
- **Windows** (local)
- **UMD HPC** (`gsapp`, with Lmod modules)
- **Generic Linux** (no module system required)
- **macOS** (best-effort; macOS GDAL wheels are sparse)

## Quick start

```bash
# Linux / macOS
python3 install.py

# Windows (PowerShell or cmd)
py -3 install.py
```

The installer prompts for confirmation and uses sensible defaults per platform.
Pass `--yes` to skip the prompt.

## Common flags

```text
--install-base DIR         Parent dir for the env. Default:
                             UMD HPC : /gpfs/data1/cmongp1/$USER
                             Windows : %USERPROFILE%\geo-stack-env
                             Linux/mac: ~/geo-stack-env
--editable PATH            Install geocif as editable from a local clone.
--editable-geoprepare PATH Install geoprepare as editable from a local clone.
--platform NAME            Override detection: windows|umd_hpc|linux|macos|auto.
--write-shell-rc           On Linux/macOS, add `~/.local/bin` to ~/.bashrc
                           (always done on UMD HPC).
--yes / -y                 Skip the confirmation prompt.
```

## Per-platform behavior

| | Windows | UMD HPC | Generic Linux | macOS |
|---|---|---|---|---|
| Python | 3.11 (system if found, else uv installs) | module `python/3.12` (3.11 fallback) | 3.11 (system if found, else uv installs) | 3.11 (system if found, else uv installs) |
| GDAL | Gohlke `cp311` wheel (via `[tool.uv.sources]` in geocif/pyproject.toml) | `module load rh9/gdal/3.11.0` + RPATH | PyPI wheel `gdal==3.11.0` | PyPI wheel |
| `~/.bashrc` | not touched | minimal: `export PATH="$HOME/.local/bin:$PATH"` | only with `--write-shell-rc` | only with `--write-shell-rc` |
| Activation helper | `activate.ps1` + `activate.bat` | `activate.sh` (with module loads) | `activate.sh` | `activate.sh` |

## Activation

After install, the script prints the activation command. Examples:

```bash
# Linux / macOS / HPC
source ~/geo-stack-env/geo-stack/activate.sh

# Windows PowerShell
. C:\Users\you\geo-stack-env\geo-stack\activate.ps1

# Windows cmd
C:\Users\you\geo-stack-env\geo-stack\activate.bat
```

The `activate.sh` on UMD HPC handles conda deactivation, module loading, and
`LD_LIBRARY_PATH` prep for libgdal. The local-Linux/macOS version just sources
the venv and clears `PYTHONPATH`.

## Editable development install

Working on geocif and geoprepare locally? Point the installer at your clones:

```bash
python install.py \
    --editable d:/Users/ritvik/projects/geocif \
    --editable-geoprepare d:/Users/ritvik/projects/geoprepare
```

Edits in those repos are visible immediately without reinstall.

## What's installed

`install.py` calls `uv pip install geocif` (or `-e <path>`). Everything else is
resolved by uv from
[`geocif/pyproject.toml`](https://github.com/ritviksahajpal/geocif/blob/main/pyproject.toml):

- **Geospatial**: gdal, rasterio, geopandas, shapely, pyproj, rtree, fiona
- **Climate/array**: xarray (>=2026.2.0), pooch, icclim, arrow
- **ML**: catboost, shap, optuna, tabpfn, tabicl, statsmodels, scikit-misc
- **Vis**: seaborn, palettable, scienceplots
- **Boruta**, **choix**, **logzero**

Plus `geoprepare` (>=0.6.129) as a transitive dep.

CUDA / nvidia-* packages are excluded by `geocif/pyproject.toml`'s
`[tool.uv] override-dependencies`. To install CUDA torch separately:

```bash
uv pip install torch --index-url https://download.pytorch.org/whl/cu128
```

## UMD HPC details

The installer detects UMD HPC by the presence of both:
1. Lmod (`$LMOD_CMD` or `lmod` on PATH)
2. `/gpfs/data1/cmongp1/` directory

On UMD HPC it will:
- `module purge`
- Try `python/3.12.9/anaconda`, `python/3.12/anaconda`, then 3.11 variants
- Try `rh9/gdal/3.11.0`, `gdal/3.11.0`, `gdal/3.11`, `gdal`
- Capture `gdal-config --libs` for the lib dir
- Set `LD_LIBRARY_PATH` and `LDFLAGS=-L<dir> -Wl,-rpath,<dir>` so the venv's
  `_gdal*.so` links against the module's libgdal (not the anaconda module's
  bundled, older copy)
- Write a minimal `~/.bashrc` block (just `~/.local/bin` on PATH for uv)

To override detection on a non-UMD cluster with the same layout, pass
`--platform umd_hpc` explicitly.

## Updating

```bash
source <install-base>/geo-stack/activate.sh  # or activate.ps1 on Windows
uv pip install --upgrade geocif
```

## Legacy bash installer

`install_geo_environment.sh` is the previous HPC-only bash installer. It is
deprecated but kept as a fallback for HPC hosts where no Python is available
before module load. New installs should use `install.py`.

## License

MIT — see LICENSE.
