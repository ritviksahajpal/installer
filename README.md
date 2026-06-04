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

**Conda is NOT required** on any platform. The installer uses [uv](https://github.com/astral-sh/uv) for Python and venv management; conda interactions are limited to *cleaning up* its state on HPC where the system auto-activates a base env.

---

## Run on UMD HPC (gsapp)

### 1. First-time install

```bash
ssh gsapp                                       # login
cd /gpfs/data1/cmongp1/$USER                    # or your project area
git clone https://github.com/ritviksahajpal/installer.git
cd installer
python install.py --yes
```

> First run takes ~3–5 minutes (downloads uv + Python 3.12.9 module + ~150 PyPI packages + a one-time source build of GDAL bindings).

### 2. Activate the env (run in every new shell)

```bash
source /gpfs/data1/cmongp1/$USER/geo-stack/activate.sh
```

### 3. Install additional Python libraries (after activating)

```bash
uv pip install <package>                # add a new package
uv pip install --upgrade <package>      # upgrade an existing one
```

---

To **update** the installer later (without rebuilding the venv):
```bash
cd /gpfs/data1/cmongp1/$USER/installer
git pull
```

To **rebuild the venv** (after a `git pull`, or if it gets broken):
```bash
python install.py --yes        # auto-deletes the old venv and rebuilds
```

---

## Run on Windows (local)

### 1. First-time install

```powershell
git clone https://github.com/ritviksahajpal/installer.git
cd installer
python install.py --yes
```

### 2. Activate the env (run in every new shell)

```powershell
# PowerShell
. C:\Users\<you>\geo-stack-env\geo-stack\activate.ps1

# cmd.exe
C:\Users\<you>\geo-stack-env\geo-stack\activate.bat
```

### 3. Install additional Python libraries (after activating)

```powershell
uv pip install <package>                # add a new package
uv pip install --upgrade <package>      # upgrade an existing one
```

> **Deactivate** with `deactivate` (PowerShell — a function defined by activate.ps1) or the `deactivate.bat` script in the env dir (cmd.exe — do **not** use plain `deactivate` in cmd; conda hijacks it).

---

## Run on generic Linux / macOS

### 1. First-time install

```bash
git clone https://github.com/ritviksahajpal/installer.git
cd installer
python install.py --yes
```

### 2. Activate the env (run in every new shell)

```bash
source ~/geo-stack-env/geo-stack/activate.sh
```

### 3. Install additional Python libraries (after activating)

```bash
uv pip install <package>                # add a new package
uv pip install --upgrade <package>      # upgrade an existing one
```

> If you don't have Python 3.11 on PATH, uv will download a standalone build during install.

---

## Common flags

```text
--install-base DIR         Parent dir for the env. Default:
                             UMD HPC : /gpfs/data1/cmongp1/$USER
                             Windows : %USERPROFILE%\geo-stack-env
                             Linux/macOS: ~/geo-stack-env
--editable PATH            Install geocif as editable from a local clone.
--editable-geoprepare PATH Install geoprepare as editable from a local clone.
--platform NAME            Override detection: windows|umd_hpc|linux|macos|auto.
--write-shell-rc           On Linux/macOS, add `~/.local/bin` to ~/.bashrc
                           (always done on UMD HPC).
--yes / -y                 Skip confirmation prompts (required for batch jobs).
```

---

## Per-platform behavior

| | Windows | UMD HPC | Generic Linux | macOS |
|---|---|---|---|---|
| Python | 3.11 (system if found, else uv installs) | module `python/3.12.9/anaconda` (3.11.7 fallback) | 3.11 (system if found, else uv installs) | 3.11 (system if found, else uv installs) |
| GDAL | Gohlke `cp311` wheel pre-installed | `rh9/gdal/3.11.0` module + source build with embedded RPATH | PyPI wheel `gdal==3.11.0` | PyPI wheel |
| `~/.bashrc` | not touched | minimal: `export PATH="$HOME/.local/bin:$PATH"` | only with `--write-shell-rc` | only with `--write-shell-rc` |
| Activation helpers | `activate.ps1`, `activate.bat`, `deactivate.bat` | `activate.sh` | `activate.sh` | `activate.sh` |
| Conda touched? | No | Only to *deactivate* if base is active | No | No |

---

## What's installed

`install.py` calls `uv pip install geocif`. Everything else is resolved by uv from
[`geocif/pyproject.toml`](https://github.com/ritviksahajpal/geocif/blob/main/pyproject.toml):

- **Geospatial**: gdal, rasterio, geopandas, shapely, pyproj, rtree, fiona, pyogrio
- **Climate/array**: xarray (>=2026.2.0), pooch, icclim, arrow, cftime, netcdf4
- **ML**: catboost, shap, optuna, tabpfn, tabicl, statsmodels, scikit-misc, scikit-learn, torch
- **Vis**: seaborn, palettable, scienceplots, cartopy, plotly
- **Other**: boruta, choix, logzero, Rbeast

Plus `geoprepare` and `pygeoutil` (the latter via git, since it's not on PyPI).

**CUDA / nvidia-** packages are excluded* by `geocif/pyproject.toml`'s `[tool.uv] override-dependencies`. To add CUDA torch:

```bash
uv pip install torch --index-url https://download.pytorch.org/whl/cu128
```

---

## Activation flow details

### UMD HPC

`activate.sh` does this each time you source it:

1. Strips conda from PATH (uses `conda deactivate` if available, then filters out user-conda dirs as a safety net) and unsets `CONDA_*` env vars
2. Bootstraps the `module` command (sources `/etc/profile.d/modules.sh` if not already a function)
3. `module purge` then `module load python/3.12.9/anaconda` + `module load rh9/gdal/3.11.0`
4. Prepends the GDAL module's `lib/` to `LD_LIBRARY_PATH` (so the venv's `_gdal*.so` finds the right `libgdal.so`)
5. Sources the venv's `bin/activate`
6. Sanity-checks `from osgeo import gdal`

You don't need to `conda deactivate` first — `activate.sh` handles it. You don't need to load any modules first — `activate.sh` handles that too.

### Windows

`activate.bat` (cmd) and `activate.ps1` (PowerShell) are *self-contained* — they set `VIRTUAL_ENV`, prepend the venv's `Scripts` dir to PATH, decorate the prompt, and don't depend on uv shipping an internal activate script (which it doesn't always).

`deactivate.bat` is shipped alongside (cmd.exe doesn't get a function-based `deactivate` like PowerShell does, and the system `deactivate` is hijacked by conda).

---

## Editable / development install

Working on geocif or geoprepare locally? Point the installer at your clones:

```bash
python install.py \
    --editable /path/to/your/geocif \
    --editable-geoprepare /path/to/your/geoprepare \
    --yes
```

Edits in those repos are visible immediately without reinstall.

---

## Troubleshooting

### "Stuck" at `[!] Existing venv found at ...`
GPFS metadata operations are slow. `shutil.rmtree` on a venv with 100k+ files can take 2–10 minutes. Either wait, or kill + pre-clean (much faster):

```bash
rm -rf <install-base>/geo-stack
python install.py --yes
```

### `Exception: Python bindings of GDAL X require at least libgdal X, but Y was found` (HPC)
The GDAL module didn't actually load — `gdal-config` is finding the system `/usr/lib64/libgdal.so` instead of the module's. Causes:
- Running from a head node where modules are restricted — try a compute node
- Module-bootstrap step failed silently — re-run with output captured: `python install.py --yes 2>&1 | tee install.log`, then check for the `--- module list after load ---` diagnostic

### `from osgeo import gdal` fails: "undefined symbol" (HPC)
The `_gdal*.so` was linked against a different `libgdal` than what's on `LD_LIBRARY_PATH`. Confirm RPATH is baked in:
```bash
readelf -d <install-base>/geo-stack/.venv/lib/python3.12/site-packages/osgeo/_gdal*.so | grep -iE 'rpath|runpath'
```
Should show the GDAL module's lib dir. If empty, the GDAL bindings were installed without source-build (probably via a wheel) — re-run install.py.

### `deactivate` doesn't work on Windows cmd
Conda hijacks the `deactivate` command name on Windows. Use the `deactivate.bat` script in your install dir instead:
```cmd
%USERPROFILE%\geo-stack-env\geo-stack\deactivate.bat
```

### Non-interactive shell (SLURM batch)
The installer's `Continue? [y/N]` prompt would hang. Pass `--yes` to skip all prompts. If you forgot and it hung, kill it and re-run.

---

## Updating packages later

See the "Install additional Python libraries" snippet in your platform's section above for the day-to-day `uv pip install` workflow. To upgrade the full stack:

```bash
uv pip install --upgrade --reinstall geocif      # geocif + all transitives
```

You only need to re-run `install.py` if you want to rebuild from scratch (e.g., switching Python versions, recovering from a broken env).

---

## Legacy bash installer

`install_geo_environment.sh` is the previous HPC-only bash installer. It is **deprecated** but kept as a fallback for HPC hosts where no Python is available before module load. New installs should use `install.py`.

---

## License

MIT — see LICENSE.
