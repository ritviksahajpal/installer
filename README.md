# Python Geospatial Environment Installer

A robust installer script for setting up a comprehensive Python environment with 200+ geospatial, climate, and scientific computing packages on HPC clusters and Linux systems.

## Features

- 🚀 **Fast Installation**: Uses UV package manager (10-100x faster than pip)
- 🌍 **200+ Packages**: Complete geospatial and scientific Python stack
- 🖥️ **HPC Optimized**: Automatic module detection and loading
- 💾 **Smart Storage**: Installs to data partitions, not home directory
- 🔧 **Version Matching**: Automatically matches Python GDAL to system GDAL
- ✅ **Verification**: Built-in package verification after installation

## Quick Start

### For HPC Systems

```bash
# Download the installer
wget https://raw.githubusercontent.com/ritviksahajpal/installer/main/install_geo_environment.sh

# Run with your paths
bash install_geo_environment.sh "/gpfs/data1/cmongp1/$USER" "/path/to/your/project"
```

### For Cloud/Generic Linux

```bash
# Download the cloud version
wget https://raw.githubusercontent.com/ritviksahajpal/installer/main/install_geo_environment_cloud.sh

# Run with local paths
bash install_geo_environment_cloud.sh "$HOME/geo-env" "$HOME/projects"
```

## What Gets Installed

### Core Geospatial Stack
- **GDAL** - Geospatial Data Abstraction Library
- **Rasterio** - Raster data I/O
- **GeoPandas** - Geospatial pandas operations
- **Shapely** - Geometric operations
- **Cartopy** - Cartographic projections
- **Fiona** - Vector data I/O

### Climate & Weather Tools
- **XArray** - N-dimensional labeled arrays
- **NetCDF4** - NetCDF file support
- **cfgrib** - GRIB file handling
- **xclim** - Climate indices calculation
- **ERA5/ECMWF tools** - Weather data access

### Machine Learning & AI
- **PyTorch** - Deep learning framework
- **Scikit-learn** - Machine learning library
- **CatBoost** - Gradient boosting
- **SHAP** - Model interpretability
- **Optuna** - Hyperparameter optimization

### Data Processing
- **Pandas** - Data analysis
- **NumPy** - Numerical computing
- **Dask** - Parallel computing
- **SciPy** - Scientific computing
- **Statsmodels** - Statistical modeling

### Cloud & Remote Sensing
- **Earth Engine API** - Google Earth Engine
- **Boto3** - AWS services
- **Azure Storage** - Azure blob storage
- **Sentinel/Landsat tools** - Satellite data

### Custom Packages
- **octvi** - Vegetation indices
- **pygeoutil** - Geospatial utilities

## Requirements

### System Requirements
- Linux OS (RHEL, Ubuntu, Debian, Amazon Linux)
- Python 3.9+ (3.12 recommended)
- 10GB free disk space
- Internet connection

### HPC Specific
- Module system (`module` command)
- GDAL module available
- Access to data partition (e.g., `/gpfs/`)

## Installation Guide

### Step 1: Choose Your Version

- **HPC Version** (`install_geo_environment.sh`): For clusters with module systems
- **Cloud Version** (`install_geo_environment_cloud.sh`): For AWS, Azure, GCP, or local Linux

### Step 2: Run the Installer

#### HPC Installation

```bash
# The installer will automatically:
# 1. Load Python module (3.12 or 3.11)
# 2. Load GDAL module
# 3. Create virtual environment
# 4. Install all packages

bash install_geo_environment.sh "/data/partition/$USER" "/project/path"
```

#### Cloud/Local Installation

```bash
# For systems without module support
bash install_geo_environment_cloud.sh "$HOME/geo-env" "$HOME/projects"
```

### Step 3: Activate Your Environment

#### HPC Systems
```bash
module purge
module load python/3.12.9/anaconda  # Or your Python module
module load rh9/gdal/3.11.0        # Or your GDAL module
source /path/to/installation/geo-stack/.venv/bin/activate
```

#### Cloud/Local Systems
```bash
source ~/geo-env/geo-stack/.venv/bin/activate
```

## Usage Examples

### Basic Usage
```python
# After activation
python
>>> import rasterio
>>> import geopandas as gpd
>>> import xarray as xr
>>> from osgeo import gdal
>>> import torch
>>> # All packages ready to use!
```

### Processing Satellite Data
```python
import rasterio
import numpy as np
from rasterio.plot import show

# Open a GeoTIFF
with rasterio.open('satellite_image.tif') as src:
    data = src.read()
    metadata = src.meta
```

### Climate Data Analysis
```python
import xarray as xr
import cartopy.crs as ccrs
import matplotlib.pyplot as plt

# Load NetCDF data
ds = xr.open_dataset('climate_data.nc')
ds.temperature.plot()
```

## Configuration Options

### Custom Installation Paths

Edit the script to change default paths:
```bash
# In the script, modify:
ENV_NAME="geo-stack"  # Change environment name
INSTALL_BASE="/custom/path"  # Change installation location
```

### Python Version Selection

The installer automatically selects the best Python version. To force a specific version:
```bash
# Load your preferred Python before running
module load python/3.11.7/anaconda
bash install_geo_environment.sh "/path" "/project"
```

## Troubleshooting

### GDAL Version Mismatch
```bash
# Check system GDAL version
gdalinfo --version

# Install matching Python bindings
source /path/to/env/.venv/bin/activate
uv pip install gdal==3.11.0  # Match your system version
```

### Module Not Found
```bash
# List available modules
module avail python
module avail gdal

# Load appropriate modules
module load python/3.12
module load gdal/3.11
```

### Permission Issues
```bash
# Check write permissions
ls -la /installation/path/

# Use a different path if needed
bash install_geo_environment.sh "$HOME/local" "$HOME/projects"
```

### Package Installation Failures
```bash
# Activate environment and install manually
source /path/to/env/.venv/bin/activate
uv pip install problem_package
```

## Directory Structure

After installation, you'll have:
```
installation_path/
├── geo-stack/
│   ├── .venv/                 # Python virtual environment
│   ├── requirements.txt       # Package list
│   └── installation_info.txt  # Installation details
├── .uv-cache/                 # UV package cache
└── .pip-cache/                # Pip cache
```

## Performance

- **With UV**: 10-15 minutes for complete installation
- **Without UV**: 1-2 hours (fallback to pip)
- **Disk usage**: ~8-10GB
- **Package count**: 200+

## Updating Packages

```bash
# Activate environment first
source /path/to/env/.venv/bin/activate

# Update specific package
uv pip install --upgrade package_name

# Update all packages
uv pip install --upgrade -r /path/to/geo-stack/requirements.txt
```

## Contributing

Issues and pull requests welcome! Please test any changes on both HPC and cloud environments.

## Version Compatibility

| Component | Version | Notes |
|-----------|---------|-------|
| Python | 3.9-3.12 | 3.12 recommended |
| GDAL | 3.4-3.11 | Must match system |
| CUDA | 11.8/12.1 | For PyTorch GPU |
| OS | Linux | RHEL, Ubuntu, Debian |

## Common Use Cases

- **Agricultural Monitoring**: Crop classification, yield prediction
- **Climate Analysis**: Temperature trends, precipitation patterns
- **Remote Sensing**: Satellite image processing, change detection
- **Geospatial ML**: Deep learning on raster data
- **Environmental Modeling**: Watershed analysis, carbon mapping

## Support

For issues specific to:
- **Installation script**: Open an issue on this repository
- **Individual packages**: Consult package documentation
- **HPC configuration**: Contact your system administrator

## License

MIT License - See LICENSE file for details

## Acknowledgments

This installer aggregates tools from the open-source geospatial community including:
- OSGeo Foundation (GDAL, GEOS)
- NumFOCUS (NumPy, Pandas, XArray)
- PyTorch Foundation
- Individual package maintainers

---

**Repository**: https://github.com/ritviksahajpal/installer  
**View Scripts**: 
- [HPC Version](https://github.com/ritviksahajpal/installer/blob/main/install_geo_environment.sh)
- [Cloud Version](https://github.com/ritviksahajpal/installer/blob/main/install_geo_environment_cloud.sh)  
**Author**: Ritvik Sahajpal  
**Last Updated**: December 2024
