# Python Geospatial Environment Installer

A robust installer script for setting up a comprehensive Python environment with 200+ geospatial, climate, and scientific computing packages on HPC clusters. Designed for running **geocif** and **geoprepare** on UMD gsapp systems.

## Quick Start (gsapp HPC)

```bash
# 1. Download the installer
wget https://raw.githubusercontent.com/ritviksahajpal/installer/main/install_geo_environment.sh

# 2. Run it (interactive — will prompt for paths)
bash install_geo_environment.sh

# Or run with arguments to skip prompts:
bash install_geo_environment.sh "/gpfs/data1/cmongp1/$USER" "/gpfs/data1/cmongp1/GEOGLAM/Code/Code/preprocess"

# 3. Log out and back in (so ~/.bashrc changes take effect), then activate:
source /gpfs/data1/cmongp1/$USER/geo-stack/activate.sh

# 4. Navigate to your working directory and run geocif/geoprepare
cd /gpfs/data1/cmongp1/GEOGLAM/Code/Code/preprocess
```

## What the Installer Does

1. **Installs UV** — a fast Python package manager (10-100x faster than pip)
2. **Detects and loads modules** — finds the best available Python and GDAL modules on the cluster
3. **Creates a virtual environment** — isolated from conda and system Python
4. **Installs 200+ packages** — including geocif, geoprepare, and all their dependencies
5. **Generates `activate.sh`** — a self-contained activation script that handles modules, conda conflicts, and environment setup
6. **Configures `~/.bashrc`** — adds a clearly marked block that deactivates conda and sets up UV PATH for future sessions

## Activation

After installation, always activate with:

```bash
source /gpfs/data1/cmongp1/$USER/geo-stack/activate.sh
```

The activation script automatically:
- Deactivates any active conda environments (prevents conflicts)
- Loads the correct Python and GDAL modules (detected during install)
- Sets `PYTHONNOUSERSITE=1` and clears `PYTHONPATH`
- Activates the virtual environment
- Runs a GDAL sanity check

It also guards against double-activation — running it twice is harmless.

## What Gets Installed

### Core Geospatial Stack
- **GDAL** — Geospatial Data Abstraction Library (matched to system version)
- **Rasterio** — Raster data I/O
- **GeoPandas** — Geospatial pandas operations
- **Shapely** — Geometric operations
- **Cartopy** — Cartographic projections
- **Fiona** — Vector data I/O

### Climate & Weather Tools
- **XArray** — N-dimensional labeled arrays
- **NetCDF4** — NetCDF file support
- **cfgrib** — GRIB file handling
- **xclim** — Climate indices calculation
- **cdsapi / ecmwf tools** — Weather data access

### Machine Learning & AI
- **PyTorch** — Deep learning framework
- **Scikit-learn** — Machine learning library
- **CatBoost** — Gradient boosting
- **SHAP** — Model interpretability
- **Optuna** — Hyperparameter optimization

### GEOGLAM Packages
- **geocif** — ML crop yield model
- **geoprepare** — Geospatial data preprocessing
- **octvi** — Vegetation indices
- **pygeoutil** — Geospatial utilities

### Data Processing
- **Pandas**, **NumPy**, **Dask**, **SciPy**, **Statsmodels**

### Cloud & Remote Sensing
- **Earth Engine API**, **Boto3** (AWS), **Azure Storage**

## What Changes in ~/.bashrc

The installer adds a clearly delimited block to `~/.bashrc`:

```bash
# BEGIN geo-stack installer
conda deactivate 2>/dev/null || true
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
export UV_CACHE_DIR="/gpfs/data1/cmongp1/$USER/.uv-cache"
export PYTHONNOUSERSITE=1
unset PYTHONPATH
# END geo-stack installer
```

This block is **idempotent** — re-running the installer replaces it rather than duplicating it. It also cleans up legacy single-line additions from older installer versions.

## Requirements

- Linux (gsapp HPC nodes)
- Module system (`module` command)
- Python 3.9+ module available (3.12 recommended)
- GDAL module available
- ~10GB free disk space on the data partition
- Internet connection (for downloading packages)

## Directory Structure

After installation:
```
/gpfs/data1/cmongp1/$USER/
├── geo-stack/
│   ├── .venv/                 # Python virtual environment
│   ├── activate.sh            # Activation script (use this!)
│   ├── requirements.txt       # Package list
│   └── installation_info.txt  # Installation details and troubleshooting
├── .uv-cache/                 # UV package cache
└── .pip-cache/                # Pip cache
```

## Troubleshooting

### GDAL import fails after activation
```bash
# Check what GDAL version the module provides
module load rh9/gdal/3.11.0   # or whatever module was detected
gdalinfo --version

# Reinstall matching Python bindings
source /gpfs/data1/cmongp1/$USER/geo-stack/activate.sh
uv pip install gdal==3.11.0   # match the version above
```

### Conda is interfering
The installer's `~/.bashrc` block deactivates conda automatically. If you still see `(base)` in your prompt after a fresh login, check that the geo-stack block appears **after** the conda initialization block in `~/.bashrc`.

### Double `(geo-stack)` prompt
The new `activate.sh` has a guard against this. If you see it with an older install, re-run the installer to regenerate `activate.sh`.

### Package installation failures
```bash
source /gpfs/data1/cmongp1/$USER/geo-stack/activate.sh
uv pip install package_name
```

### Permission issues
```bash
# The installer needs write access to INSTALL_BASE
# Default: /gpfs/data1/cmongp1/$USER
ls -la /gpfs/data1/cmongp1/$USER/
```

## Updating Packages

```bash
source /gpfs/data1/cmongp1/$USER/geo-stack/activate.sh

# Update a specific package
uv pip install --upgrade geocif

# Update all packages
uv pip install --upgrade -r /gpfs/data1/cmongp1/$USER/geo-stack/requirements.txt
```

## For Other Users on gsapp

Any user on gsapp can run the installer with their own paths:

```bash
wget https://raw.githubusercontent.com/ritviksahajpal/installer/main/install_geo_environment.sh
bash install_geo_environment.sh "/gpfs/data1/cmongp1/$USER" "/gpfs/data1/cmongp1/GEOGLAM/Code/Code/preprocess"
```

The installer will detect the available modules on the system and configure everything automatically. Each user gets their own independent environment.

## License

MIT License - See LICENSE file for details
