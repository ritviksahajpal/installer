#!/usr/bin/env python3
"""
Cross-platform pixi installer for geocif + geoprepare + octvi.

Provisions a self-contained pixi (conda-forge) environment. Compared with the
old uv/venv installer this removes ALL of:
  * Lmod python/GDAL module loading + GDAL source-build + RPATH/patchelf surgery
  * cgohlke Windows wheels
  * the CPU-only-torch swap + nvidia/CUDA uninstall dance
  * the 200-package supplemental requirements list
conda-forge ships its own libgdal, a CPU pytorch build, and every binary dep,
so one `pixi install` does the whole job on Windows, Linux x86-64, Linux ARM
(aarch64), the UMD HPC, and managed Jupyter boxes.

Usage:
    python install.py [--install-base DIR] [--yes]
                      [--editable-geocif PATH] [--editable-geoprepare PATH]
                      [--editable-octvi PATH] [--octvi-git URL]
                      [--platform {auto,windows,umd_hpc,linux,macos}]

Stdlib-only; needs Python 3.8+ to bootstrap (pixi manages the target Python).
"""

from __future__ import annotations

__version__ = "1.0.0"  # pixi rewrite

import argparse
import os
import pathlib
import platform as platform_mod
import shutil
import subprocess
import sys


# -------- ANSI colors (auto-disabled on non-TTY) --------

_USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
_C = {
    "red": "\033[0;31m" if _USE_COLOR else "",
    "green": "\033[0;32m" if _USE_COLOR else "",
    "yellow": "\033[1;33m" if _USE_COLOR else "",
    "cyan": "\033[0;36m" if _USE_COLOR else "",
    "bold": "\033[1m" if _USE_COLOR else "",
    "reset": "\033[0m" if _USE_COLOR else "",
}


def ok(msg: str) -> None:
    print(f"{_C['green']}[ok]{_C['reset']}  {msg}")


def err(msg: str) -> None:
    print(f"{_C['red']}[err]{_C['reset']} {msg}", file=sys.stderr)


def warn(msg: str) -> None:
    print(f"{_C['yellow']}[!]{_C['reset']}   {msg}")


def info(msg: str) -> None:
    print(f"->    {msg}")


# -------- Platform detection --------

UMD_HPC_MARKER = pathlib.Path("/gpfs/data1/cmongp1")


def is_umd_hpc() -> bool:
    has_lmod = bool(os.environ.get("LMOD_CMD")) or bool(shutil.which("lmod"))
    return has_lmod and UMD_HPC_MARKER.exists()


def detect_platform() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "umd_hpc" if is_umd_hpc() else "linux"
    raise SystemExit(f"Unsupported platform: {sys.platform}")


def pixi_platform() -> str:
    """The conda subdir pixi will resolve for this host (informational)."""
    m = platform_mod.machine().lower()
    if sys.platform == "win32":
        return "win-64"
    if sys.platform == "darwin":
        return "osx-arm64" if m in ("arm64", "aarch64") else "osx-64"
    return "linux-aarch64" if m in ("aarch64", "arm64") else "linux-64"


# -------- Subprocess helper --------

def run(cmd, *, env=None, check=True, cwd=None, shell=False):
    printable = cmd if isinstance(cmd, str) else " ".join(str(c) for c in cmd)
    info(f"$ {printable}")
    result = subprocess.run(cmd, env=env, cwd=cwd, shell=shell, text=True)
    if check and result.returncode != 0:
        raise SystemExit(f"Command failed (exit {result.returncode}): {printable}")
    return result


# -------- pixi bootstrap --------

def pixi_bin_candidates(pixi_home: pathlib.Path | None = None) -> list[pathlib.Path]:
    exe = "pixi.exe" if sys.platform == "win32" else "pixi"
    cands: list[pathlib.Path] = []
    if pixi_home:
        cands.append(pixi_home / "bin" / exe)
    home = pathlib.Path.home()
    if sys.platform == "win32":
        base = pathlib.Path(os.environ.get("USERPROFILE", home))
        cands.append(base / ".pixi" / "bin" / exe)
    else:
        cands.append(home / ".pixi" / "bin" / exe)
    return cands


def ensure_pixi(platform: str, tmpdir: pathlib.Path,
                pixi_home: pathlib.Path | None = None,
                base_env: dict | None = None) -> str:
    """Return an absolute path to a working pixi binary, installing it if needed.

    On HPC / quota'd hosts we install pixi under PIXI_HOME on a big disk — the
    default ~/.pixi lives on a small /home ("Disk quota exceeded"). Managed
    Linux boxes also force TMPDIR to a read-only path, breaking pixi's installer
    (`mktemp ... Permission denied`) — we point TMPDIR at a writable dir first.
    """
    for cand in pixi_bin_candidates(pixi_home):
        if cand.exists():
            ok(f"pixi found: {cand}")
            return str(cand)
    found = shutil.which("pixi")
    if found:
        ok(f"pixi found: {found}")
        return found

    info("Installing pixi...")
    env = dict(base_env or os.environ)
    if pixi_home:
        pixi_home.mkdir(parents=True, exist_ok=True)
        env["PIXI_HOME"] = str(pixi_home)  # keep pixi off a quota'd /home
    if platform == "windows":
        run(
            'powershell -ExecutionPolicy ByPass -NoProfile -Command '
            '"irm -useb https://pixi.sh/install.ps1 | iex"',
            shell=True, env=env,
        )
    else:
        tmpdir.mkdir(parents=True, exist_ok=True)
        env["TMPDIR"] = str(tmpdir)  # dodge read-only /ASTG/tmp etc.
        if not (shutil.which("curl") or shutil.which("wget")):
            raise SystemExit("Need curl or wget to install pixi.")
        tool = "curl -fsSL" if shutil.which("curl") else "wget -qO-"
        run(f"{tool} https://pixi.sh/install.sh | bash", shell=True, env=env)

    for cand in pixi_bin_candidates(pixi_home):
        if cand.exists():
            ok(f"pixi installed: {cand}")
            return str(cand)
    found = shutil.which("pixi")
    if found:
        return found
    fallback = (pixi_home or pathlib.Path.home() / ".pixi") / "bin"
    raise SystemExit(
        "pixi installed but binary not found. Add it to PATH and re-run:\n"
        f'  export PATH="{fallback}:$PATH"'
    )


# -------- pixi.toml (batteries-included; validated across win-64/linux-64/linux-aarch64) --------

# Everything that is on conda-forge for all 3 platforms goes in [dependencies]
# (prebuilt binaries, no source compiles). The three packages plus the handful
# of PyPI-only / no-aarch64-wheel libs go in [pypi-dependencies].
_CONDA_DEPS = """\
python = "3.11.*"
# geospatial (conda-forge libgdal/geos/proj - no module, no cgohlke wheels)
gdal = ">=3.10"
rasterio = "*"
fiona = "*"
pyproj = "*"
shapely = "*"
rtree = "*"
cartopy = "*"
geopandas = "*"
rioxarray = "*"
affine = "*"
netcdf4 = "*"
pyhdf = "*"
pyresample = "*"
# numerics / climate
xarray = ">=2026.2.0"
numpy = "*"
pandas = "*"
scipy = "*"
matplotlib = "<3.11"
seaborn = "*"
bottleneck = ">=1.3"
# core ML (compiled)
numba = ">=0.59"
scikit-learn = ">=1.4"
scikit-image = "*"
scikit-misc = ">=0.5.2"
catboost = ">=1.2.8"
statsmodels = ">=0.14.6"
shap = ">=0.48.0"
shapiq = ">=1.0"
pytorch-cpu = "*"
# ML backends / selection (conda-forge)
optuna = "*"
ngboost = ">=0.5"
mapie = ">=0.8"
crepes = ">=0.6"
lifelines = ">=0.27"
kneed = ">=0.8"
feature_engine = ">=1.6"
mrmr_selection = ">=0.2"
# spatial stats
esda = ">=2.5"
libpysal = ">=4.10"
# indices / analysis / trend
icclim = ">=7.0.4"
mapclassify = ">=2.5"
pymannkendall = ">=1.4"
# utilities
pooch = ">=1.8.0"
choix = ">=0.3.4"
palettable = ">=3.3.3"
scienceplots = ">=2.0.0"
cachetools = ">=5.0"
geopy = ">=2.0"
arrow = ">=1.4.0"
rich = "*"
tenacity = "*"
logzero = ">=1.7.0"
tqdm = "*"
requests = "*"
urllib3 = "*"
beautifulsoup4 = "*"
setuptools = "<81"
# download sources
cdsapi = "*"
pymodis = "*"
earthaccess = "*"
pydap = "*"
# extras: dashboard / gee / spatial / narrative (all conda-forge)
panel = ">=1.4.0"
hvplot = ">=0.10.0"
holoviews = ">=1.18"
earthengine-api = ">=1.0"
geemap = ">=0.30"
pysal = ">=2.6"
reportlab = ">=4.0"
anthropic = ">=0.30"
"""

# PyPI-only / no-conda-aarch64 deps (pulled from PyPI). geoprepare/geocif/octvi
# lines are appended dynamically (PyPI vs git vs editable path).
_PYPI_ONLY = """\
tabpfn = ">=6.4.1"
tabpfn-extensions = ">=0.4"
tabicl = ">=2.0.2"
cubist = ">=1.0"
merf = ">=1.0"
pyeogpr = ">=2.4.7"
pangres = ">=4.0"
stabl = ">=0.0.1"
arfs = ">=2.0"
BorutaShap = ">=1.0"
pyl4c = "*"
wget = "*"
Rbeast = ">=0.1.20"              # no conda-forge aarch64 build; PyPI ships aarch64 wheels
sklearn-genetic-opt = ">=0.10"  # conda recipe stuck on py3.12/tensorflow; take from PyPI
aquacrop = ">=3.0"
pymupdf = ">=1.23"
pdfplumber = ">=0.10"
"""

DEFAULT_OCTVI_GIT = "https://github.com/ritviksahajpal/octvi.git"
PYGEOUTIL_GIT = "https://github.com/ritviksahajpal/pygeoutil.git"


def _pkg_line(name: str, editable_path: str | None, pypi_spec: str) -> str:
    if editable_path:
        p = pathlib.Path(editable_path).expanduser().resolve().as_posix()
        return f'{name} = {{ path = "{p}", editable = true }}'
    return f"{name} = {pypi_spec}"


def render_pixi_toml(
    editable_geocif: str | None,
    editable_geoprepare: str | None,
    editable_octvi: str | None,
    octvi_git: str,
) -> str:
    geoprepare = _pkg_line("geoprepare", editable_geoprepare, '">=0.6.286"')
    geocif = _pkg_line("geocif", editable_geocif, '">=0.4.880"')
    if editable_octvi:
        p = pathlib.Path(editable_octvi).expanduser().resolve().as_posix()
        octvi = f'octvi = {{ path = "{p}", editable = true }}'
    else:
        octvi = f'octvi = {{ git = "{octvi_git}" }}'
    return (
        "[workspace]\n"
        'name = "geo-stack"\n'
        'channels = ["conda-forge"]\n'
        'platforms = ["linux-64", "linux-aarch64", "win-64"]\n\n'
        "# Generated by installer/install.py. conda-forge binaries below; the\n"
        "# packages + PyPI-only deps are in [pypi-dependencies].\n"
        "[dependencies]\n"
        + _CONDA_DEPS
        + "\n[pypi-dependencies]\n"
        + f"{geoprepare}\n{geocif}\n"
        + "# octvi is not on PyPI; pixi fetches it during install. Point at the\n"
        + "# fork carrying the GCVI Int32 fix (upstream nasaharvest lacks it).\n"
        + f"{octvi}\n"
        + f'pygeoutil = {{ git = "{PYGEOUTIL_GIT}" }}\n'
        + _PYPI_ONLY
    )


# -------- Activation helpers --------
# pixi has no persistent "activate" — you `pixi run <cmd>` or `pixi shell` from
# the project dir. These thin wrappers just cd there and drop you into a shell.

ACTIVATE_PS1 = """\
# geo-stack: enter the pixi environment.  Usage: . .\\activate.ps1
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PATH = "$env:USERPROFILE\\.pixi\\bin;$env:PATH"
pixi shell --manifest-path (Join-Path $Here "pixi.toml")
"""


def write_activation(install_dir: pathlib.Path, platform: str, pixi_bin_dir: str,
                     pixi_home: pathlib.Path | None, cache_dir: pathlib.Path | None) -> None:
    if platform == "windows":
        (install_dir / "activate.ps1").write_text(ACTIVATE_PS1, encoding="utf-8")
        ok(f"Wrote activate.ps1 in {install_dir}")
        return
    exports = [f'export PATH="{pixi_bin_dir}:$PATH"']
    if pixi_home:
        exports.append(f'export PIXI_HOME="{pixi_home}"')
    if cache_dir:
        exports.append(f'export PIXI_CACHE_DIR="{cache_dir}"')
    body = (
        "#!/usr/bin/env bash\n"
        "# geo-stack: enter the pixi environment. Usage: source activate.sh\n"
        'HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"\n'
        + "\n".join(exports) + "\n"
        + 'exec pixi shell --manifest-path "$HERE/pixi.toml"\n'
    )
    path = install_dir / "activate.sh"
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    ok(f"Wrote activate.sh in {install_dir}")


# -------- Verify --------

def verify(pixi: str, install_dir: pathlib.Path, env: dict) -> None:
    info("Verifying installation (pixi run)...")
    script = (
        "import importlib\n"
        "mods = ['numpy','pandas','osgeo.gdal','rasterio','geopandas',"
        "'geoprepare','geocif','octvi']\n"
        "bad = []\n"
        "for m in mods:\n"
        "    try:\n"
        "        obj = importlib.import_module(m)\n"
        "        print('[ok]', m, getattr(obj, '__version__', ''))\n"
        "    except Exception as e:\n"
        "        print('[err]', m, type(e).__name__, e); bad.append(m)\n"
        "import sys; sys.exit(1 if bad else 0)\n"
    )
    result = run(
        [pixi, "run", "--manifest-path", str(install_dir / "pixi.toml"), "python", "-c", script],
        env=env, check=False,
    )
    if result.returncode != 0:
        warn("Some packages failed to import (see above)")
    else:
        ok("All critical packages imported successfully")


# -------- Defaults / CLI --------

def default_install_base(platform: str) -> pathlib.Path:
    if platform == "umd_hpc":
        gpfs_user = UMD_HPC_MARKER / os.environ.get("USER", "")
        if gpfs_user.parent.exists():
            return gpfs_user
    if platform == "windows":
        return pathlib.Path(os.environ.get("USERPROFILE", "C:\\")) / "geo-stack-env"
    return pathlib.Path.home() / "geo-stack-env"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="pixi installer for geocif/geoprepare/octvi.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--install-base", type=pathlib.Path, default=None,
                   help="Parent dir for the geo-stack env (default per platform).")
    p.add_argument("--editable-geocif", type=str, default=None,
                   help="Install geocif editable from this local clone.")
    p.add_argument("--editable-geoprepare", type=str, default=None,
                   help="Install geoprepare editable from this local clone.")
    p.add_argument("--editable-octvi", type=str, default=None,
                   help="Install octvi editable from this local clone.")
    p.add_argument("--octvi-git", type=str, default=DEFAULT_OCTVI_GIT,
                   help=f"octvi git URL when not editable (default: {DEFAULT_OCTVI_GIT}).")
    p.add_argument("--platform", choices=["auto", "windows", "umd_hpc", "linux", "macos"],
                   default="auto", help="Override platform detection.")
    p.add_argument("--yes", "-y", action="store_true", help="Skip confirmation.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if not args.yes and not sys.stdin.isatty():
        raise SystemExit("Non-interactive shell (no TTY). Re-run with --yes.")

    info(f"installer version: {__version__}")
    platform = args.platform if args.platform != "auto" else detect_platform()
    install_base = (args.install_base or default_install_base(platform)).expanduser().resolve()
    install_dir = install_base / "geo-stack"

    print("=" * 60)
    print(f"Platform:       {platform}  (conda subdir: {pixi_platform()})")
    print(f"Install dir:    {install_dir}")
    print(f"geocif:         {args.editable_geocif or '(PyPI >=0.4.880)'}")
    print(f"geoprepare:     {args.editable_geoprepare or '(PyPI >=0.6.286)'}")
    print(f"octvi:          {args.editable_octvi or args.octvi_git}")
    print("=" * 60)
    if not args.yes:
        if input("Continue? [y/N] ").strip().lower() not in ("y", "yes"):
            raise SystemExit("Aborted.")

    install_dir.mkdir(parents=True, exist_ok=True)

    # Keep pixi's binary (PIXI_HOME) AND package cache (PIXI_CACHE_DIR) off
    # small/quota'd homes (HPC /home is tiny — "Disk quota exceeded"). On HPC
    # both go under install_base (which is on /gpfs).
    cache_dir = None
    pixi_home = None
    env = dict(os.environ)
    if platform in ("umd_hpc",) or is_umd_hpc():
        cache_dir = install_base / ".pixi-cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        env["PIXI_CACHE_DIR"] = str(cache_dir)
        pixi_home = install_base / ".pixi-home"
        env["PIXI_HOME"] = str(pixi_home)
        info(f"pixi home:  {pixi_home}")
        info(f"pixi cache: {cache_dir}")
    env["UV_LOCK_TIMEOUT"] = "600"

    pixi = ensure_pixi(platform, tmpdir=install_base / ".tmp",
                       pixi_home=pixi_home, base_env=env)

    # Write the manifest (idempotent — overwrites any prior one).
    toml = render_pixi_toml(
        editable_geocif=args.editable_geocif,
        editable_geoprepare=args.editable_geoprepare,
        editable_octvi=args.editable_octvi,
        octvi_git=args.octvi_git,
    )
    (install_dir / "pixi.toml").write_text(toml, encoding="utf-8")
    ok(f"Wrote {install_dir / 'pixi.toml'}")

    info("Solving + installing the environment (first run downloads a few hundred MB)...")
    run([pixi, "install", "--manifest-path", str(install_dir / "pixi.toml")], env=env)

    pixi_bin_dir = str(pathlib.Path(pixi).parent)
    write_activation(install_dir, platform, pixi_bin_dir, pixi_home, cache_dir)
    verify(pixi, install_dir, env)

    bar = "=" * 60
    act = ("  . " + str(install_dir / "activate.ps1")) if platform == "windows" \
        else ("  source " + str(install_dir / "activate.sh"))
    print(f"\n{_C['green']}{bar}\n  INSTALLATION COMPLETE\n{bar}{_C['reset']}\n")
    print("Enter the environment (each new shell):")
    print(f"{_C['cyan']}{act}{_C['reset']}")
    print("\nOr run one-off commands without a subshell:")
    print(f"{_C['cyan']}  pixi run --manifest-path {install_dir / 'pixi.toml'} python -c \"import geocif\"{_C['reset']}")
    print("\nAdd a package later:  pixi add <pkg>   |   pixi add --pypi <pkg>")
    print(f"Rebuild from scratch: re-run this installer.\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        err("Interrupted")
        sys.exit(130)
