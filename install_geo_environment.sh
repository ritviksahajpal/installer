#!/bin/bash

# ============================================
# Python Geospatial Environment Installer
# HPC/Cluster Version with Module Support
# ============================================

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored messages
print_success() { echo -e "${GREEN}✓ $1${NC}"; }
print_error() { echo -e "${RED}✗ $1${NC}"; }
print_warning() { echo -e "${YELLOW}⚠ $1${NC}"; }
print_info() { echo -e "→ $1"; }

# ============================================
# CONFIGURATION SECTION
# ============================================

# Default paths (can be overridden by command line arguments)
INSTALL_BASE=""
WORK_DIR=""

# Use command line arguments if provided
if [ $# -eq 2 ]; then
    INSTALL_BASE="$1"
    WORK_DIR="$2"
fi

# Interactive prompts if paths not set
if [ -z "$INSTALL_BASE" ]; then
    echo "============================================"
    echo "   Python Geospatial Environment Installer"
    echo "   HPC/Cluster Version"
    echo "============================================"
    echo ""
    echo "Please provide installation paths:"
    echo ""
    echo "Example paths:"
    echo "  Data partition: /gpfs/data1/cmongp1/\$USER"
    echo "  Working directory: /gpfs/data1/cmongp1/GEOGLAM/Code/Code/preprocess"
    echo ""
    read -p "Enter your data partition path: " INSTALL_BASE
    read -p "Enter your working directory path: " WORK_DIR
fi

# Expand $USER variable if present
INSTALL_BASE="${INSTALL_BASE//\$USER/$USER}"
WORK_DIR="${WORK_DIR//\$USER/$USER}"

# Environment name
ENV_NAME="geo-stack"
PYTHON_VERSION=""  # Will be detected from module
GDAL_VERSION=""    # Will be detected from system
PYTHON_CMD=""      # Will be set based on loaded module

# ============================================
# VALIDATION
# ============================================

echo ""
echo "============================================"
echo "Installation Configuration:"
echo "============================================"
echo "Install location: $INSTALL_BASE"
echo "Working directory: $WORK_DIR"
echo "Environment name: $ENV_NAME"
echo "============================================"
echo ""

# Check if paths are set
if [ -z "$INSTALL_BASE" ] || [ -z "$WORK_DIR" ]; then
    print_error "Installation paths not set!"
    exit 1
fi

# Confirm with user
read -p "Continue with installation? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Installation cancelled."
    exit 0
fi

# ============================================
# LOAD SYSTEM MODULES
# ============================================

print_info "Loading system modules..."

if command -v module &> /dev/null; then
    module purge 2>/dev/null || true
    
    # Load Python module - prefer 3.12, fallback to 3.11
    print_info "Looking for Python module..."
    PYTHON_LOADED=false
    
    # Try Python 3.12 first (preferred)
    for py_module in "python/3.12.9/anaconda" "python/3.12/anaconda" "python/3.12"; do
        if module load $py_module 2>/dev/null; then
            print_success "Loaded Python module: $py_module"
            PYTHON_LOADED=true
            PYTHON_CMD=python3.12
            break
        fi
    done
    
    # If 3.12 not found, try 3.11
    if [ "$PYTHON_LOADED" = false ]; then
        for py_module in "python/3.11.7/anaconda" "python/3.11/anaconda" "python/3.11"; do
            if module load $py_module 2>/dev/null; then
                print_success "Loaded Python module: $py_module"
                PYTHON_LOADED=true
                PYTHON_CMD=python3.11
                break
            fi
        done
    fi
    
    # If still no Python module, try default
    if [ "$PYTHON_LOADED" = false ]; then
        if module load python 2>/dev/null; then
            print_success "Loaded default Python module"
            PYTHON_LOADED=true
            PYTHON_CMD=python3
        fi
    fi
    
    if [ "$PYTHON_LOADED" = false ]; then
        print_warning "No Python module found. Using system Python."
        print_info "Available Python modules:"
        module avail python 2>&1 | grep -i python || true
        PYTHON_CMD=python3
    fi
    
    # Load GDAL module
    print_info "Looking for GDAL module..."
    GDAL_LOADED=false
    
    # Try common GDAL module names
    for gdal_module in "rh9/gdal/3.11.0" "gdal/3.11.0" "gdal/3.11" "gdal"; do
        if module load $gdal_module 2>/dev/null; then
            print_success "Loaded GDAL module: $gdal_module"
            GDAL_LOADED=true
            
            # Check GDAL version from the loaded module
            if command -v gdalinfo &> /dev/null; then
                GDAL_VERSION=$(gdalinfo --version | grep -oP 'GDAL \K[0-9]+\.[0-9]+\.[0-9]+' || echo "")
                print_info "System GDAL version: $GDAL_VERSION"
            fi
            break
        fi
    done
    
    if [ "$GDAL_LOADED" = false ]; then
        print_warning "No GDAL module found. Will attempt to install from pip."
        print_info "Available GDAL modules:"
        module avail 2>&1 | grep -i gdal || true
    fi
else
    print_warning "Module system not available. Using system Python and GDAL."
    PYTHON_CMD=python3
fi

# ============================================
# VERIFY PYTHON VERSION
# ============================================

print_info "Verifying Python installation..."

# Set Python command if not already set
if [ -z "$PYTHON_CMD" ]; then
    # Try to find the best Python version available
    for cmd in python3.12 python3.11 python3.10 python3; do
        if command -v $cmd &> /dev/null; then
            PYTHON_CMD=$cmd
            break
        fi
    done
fi

if [ -z "$PYTHON_CMD" ] || ! command -v $PYTHON_CMD &> /dev/null; then
    print_error "No suitable Python found. Please load a Python module."
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | grep -oP 'Python \K[0-9]+\.[0-9]+\.[0-9]+')
print_success "Using Python: $PYTHON_CMD (version $PYTHON_VERSION)"

# Check if Python version is sufficient
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 9 ]); then
    print_error "Python 3.9+ required, but $PYTHON_VERSION found"
    exit 1
fi

# ============================================
# SETUP ENVIRONMENT VARIABLES
# ============================================

print_info "Setting up environment variables..."

export PYTHONNOUSERSITE=1
export PIP_USER=0
export UV_CACHE_DIR="$INSTALL_BASE/.uv-cache"
export PIP_CACHE_DIR="$INSTALL_BASE/.pip-cache"
export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"

# ============================================
# CREATE DIRECTORIES
# ============================================

print_info "Creating installation directories..."

mkdir -p "$INSTALL_BASE"
mkdir -p "$UV_CACHE_DIR"
mkdir -p "$PIP_CACHE_DIR"
mkdir -p "$INSTALL_BASE/$ENV_NAME"

if [ ! -w "$INSTALL_BASE" ]; then
    print_error "No write permission to $INSTALL_BASE"
    exit 1
fi

cd "$INSTALL_BASE"
print_success "Directories created"

# ============================================
# INSTALL UV IF NOT PRESENT
# ============================================

if ! command -v uv &> /dev/null; then
    print_info "Installing UV package manager (fast Python installer)..."
    
    # Try curl first
    if command -v curl &> /dev/null; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    # Try wget if curl fails
    elif command -v wget &> /dev/null; then
        wget -qO- https://astral.sh/uv/install.sh | sh
    else
        print_warning "Neither curl nor wget available. Installing via pip..."
        $PYTHON_CMD -m pip install --user uv
    fi
    
    # Update PATH for current session
    export PATH="$HOME/.cargo/bin:$HOME/.local/bin:$PATH"
    
    # Verify UV installation
    if ! command -v uv &> /dev/null; then
        print_error "UV installation failed. Falling back to pip."
        USE_PIP=true
    else
        print_success "UV installed successfully"
        USE_PIP=false
    fi
else
    print_success "UV already installed: $(uv --version)"
    USE_PIP=false
fi

# ============================================
# CREATE VIRTUAL ENVIRONMENT
# ============================================

print_info "Creating Python virtual environment..."

if [ -d "$INSTALL_BASE/$ENV_NAME/.venv" ]; then
    print_warning "Virtual environment already exists. Removing old environment..."
    rm -rf "$INSTALL_BASE/$ENV_NAME/.venv"
fi

# Create virtual environment with the specific Python version
$PYTHON_CMD -m venv "$ENV_NAME/.venv"
print_success "Virtual environment created with Python $PYTHON_VERSION"

# ============================================
# ACTIVATE VIRTUAL ENVIRONMENT
# ============================================

print_info "Activating virtual environment..."

unset PYTHONPATH
source "$INSTALL_BASE/$ENV_NAME/.venv/bin/activate"

print_success "Environment activated: $(which python)"
print_info "Python version in venv: $(python --version)"

# ============================================
# CREATE REQUIREMENTS FILE
# ============================================

print_info "Creating requirements.txt with 200+ packages..."

# Use detected GDAL version or default to 3.11.0
GDAL_REQUIREMENT="gdal==${GDAL_VERSION:-3.11.0}"
print_info "Using GDAL requirement: $GDAL_REQUIREMENT"

# Adjust numpy version based on Python version
if [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]; then
    NUMPY_VERSION="numpy==1.26.4"  # Last version for Python 3.9/3.10
else
    NUMPY_VERSION="numpy==2.3.3"   # For Python 3.11+
fi

cat > "$INSTALL_BASE/$ENV_NAME/requirements.txt" << REQUIREMENTS_EOF
# Core dependencies - install first
$NUMPY_VERSION
cython
setuptools==80.9.0
wheel

# GDAL and geospatial packages
$GDAL_REQUIREMENT
fiona==1.10.1
rasterio==1.4.3
geopandas==1.1.1
shapely==2.1.2
pyproj==3.7.2
cartopy==0.25.0
pyogrio==0.11.1
rtree==1.4.1

# Climate and NetCDF packages
netcdf4==1.7.2
h5netcdf==1.7.3
xarray==2025.1.1
cfgrib==0.9.15.1
cftime==1.6.4.post1
eccodes==2.44.0
xclim==0.58.1

# Data processing
pandas==2.3.3
dask==2025.9.1
bottleneck==1.6.0
scipy==1.15.3
statsmodels==0.14.5

# Machine learning
scikit-learn==1.7.2
torch==2.9.0
catboost==1.2.8
shap==0.49.1
optuna==4.5.0

# Visualization
matplotlib==3.10.7
seaborn==0.13.2
plotly==6.3.1
scienceplots==2.1.1

# Additional packages
affine==2.4.0
aiofiles==25.1.0
alembic==1.17.0
annotated-types==0.7.0
anyio==4.11.0
arrow==1.3.0
attrs==25.4.0
azure-core==1.35.1
azure-storage-blob==12.26.0
backoff==2.2.1
beautifulsoup4==4.14.2
boltons==25.0.0
boruta==0.4.3
boto3==1.40.50
botocore==1.40.50
bravado==11.1.0
bravado-core==6.1.1
bs4==0.0.2
cached-property==2.0.1
cachetools==6.2.0
cdsapi==0.7.7
certifi==2025.10.5
cf-xarray==0.10.9
cffi==2.0.0
chardet==5.2.0
charset-normalizer==3.4.3
click==8.3.0
click-plugins==1.1.1.2
cligj==0.7.2
cloudpickle==3.1.1
colorlog==6.10.1
configobj==5.0.9
contourpy==1.3.3
cryptography==46.0.2
cycler==0.12.1
deprecated==1.2.18
distro==1.9.0
donfig==0.8.1.post1
earthengine-api==1.6.13
eccodeslib==2.44.0.5
eckitlib==1.32.2.5
ecmwf-datastores-client==0.4.0
einops==0.8.1
et-xmlfile==2.0.0
eval-type-backport==0.2.2
fckitlib==0.14.0.5
filelock==3.20.0
filetype==1.2.0
findlibs==0.1.2
flexcache==0.3
flexparser==0.4
fonttools==4.60.1
fqdn==1.5.1
fsspec==2025.9.0
future==1.0.0
geocif==0.2.88
geographiclib==2.1
geoprepare==0.6.17
geopy==2.4.1
gitdb==4.0.12
gitpython==3.1.45
google-api-core==2.27.0
google-api-python-client==2.185.0
google-auth==2.41.1
google-auth-httplib2==0.2.0
google-cloud-core==2.4.3
google-cloud-storage==3.4.1
google-crc32c==1.7.1
google-resumable-media==2.7.2
googleapis-common-protos==1.71.0
graphviz==0.21
greenlet==3.2.4
h11==0.16.0
h2==4.3.0
h5py==3.14.0
hf-xet==1.2.0
hpack==4.1.0
httpcore==1.0.9
httplib2==0.31.0
httpx==0.28.1
huggingface-hub==1.1.2
hyperframe==6.1.0
idna==3.10
imageio==2.37.0
importlib-resources==6.5.2
isodate==0.7.2
isoduration==20.11.0
jinja2==3.1.6
jmespath==1.0.1
joblib==1.5.2
jsonpointer==3.0.0
jsonref==1.1.0
jsonschema==4.25.1
jsonschema-specifications==2025.9.1
kditransform==1.2.0
kiwisolver==1.4.9
lark==1.3.0
lazy-loader==0.4
llvmlite==0.45.1
locket==1.0.0
logzero==1.7.0
mako==1.3.10
markupsafe==3.0.3
monotonic==1.6
more-itertools==10.8.0
mpmath==1.3.0
msgpack==1.1.2
multiurl==0.3.7
narwhals==2.9.0
neptune==1.14.0
neptune-api==0.23.0
neptune-scale==0.27.0
networkx==3.5
numba==0.62.1
nvidia-cublas-cu12==12.8.4.1
nvidia-cuda-cupti-cu12==12.8.90
nvidia-cuda-nvrtc-cu12==12.8.93
nvidia-cuda-runtime-cu12==12.8.90
nvidia-cudnn-cu12==9.10.2.21
nvidia-cufft-cu12==11.3.3.83
nvidia-cufile-cu12==1.13.1.3
nvidia-curand-cu12==10.3.9.90
nvidia-cusolver-cu12==11.7.3.90
nvidia-cusparse-cu12==12.5.8.93
nvidia-cusparselt-cu12==0.7.1
nvidia-nccl-cu12==2.27.5
nvidia-nvjitlink-cu12==12.8.93
nvidia-nvshmem-cu12==3.3.20
nvidia-nvtx-cu12==12.8.90
oauthlib==3.3.1
openeo==0.45.0
openpyxl==3.1.5
packaging==25.0
palettable==3.3.3
pandas-flavor==0.7.0
partd==1.4.2
patsy==1.0.1
pillow==11.3.0
pingouin==0.5.5
pint==0.25
platformdirs==4.5.0
pooch==1.8.2
posthog==6.9.0
proto-plus==1.26.1
protobuf==6.32.1
psutil==7.1.0
pyarrow==21.0.0
pyasn1==0.6.1
pyasn1-modules==0.4.2
pycparser==2.23
pydantic==2.12.3
pydantic-core==2.41.4
pydantic-settings==2.11.0
pyeogpr==2.4.7
pyhdf==0.11.6
pyjwt==2.10.1
pykdtree==1.4.3
pyl4c==0.18.1
pymannkendall==1.4.3
pyparsing==3.2.5
pyresample==1.34.2
pyshp==2.3.1
pystac==1.14.1
python-dateutil==2.9.0.post0
python-dotenv==1.2.1
pytz==2025.2
pyyaml==6.0.3
rasterstats==0.20.0
referencing==0.36.2
regionmask==0.13.0
requests==2.32.5
requests-oauthlib==2.0.0
rfc3339-validator==0.1.4
rfc3986-validator==0.1.1
rfc3987-syntax==1.1.0
rioxarray==0.19.0
rpds-py==0.27.1
rsa==4.9.1
s3transfer==0.14.0
scikit-image==0.25.2
sentry-sdk==2.42.1
simplejson==3.20.2
six==1.17.0
slicer==0.0.8
smmap==5.0.2
sniffio==1.3.1
soupsieve==2.8
sqlalchemy==2.0.44
swagger-spec-validator==3.0.4
sympy==1.14.0
tabpfn==6.0.5
tabpfn-common-utils==0.2.7
tabulate==0.9.0
tenacity==9.1.2
threadpoolctl==3.6.0
tifffile==2025.10.4
toolz==1.0.0
tqdm==4.67.1
triton==3.5.0
typer-slim==0.20.0
types-python-dateutil==2.9.0.20251008
typing-extensions==4.15.0
typing-inspection==0.4.2
tzdata==2025.2
uri-template==1.3.0
uritemplate==4.2.0
urllib3==2.5.0
wandb==0.22.2
webcolors==24.11.1
websocket-client==1.9.0
wget==3.2
wrapt==1.17.3
yamale==6.0.0
REQUIREMENTS_EOF

print_success "Requirements file created"

# ============================================
# INSTALL PACKAGES
# ============================================

print_info "Installing Python packages (10-15 minutes with UV)..."
echo "Using fast UV installer for speed..."

# Function to install packages
install_packages() {
    if [ "$USE_PIP" = false ] && command -v uv &> /dev/null; then
        # Use UV for fast installation
        uv pip install "$@"
    else
        # Fallback to regular pip
        pip install "$@"
    fi
}

# Install core dependencies first
print_info "Step 1/4: Installing core dependencies..."
install_packages --upgrade pip setuptools wheel cython
install_packages $NUMPY_VERSION

# Install GDAL
print_info "Step 2/4: Installing GDAL Python bindings..."

# If GDAL module is loaded and version detected, use that version
if [ -n "$GDAL_VERSION" ]; then
    print_info "Installing GDAL Python bindings to match system GDAL $GDAL_VERSION"
    install_packages gdal==$GDAL_VERSION || {
        print_warning "Exact version match failed, trying without version pin..."
        install_packages gdal
    }
else
    # No system GDAL found, try default version
    print_warning "No system GDAL detected, attempting to install from pip..."
    install_packages gdal==3.11.0 || {
        print_warning "GDAL installation failed. You may need to load a GDAL module first."
        print_info "Try: module load rh9/gdal/3.11.0"
    }
fi

# Install all packages
print_info "Step 3/4: Installing all packages from requirements.txt..."
install_packages -r "$INSTALL_BASE/$ENV_NAME/requirements.txt" || {
    print_warning "Some packages failed. Attempting individual installation..."
    
    # Try to install critical packages individually
    print_info "Installing critical packages individually..."
    install_packages pandas || true
    install_packages xarray || true
    install_packages rasterio || true
    install_packages geopandas || true
    install_packages matplotlib || true
    install_packages scikit-learn || true
    install_packages netCDF4 || true
}

# Install Git packages
print_info "Step 4/4: Installing custom Git packages..."
install_packages git+https://github.com/ritviksahajpal/octvi.git@7760ceb5c903f47d847c46240870e65780548e1b || {
    print_warning "octvi installation failed"
}
install_packages git+https://github.com/ritviksahajpal/pygeoutil.git@29f1b2e1ba880d4f3bbc8a3bc710c89de2912b63 || {
    print_warning "pygeoutil installation failed"
}

print_success "Package installation completed!"

# ============================================
# VERIFICATION
# ============================================

print_info "Verifying installation..."

python << 'VERIFY_EOF'
import sys
import os

print("\nVerification Results:")
print("-" * 40)

# Check Python location
home = os.path.expanduser('~')
if home not in sys.executable:
    print("✓ Python location correct (not in home)")
else:
    print("⚠ Python appears to be in home directory")

# Test critical imports
critical = ['numpy', 'pandas', 'xarray', 'gdal', 'rasterio', 'netCDF4', 'torch']
failed = []

for pkg in critical:
    try:
        __import__(pkg)
        print(f"✓ {pkg} imported successfully")
    except ImportError:
        print(f"✗ {pkg} import failed")
        failed.append(pkg)

if not failed:
    print("\n✅ All critical packages verified!")
else:
    print(f"\n⚠ Failed packages: {', '.join(failed)}")
    print("You can try installing them manually with:")
    print(f"  uv pip install {' '.join(failed)}")
VERIFY_EOF

# ============================================
# SAVE INSTALLATION INFO
# ============================================

cat > "$INSTALL_BASE/$ENV_NAME/installation_info.txt" << INFO_EOF
Geospatial Environment Installation Summary
=========================================
Installation Date: $(date)
Install Location: $INSTALL_BASE/$ENV_NAME
Working Directory: $WORK_DIR
Python Version: $PYTHON_VERSION
GDAL Version: ${GDAL_VERSION:-Not detected}
Virtual Environment: $INSTALL_BASE/$ENV_NAME/.venv
Package Count: 200+

To activate this environment:
  module purge
  module load python/3.12.9/anaconda  # Or your Python module
  module load rh9/gdal/3.11.0         # Or your GDAL module
  source $INSTALL_BASE/$ENV_NAME/.venv/bin/activate

To update packages:
  Activate environment first, then:
  uv pip install --upgrade package_name

To add new packages:
  Activate environment first, then:
  uv pip install new_package_name
INFO_EOF

print_success "Installation info saved to $INSTALL_BASE/$ENV_NAME/installation_info.txt"

# ============================================
# FINAL MESSAGE
# ============================================

echo ""
echo "============================================"
echo -e "${GREEN}   INSTALLATION COMPLETE!${NC}"
echo "============================================"
echo ""
echo "✅ Your Python environment is ready!"
echo ""
echo "To activate your environment, run these commands:"
echo ""
echo "  module purge"
if [ "$PYTHON_LOADED" = true ]; then
    echo "  module load python/3.12.9/anaconda  # (or python/3.11.7/anaconda)"
fi
if [ "$GDAL_LOADED" = true ]; then
    echo "  module load rh9/gdal/3.11.0"
fi
echo "  source $INSTALL_BASE/$ENV_NAME/.venv/bin/activate"
echo ""
echo "Then navigate to your working directory:"
echo "  cd $WORK_DIR"
echo ""
echo "Installation Details:"
echo "  Location: $INSTALL_BASE/$ENV_NAME"
echo "  Python Version: $PYTHON_VERSION"
if [ -n "$GDAL_VERSION" ]; then
    echo "  GDAL Version: $GDAL_VERSION"
fi
echo "  Packages: 200+ scientific packages"
echo ""
echo "============================================"
echo ""

# End of script
