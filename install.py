#!/usr/bin/env python3
"""
Cross-platform installer for geocif + geoprepare.

Detects platform (Windows / UMD HPC / generic Linux / macOS) and provisions a
Python 3.11 (3.12 on HPC) virtual environment with geocif installed. All
dependency resolution is delegated to uv and geocif/pyproject.toml.

Usage:
    python install.py [--install-base DIR] [--editable PATH] [--editable-geoprepare PATH]
                      [--platform {auto,windows,umd_hpc,linux,macos}]
                      [--write-shell-rc]

Stdlib-only; requires Python 3.8+ to bootstrap (uv handles the target Python).
"""

from __future__ import annotations

__version__ = "0.4.4"

import argparse
import contextlib
import os
import pathlib
import platform as platform_mod
import shutil
import subprocess
import sys
import textwrap
import urllib.request


class _Tee:
    """Write to multiple streams. Used to mirror stdout/stderr to a log file."""
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data: str) -> int:
        for s in self.streams:
            try:
                s.write(data)
                s.flush()
            except Exception:
                pass
        return len(data)

    def flush(self) -> None:
        for s in self.streams:
            try:
                s.flush()
            except Exception:
                pass

    def isatty(self) -> bool:
        return getattr(self.streams[0], "isatty", lambda: False)()


_LOG_FH = None  # set in main() if --log-file passed

# -------- ANSI colors (auto-disabled on non-TTY / Windows legacy) --------

_USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
_C = {
    "red":    "\033[0;31m" if _USE_COLOR else "",
    "green":  "\033[0;32m" if _USE_COLOR else "",
    "yellow": "\033[1;33m" if _USE_COLOR else "",
    "reset":  "\033[0m"    if _USE_COLOR else "",
}

def ok(msg: str) -> None:     print(f"{_C['green']}[ok]{_C['reset']}  {msg}")
def err(msg: str) -> None:    print(f"{_C['red']}[err]{_C['reset']} {msg}", file=sys.stderr)
def warn(msg: str) -> None:   print(f"{_C['yellow']}[!]{_C['reset']}   {msg}")
def info(msg: str) -> None:   print(f"->    {msg}")

# -------- Platform detection --------

UMD_HPC_MARKER = pathlib.Path("/gpfs/data1/cmongp1")

def detect_platform() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        if is_umd_hpc():
            return "umd_hpc"
        return "linux"
    raise SystemExit(f"Unsupported platform: {sys.platform}")

def is_umd_hpc() -> bool:
    has_lmod = bool(os.environ.get("LMOD_CMD")) or bool(shutil.which("lmod"))
    return has_lmod and UMD_HPC_MARKER.exists()

# -------- Subprocess helpers --------

def run(cmd, *, env=None, check=True, capture=False, shell=False, cwd=None):
    """Run a command; print it; surface stderr on failure.

    When _LOG_FH is set (via --log-file), forces capture so subprocess output
    is mirrored through Python's stdout/stderr (which are teed to the log).
    Otherwise lets subprocess inherit stdout/stderr directly for speed.
    """
    if isinstance(cmd, list):
        printable = " ".join(cmd)
    else:
        printable = cmd
    info(f"$ {printable}")
    do_capture = capture or (_LOG_FH is not None)
    result = subprocess.run(
        cmd, env=env, shell=shell, cwd=cwd,
        stdout=subprocess.PIPE if do_capture else None,
        stderr=subprocess.PIPE if do_capture else None,
        text=True,
    )
    if _LOG_FH is not None:
        # Relay captured output to (teed) stdout/stderr so the log gets it.
        if result.stdout:
            sys.stdout.write(result.stdout)
            sys.stdout.flush()
        if result.stderr:
            sys.stderr.write(result.stderr)
            sys.stderr.flush()
    if check and result.returncode != 0:
        if capture and result.stderr:
            err(result.stderr.strip())
        raise SystemExit(f"Command failed (exit {result.returncode}): {printable}")
    return result

def run_bash(script: str, *, env=None, check=True, capture=False):
    """Run a bash snippet (Linux/macOS only). Non-login shell (`-c`, not `-lc`)
    so we don't inherit the user's conda init from ~/.bashrc. Scripts that need
    `module` must source /etc/profile.d/modules.sh themselves."""
    return run(["bash", "-c", script], env=env, check=check, capture=capture)

# -------- uv installer --------

def ensure_uv(platform: str) -> str:
    """Install uv if missing; return absolute path to the uv binary."""
    uv = shutil.which("uv")
    if uv:
        ok(f"uv found: {uv}")
        return uv

    info("Installing uv...")
    if platform == "windows":
        ps_cmd = (
            "powershell -ExecutionPolicy ByPass -NoProfile -Command "
            "\"irm https://astral.sh/uv/install.ps1 | iex\""
        )
        run(ps_cmd, shell=True)
        candidate = pathlib.Path(os.environ["USERPROFILE"]) / ".local" / "bin" / "uv.exe"
    else:
        # curl-or-wget piped to sh, official Astral path
        if shutil.which("curl"):
            run("curl -LsSf https://astral.sh/uv/install.sh | sh", shell=True)
        elif shutil.which("wget"):
            run("wget -qO- https://astral.sh/uv/install.sh | sh", shell=True)
        else:
            raise SystemExit("Need curl or wget to install uv.")
        candidate = pathlib.Path.home() / ".local" / "bin" / "uv"

    # uv installer drops to ~/.local/bin (or %USERPROFILE%\.local\bin on Windows)
    if candidate.exists():
        ok(f"uv installed: {candidate}")
        return str(candidate)

    # Last resort: rehash PATH and look again
    uv = shutil.which("uv")
    if uv:
        return uv
    raise SystemExit(f"uv installation succeeded but binary not found at {candidate}")

# -------- HPC: module loading --------

def load_hpc_modules() -> tuple[str, dict[str, str], str | None]:
    """
    Purge active conda state, bootstrap Lmod, and load python + GDAL modules.
    Returns: (python_abs_path, env_after_loads, gdal_lib_dir)

    Confirmed gsapp module names: `python/3.12.9/anaconda` (no short-form alias
    on this cluster), `rh9/gdal/3.11.0` (the (D) default).
    """
    info("Loading HPC modules (stripping conda, sourcing Lmod init)...")
    # Exact module IDs known to exist on gsapp (verified via `module avail`).
    # No short-form fallbacks (e.g. `python/3.12/anaconda`) — those don't exist.
    python_modules = ["python/3.12.9/anaconda", "python/3.11.7/anaconda"]
    gdal_modules = ["rh9/gdal/3.11.0", "rh9/gdal/3.5.3", "gdal/3.1.0", "gdal"]

    py_modules_sh = " ".join(python_modules)
    gdal_modules_sh = " ".join(gdal_modules)

    # Build env-capture regex programmatically so the grep is readable.
    capture_prefixes = (
        "PATH", "LD_LIBRARY_PATH", "PYTHONPATH",
        "LOADEDMODULES", "_LMFILES_", "MODULEPATH", "LMOD_",
        "GDAL_", "PROJ_", "GS_LIB", "GEOTIFF_", "CPL_", "OGR_",
    )
    capture_regex = "^(" + "|".join(capture_prefixes) + ")"

    script = textwrap.dedent(f"""
        set -e

        # 1. Clean conda. Source /etc/profile.d/conda.sh so the `conda`
        # function is defined in this non-login shell, then deactivate any
        # active env (gsapp auto-activates `(base)` system-wide). Fallback:
        # strip user-conda dirs from PATH if conda is unavailable.
        if [ -r /etc/profile.d/conda.sh ]; then
            . /etc/profile.d/conda.sh
            while [ -n "$CONDA_DEFAULT_ENV" ]; do
                conda deactivate 2>/dev/null || break
            done
        fi
        # Defensive PATH strip — narrow patterns to user-conda installs only
        # (e.g. ~/miniconda3, ~/anaconda3). Does NOT touch module-provided
        # /apps/.../anaconda/bin (no "3" suffix in that dir name).
        PATH=$(echo "$PATH" | tr ':' '\\n' \\
            | grep -viE '(miniconda3|anaconda3|/conda3?/)' \\
            | paste -sd: -)
        export PATH
        unset CONDA_DEFAULT_ENV CONDA_PREFIX CONDA_SHLVL CONDA_PYTHON_EXE \\
              CONDA_EXE CONDA_PROMPT_MODIFIER _CE_CONDA _CE_M PYTHONHOME

        # 2. Bootstrap `module` (non-login shell doesn't auto-source this).
        if ! command -v module >/dev/null 2>&1; then
            for init in /etc/profile.d/modules.sh \\
                        /usr/share/lmod/lmod/init/bash \\
                        /apps/lmod/lmod/init/bash; do
                [ -r "$init" ] && . "$init" && break
            done
        fi
        if ! command -v module >/dev/null 2>&1; then
            echo "MODULE_BOOTSTRAP_FAILED" >&2
            exit 1
        fi

        # 3. Purge and load. Use a sequential for-loop in the CURRENT shell
        # (no subshell `( ... )` — PATH changes from `module load` must
        # persist for steps 4-6 to find the loaded python and gdal-config).
        module purge 2>/dev/null || true

        PY_OK=0
        for m in {py_modules_sh}; do
            if module load "$m" 2>/dev/null; then PY_OK=1; break; fi
        done
        [ "$PY_OK" = "1" ] || {{ echo "PY_LOAD_FAILED" >&2; exit 1; }}

        GDAL_OK=0
        for m in {gdal_modules_sh}; do
            if module load "$m" 2>/dev/null; then GDAL_OK=1; break; fi
        done
        [ "$GDAL_OK" = "1" ] || echo "GDAL_LOAD_FAILED" >&2

        # Diagnostic: show what's actually loaded (goes to stderr → visible in installer output).
        echo "--- module list after load ---" >&2
        module list 2>&1 >&2 || true

        # 4. Find the loaded python — absolute path, so the parent process
        # doesn't rely on PATH ordering.
        for cmd in python3.12 python3.11 python3; do
            if command -v "$cmd" >/dev/null 2>&1; then
                PY_ABS=$(command -v "$cmd")
                break
            fi
        done
        echo "PYTHON_CMD=$PY_ABS"

        # 5. Capture libgdal location from gdal-config so we can RPATH-link.
        if command -v gdal-config >/dev/null 2>&1; then
            GDAL_LIBS=$(gdal-config --libs 2>/dev/null || true)
            GDAL_LIB_DIR=$(echo "$GDAL_LIBS" | grep -oE '\\-L[^ ]+' | head -1 | sed 's/^-L//')
            echo "GDAL_LIB_DIR=$GDAL_LIB_DIR"
            echo "GDAL_CONFIG_PATH=$(command -v gdal-config)" >&2
            echo "GDAL_VERSION=$(gdal-config --version 2>/dev/null)" >&2
        fi

        # 6. Dump relevant env vars so Python inherits the post-load state.
        env | grep -E '{capture_regex}' \\
            | while IFS= read -r line; do echo "ENV:$line"; done
    """)

    result = run_bash(script, capture=True, check=True)

    # Surface the bash script's stderr (module list, gdal-config diagnostics)
    # so the user can see what actually loaded.
    if result.stderr:
        for line in result.stderr.rstrip().splitlines():
            print(f"      {line}")

    python_cmd = "python3"
    gdal_lib_dir: str | None = None
    new_env = dict(os.environ)
    # Defense-in-depth: drop any conda vars from the parent env too, in case
    # the user ran `python install.py` with `(base)` still active.
    for k in list(new_env):
        if k.startswith("CONDA_") or k in ("_CE_CONDA", "_CE_M", "PYTHONHOME"):
            new_env.pop(k, None)

    for line in (result.stdout or "").splitlines():
        if line.startswith("PYTHON_CMD="):
            python_cmd = line.split("=", 1)[1].strip() or python_cmd
        elif line.startswith("GDAL_LIB_DIR="):
            val = line.split("=", 1)[1].strip()
            gdal_lib_dir = val or None
        elif line.startswith("ENV:"):
            kv = line[4:]
            if "=" in kv:
                k, v = kv.split("=", 1)
                # Skip PYTHONPATH — HPC GDAL module sets it to
                # /apps/.../gdal/3.11.0/lib64/python3.9/site-packages, which
                # contains osgeo built for cp39. Letting it into our env causes
                # cp312 venv to find osgeo from that dir first and fail with
                # "No module named '_gdal'" (cp39 .so won't load in cp312).
                # activate.sh also unsets PYTHONPATH for the same reason.
                if k == "PYTHONPATH":
                    continue
                new_env[k] = v
    # Belt-and-suspenders: explicit removal in case it was set on
    # os.environ at script entry.
    new_env.pop("PYTHONPATH", None)
    new_env["PYTHONNOUSERSITE"] = "1"

    ok(f"HPC python: {python_cmd}")
    if gdal_lib_dir:
        ok(f"GDAL lib dir: {gdal_lib_dir}")
    else:
        warn("gdal-config not found; pip will use whatever libgdal it can find")
    return python_cmd, new_env, gdal_lib_dir

# -------- Non-HPC: Python 3.11 resolution --------

def resolve_python_311(platform: str, uv: str) -> str:
    """
    Find or install Python 3.11. Returns either a name uv accepts (`3.11`) or an
    absolute path. We always defer to `uv venv --python 3.11`, which itself
    discovers system 3.11 or downloads a standalone build if needed.
    """
    candidates = ["python3.11", "py -3.11"] if platform != "windows" else ["py -3.11", "python3.11"]
    for c in candidates:
        # `py -3.11` is a launcher invocation; test with --version
        try:
            r = subprocess.run(c.split(), capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and "3.11" in (r.stdout + r.stderr):
                ok(f"Found system Python 3.11: {c}")
                return "3.11"  # let uv resolve it; it discovers system 3.11s
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    info("System Python 3.11 not found; uv will download a standalone build")
    # `uv python install` is idempotent
    run([uv, "python", "install", "3.11"])
    return "3.11"

# -------- Windows: Gohlke wheels --------
# Mirrors geocif/pyproject.toml [tool.uv.sources]. tool.uv.sources is honored
# only when uv operates on the geocif project itself (editable/uv sync). When
# installing geocif from PyPI, uv ignores those overrides and tries to build
# from sdist, which fails for GDAL on Windows. So we pre-install the wheels.
WINDOWS_WHEELS = [
    "https://github.com/cgohlke/geospatial-wheels/releases/download/v2025.3.30/gdal-3.10.2-cp311-cp311-win_amd64.whl",
    "https://github.com/cgohlke/geospatial-wheels/releases/download/v2025.3.30/rasterio-1.4.3-cp311-cp311-win_amd64.whl",
    "https://github.com/cgohlke/geospatial-wheels/releases/download/v2025.3.30/shapely-2.0.7-cp311-cp311-win_amd64.whl",
    "https://github.com/cgohlke/geospatial-wheels/releases/download/v2025.3.30/pyproj-3.7.1-cp311-cp311-win_amd64.whl",
    "https://github.com/cgohlke/geospatial-wheels/releases/download/v2025.3.30/rtree-1.4.0-cp311-cp311-win_amd64.whl",
    "https://github.com/cgohlke/geospatial-wheels/releases/download/v2025.3.30/fiona-1.10.1-cp311-cp311-win_amd64.whl",
]

# -------- Venv + install --------

def create_venv(uv: str, venv_dir: pathlib.Path, python_spec: str, env: dict | None = None) -> None:
    info(f"Creating venv at {venv_dir} (python={python_spec})")
    run([uv, "venv", str(venv_dir), "--python", python_spec], env=env)

def venv_python(venv_dir: pathlib.Path, platform: str) -> pathlib.Path:
    if platform == "windows":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"

def _patchelf_osgeo_libgdal(venv_dir: pathlib.Path, gdal_lib_dir: str) -> None:
    """Rewrite osgeo/_*.so NEEDED entries so they request the module's libgdal
    soname (e.g. libgdal.so.37) instead of whatever older one the linker
    happened to find (e.g. anaconda's libgdal.so.36).

    See callsite for the full rationale. Assumes patchelf has already been
    installed into the venv (we add it to GDAL build deps).
    """
    patchelf = venv_dir / "bin" / "patchelf"
    if not patchelf.exists():
        warn(f"patchelf binary not in venv ({patchelf}); skipping soname patch")
        return

    # Resolve the target SONAME from the module's libgdal.so (a symlink).
    libgdal_canonical = pathlib.Path(gdal_lib_dir) / "libgdal.so"
    if not libgdal_canonical.exists():
        warn(f"{libgdal_canonical} not found; skipping soname patch")
        return
    r = subprocess.run(
        [str(patchelf), "--print-soname", str(libgdal_canonical)],
        capture_output=True, text=True, check=False,
    )
    target = (r.stdout or "").strip()
    if not target:
        warn(f"Could not read SONAME from {libgdal_canonical}; skipping soname patch")
        return
    info(f"Target libgdal SONAME: {target}")

    osgeo_dir = None
    for pylib in (venv_dir / "lib").glob("python*"):
        cand = pylib / "site-packages" / "osgeo"
        if cand.exists():
            osgeo_dir = cand
            break
    if not osgeo_dir:
        warn("osgeo/ dir not found in venv; skipping soname patch")
        return

    patched = 0
    for so in sorted(osgeo_dir.glob("_*.so")):
        n = subprocess.run(
            [str(patchelf), "--print-needed", str(so)],
            capture_output=True, text=True, check=False,
        )
        for line in (n.stdout or "").splitlines():
            line = line.strip()
            if line.startswith("libgdal.so.") and line != target:
                subprocess.run(
                    [str(patchelf), "--replace-needed", line, target, str(so)],
                    check=True,
                )
                info(f"  {so.name}: {line} -> {target}")
                patched += 1
    if patched:
        ok(f"patchelf: rewrote {patched} libgdal NEEDED entries to {target}")
    else:
        ok(f"patchelf: all osgeo extensions already reference {target}")

def install_geocif(
    uv: str,
    venv_dir: pathlib.Path,
    platform: str,
    editable_geocif: str | None,
    editable_geoprepare: str | None,
    gdal_lib_dir: str | None,
    base_env: dict | None,
) -> None:
    env = dict(base_env or os.environ)
    env["VIRTUAL_ENV"] = str(venv_dir)
    env["UV_PROJECT_ENVIRONMENT"] = str(venv_dir)
    env.pop("PYTHONPATH", None)
    env["PYTHONNOUSERSITE"] = "1"
    # Defense-in-depth: ensure no conda vars leak into pip's build environment.
    for k in list(env):
        if k.startswith("CONDA_") or k in ("_CE_CONDA", "_CE_M", "PYTHONHOME"):
            env.pop(k, None)

    # Windows-only: pre-install Gohlke wheels because uv ignores geocif's
    # [tool.uv.sources] when geocif is a PyPI install (not the active project).
    # Without this, uv tries to build gdal==3.10.2 from sdist and fails.
    if platform == "windows":
        info("Pre-installing Gohlke geospatial wheels (Windows cp311)...")
        run([uv, "pip", "install", *WINDOWS_WHEELS], env=env)

    # HPC-only: prepare LDFLAGS env for the source-built GDAL (applied later,
    # AFTER `uv pip install geocif`, because uv otherwise reinstalls gdal from
    # a PyPI wheel during the geocif resolution step — even if our pre-built
    # version is already in the venv. Scoping LDFLAGS to gdal_env keeps the
    # RPATH out of other packages' .so files.
    gdal_env = None
    if platform == "umd_hpc" and gdal_lib_dir:
        gdal_env = dict(env)
        gdal_env["LD_LIBRARY_PATH"] = (
            f"{gdal_lib_dir}:{env.get('LD_LIBRARY_PATH', '')}"
        )
        # --enable-new-dtags emits DT_RUNPATH instead of DT_RPATH. Under
        # RUNPATH, LD_LIBRARY_PATH is checked BEFORE the embedded path —
        # this is what we want, because GDAL's setup.py may prepend
        # /apps/python/3.12.9/anaconda3/lib (which has an older libgdal)
        # to RPATH. With RUNPATH semantics, our LD_LIBRARY_PATH
        # (module's libgdal 3.11.0 first) wins.
        gdal_env["LDFLAGS"] = (
            f"-L{gdal_lib_dir} "
            f"-Wl,-rpath,{gdal_lib_dir} "
            f"-Wl,--enable-new-dtags"
        )

    # Install geoprepare first if editable, so geocif's pin resolves to it
    if editable_geoprepare:
        info(f"Installing geoprepare (editable) from {editable_geoprepare}")
        run([uv, "pip", "install", "-e", editable_geoprepare], env=env)

    if editable_geocif:
        info(f"Installing geocif (editable) from {editable_geocif}")
        run([uv, "pip", "install", "-e", editable_geocif], env=env)
    else:
        info("Installing geocif from PyPI (pulls geoprepare transitively)")
        run([uv, "pip", "install", "geocif"], env=env)

    # Supplemental deps: belt-and-suspenders fallback for packages needed by
    # geocif's production import chain but possibly missing from the PyPI-
    # published geocif metadata. Idempotent — becomes a no-op once everything
    # is in the env. Mirrors the latest geocif/pyproject.toml core deps.
    # TODO: remove once the matching geocif release is on PyPI.
    #
    # Names only (no version pins). Pinning ad-hoc versions is fragile —
    # if a single pin is unsatisfiable on PyPI (e.g. `stabl>=1.0` when only
    # 0.0.1 is published), uv's resolver fails the whole batch.
    #
    # Split into small groups with check=False so one broken/missing
    # package doesn't abort the whole step.
    supplemental_groups = {
        "core": [
            "cartopy", "Rbeast", "scikit-learn", "bottleneck",
            "cachetools", "geopy", "scikit-image",
            "mapclassify", "pymannkendall", "pangres", "kneed", "lifelines",
        ],
        "spatial (esda/libpysal — used by beast_spatial.py)": [
            "esda", "libpysal",
        ],
        "ML trainers (ml/trainers.py)": [
            "crepes", "cubist", "mapie", "merf", "ngboost",
            "tabpfn-extensions", "treeple", "ydf",
            "desReg",
            # geospaNN excluded — install manually if needed
        ],
        "ML feature selection (ml/feature_selection.py)": [
            "BorutaShap", "arfs", "fasttreeshap", "feature-engine",
            "mrmr-selection", "powershap", "sklearn-genetic-opt",
            "stabl",  # PyPI has 0.0.1 placeholder; if you need full impl,
                      # install from github manually after this.
        ],
        "geoprepare's real transitive deps": [
            "pyresample", "cdsapi", "pymodis", "pyl4c", "beautifulsoup4",
            "wget", "rioxarray", "affine",
        ],
    }
    for label, pkgs in supplemental_groups.items():
        info(f"Supplemental ({label})")
        result = run([uv, "pip", "install", *pkgs], env=env, check=False)
        if result.returncode != 0:
            warn(f"  Group '{label}' had install issues — see above; continuing")

    # Post-supplemental: some ML feature-selection libs (notably `arfs` and
    # `fasttreeshap`) carry old shap pins that uv resolves by downgrading shap
    # to 0.45.x. shap 0.45 was built against numpy 1.x and ImportError's
    # against numpy 2.x ("module compiled using NumPy 1.x cannot be run in
    # NumPy 2.x"). Re-upgrade shap to the latest compatible release.
    info("Restoring latest shap (feature-selection group may have downgraded it)")
    run([uv, "pip", "install", "--upgrade", "--no-deps", "shap"], env=env, check=False)

    # pygeoutil is git-only (not on PyPI) and is imported by geocif/viz/plot.py.
    # PyPI forbids URL deps in published packages, so geocif's pyproject can't
    # declare it directly — the installer pulls it explicitly.
    info("Installing pygeoutil from git (tracks main)")
    run([uv, "pip", "install", "git+https://github.com/ritviksahajpal/pygeoutil.git"], env=env)

    # Strip CUDA/nvidia/triton packages. torch wheels for Linux pull these
    # in transitively (~3GB), but geocif's import chain is CPU-only. The
    # exclusion in geocif/pyproject.toml's `[tool.uv] override-dependencies`
    # is honored ONLY when geocif is the active uv project — when installed
    # from PyPI as a dependency, uv ignores it. So we uninstall here.
    # torch itself stays installed (CPU code paths work without nvidia-*).
    # check=False because many of these may not exist on Windows/macOS.
    info("Removing CUDA/nvidia/triton packages (CPU-only setup)")
    cuda_packages = [
        "cuda-bindings", "cuda-pathfinder", "cuda-toolkit",
        "nvidia-cublas", "nvidia-cuda-cupti", "nvidia-cuda-nvrtc",
        "nvidia-cuda-runtime", "nvidia-cudnn-cu13", "nvidia-cufft",
        "nvidia-cufile", "nvidia-curand", "nvidia-cusolver", "nvidia-cusparse",
        "nvidia-cusparselt-cu13", "nvidia-ml-py", "nvidia-nccl-cu13",
        "nvidia-nvjitlink", "nvidia-nvshmem-cu13", "nvidia-nvtx",
        "triton",
    ]
    run([uv, "pip", "uninstall", *cuda_packages], env=env, check=False)

    # HPC ONLY: now that all other packages are installed, force-rebuild GDAL
    # from source with our RPATH-embedding LDFLAGS. This must come LAST because
    # `uv pip install geocif` re-resolves and may install gdal from a PyPI
    # wheel (overwriting any earlier source build with one whose _gdal.so
    # links against a different libgdal — symptom: missing _gdal.so or
    # "No module named '_gdal'" on import).
    # --force-reinstall --no-deps overwrites gdal without touching anything
    # else; --no-binary gdal forces source build; --no-build-isolation uses the
    # venv's setuptools/numpy/cython for ABI consistency.
    if platform == "umd_hpc" and gdal_lib_dir and gdal_env is not None:
        info("Installing GDAL build deps (setuptools, wheel, numpy, cython, patchelf)")
        run([uv, "pip", "install",
             "setuptools<81", "wheel", "numpy", "cython", "patchelf"], env=env)
        info(f"Final source build of GDAL==3.11.0 against module libgdal at {gdal_lib_dir} (overwrites any wheel uv installed)")
        # --no-cache to avoid reusing a previous broken build artifact.
        run([uv, "pip", "install",
             "--no-binary", "gdal",
             "--no-build-isolation",
             "--no-cache",
             "--force-reinstall", "--no-deps",
             "gdal==3.11.0"], env=gdal_env)

        # Post-build patchelf: anaconda Python's baked-in LDSHARED puts
        # /apps/python/.../anaconda3/lib EARLIER in the link line than our
        # LDFLAGS' -L<gdal_lib_dir>. So `-lgdal` resolves to anaconda's older
        # libgdal.so.<N> (e.g. .so.36 = GDAL 3.10), and that soname gets
        # baked into NEEDED entries of every osgeo/_*.so. At runtime the
        # loader picks up anaconda's libgdal — symbol mismatch
        # ("undefined symbol: CPLQuietWarningsErrorHandler" etc.).
        # Rewriting NEEDED to the module's soname (e.g. libgdal.so.37) makes
        # the loader pick up the module's libgdal, which DOES have the symbols
        # the bindings were compiled against (gdal-config 3.11 headers).
        _patchelf_osgeo_libgdal(venv_dir, gdal_lib_dir)

        # Sanity check: look specifically for the _gdal extension (NOT
        # _gdalconst, _gdal_array, etc. — those are separate, smaller
        # extensions; a build can ship _gdalconst.so but skip the main
        # _gdal.so silently if something is wrong).
        gdal_so_found = False
        osgeo_dir = None
        for pylib in (venv_dir / "lib").glob("python*"):
            cand = pylib / "site-packages" / "osgeo"
            if cand.exists():
                osgeo_dir = cand
                break
        if osgeo_dir:
            main_gdal_so = (
                list(osgeo_dir.glob("_gdal.cpython-*.so"))
                + list(osgeo_dir.glob("_gdal.abi3.so"))
                + list(osgeo_dir.glob("_gdal.so"))
            )
            if main_gdal_so:
                ok(f"GDAL main extension: {main_gdal_so[0].name}")
                gdal_so_found = True
                # Confirm RPATH/RUNPATH was baked into the .so
                if shutil.which("readelf"):
                    rp = subprocess.run(
                        ["readelf", "-d", str(main_gdal_so[0])],
                        capture_output=True, text=True, check=False,
                    )
                    rpath_lines = [
                        ln for ln in (rp.stdout or "").splitlines()
                        if "RPATH" in ln or "RUNPATH" in ln
                    ]
                    if rpath_lines:
                        for ln in rpath_lines:
                            info(f"  {ln.strip()}")
                    else:
                        warn("  No RPATH/RUNPATH in _gdal.so — runtime may fail to find libgdal")
                # Run ldd to show whether the loader actually finds libgdal
                # (using the same env as the verify subprocess will).
                if shutil.which("ldd"):
                    ldd_env = dict(env)
                    if gdal_lib_dir:
                        ldd_env["LD_LIBRARY_PATH"] = (
                            f"{gdal_lib_dir}:{env.get('LD_LIBRARY_PATH', '')}"
                        )
                    ldd_res = subprocess.run(
                        ["ldd", str(main_gdal_so[0])],
                        capture_output=True, text=True, check=False,
                        env=ldd_env,
                    )
                    info("  ldd _gdal.so (libgdal resolution):")
                    for ln in (ldd_res.stdout or "").splitlines():
                        if "libgdal" in ln or "not found" in ln:
                            info(f"    {ln.strip()}")
            else:
                other_sos = sorted(p.name for p in osgeo_dir.glob("_*.so"))
                err("_gdal.cpython-*.so NOT FOUND in venv site-packages.")
                err(f"Found other extensions in osgeo/: {other_sos}")
                err("The GDAL source build silently skipped the main extension.")
                err("Likely fix: clear the uv build cache and rerun")
                err(f"  rm -rf {os.environ.get('UV_CACHE_DIR', '~/.cache/uv')}/builds-v0")
                err(f"  python install.py --yes")
        else:
            warn("osgeo/ dir not found in venv — gdal install completely failed")

# -------- Activation scripts --------

ACTIVATE_SH_LOCAL = """\
#!/usr/bin/env bash
# Activation script for geo-stack (local Linux/macOS)
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
unset PYTHONPATH
export PYTHONNOUSERSITE=1
source "$HERE/.venv/bin/activate"
echo "[ok] geo-stack activated: $(python --version 2>&1)"
"""

ACTIVATE_SH_HPC_TEMPLATE = """\
#!/usr/bin/env bash
# Activation script for geo-stack (UMD HPC) — minimizes conda, uses modules + uv
HERE="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"

# Skip if already active.
if [[ "$VIRTUAL_ENV" == *"geo-stack"* ]]; then
    echo "geo-stack is already active"
    return 0 2>/dev/null || exit 0
fi

# Strip conda dirs from PATH and unset conda vars. gsapp auto-activates (base)
# via /etc/profile.d/conda.sh on every login — we don't fight that with
# `conda deactivate` (which depends on conda being callable and may misbehave);
# we just remove conda's PATH entries and clear its env vars.
PATH=$(echo "$PATH" | tr ':' '\\n' \\
    | grep -viE '(miniconda|anaconda|/conda/|conda3)' \\
    | paste -sd: -)
export PATH
unset CONDA_DEFAULT_ENV CONDA_PREFIX CONDA_SHLVL CONDA_PYTHON_EXE \\
      CONDA_EXE CONDA_PROMPT_MODIFIER _CE_CONDA _CE_M PYTHONHOME

# uv must be on PATH (installer adds $HOME/.local/bin to ~/.bashrc).
export PATH="$HOME/.local/bin:$PATH"

# Bootstrap `module` if not already a function (non-login shells skip
# /etc/profile.d/modules.sh).
if ! command -v module >/dev/null 2>&1; then
    for init in /etc/profile.d/modules.sh \\
                /usr/share/lmod/lmod/init/bash \\
                /apps/lmod/lmod/init/bash; do
        [ -r "$init" ] && . "$init" && break
    done
fi

if command -v module >/dev/null 2>&1; then
    module purge 2>/dev/null || true
    {module_loads}
else
    echo "[!]  module command unavailable -- GDAL imports may fail"
fi

# Ensure the GDAL module's libgdal is ahead of anything else on the loader path.
GDAL_LIB="{gdal_lib}"
if [[ -n "$GDAL_LIB" && -d "$GDAL_LIB" ]]; then
    export LD_LIBRARY_PATH="${{GDAL_LIB}}:${{LD_LIBRARY_PATH:-}}"
fi

unset PYTHONPATH
export PYTHONNOUSERSITE=1
source "$HERE/.venv/bin/activate"

echo "[ok] geo-stack activated: $(python --version 2>&1)"
python -c "from osgeo import gdal" 2>/dev/null && echo "[ok] GDAL import OK" \\
    || echo "[!]  GDAL import failed -- check module loading"
"""

ACTIVATE_PS1 = """\
# Activation script for geo-stack (Windows PowerShell) — self-contained
# Does NOT call uv-shipped activate scripts (which uv often skips creating).
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $Here ".venv"
$ScriptsDir = Join-Path $VenvDir "Scripts"

# Save originals so `deactivate` can restore them (only on first activation
# of this shell, so re-activating doesn't double-decorate PATH/PROMPT).
if (-not $script:_GeoOldPath)   { $script:_GeoOldPath   = $env:PATH }
if (-not $script:_GeoOldPrompt) { $script:_GeoOldPrompt = (Get-Item function:prompt).ScriptBlock }

$env:VIRTUAL_ENV = $VenvDir
$env:PATH = "$ScriptsDir;$script:_GeoOldPath"
$env:PYTHONNOUSERSITE = "1"
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue

function global:prompt { "(geo-stack) " + (& $script:_GeoOldPrompt) }

function global:deactivate {
    if ($script:_GeoOldPath) {
        $env:PATH = $script:_GeoOldPath
        $script:_GeoOldPath = $null
    }
    if ($script:_GeoOldPrompt) {
        Set-Item function:global:prompt $script:_GeoOldPrompt
        $script:_GeoOldPrompt = $null
    }
    Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
    Remove-Item Env:PYTHONNOUSERSITE -ErrorAction SilentlyContinue
    Write-Host "[ok] geo-stack deactivated"
}

Write-Host "[ok] geo-stack activated: $(& "$ScriptsDir\\python.exe" --version 2>&1)"
"""

ACTIVATE_BAT = """\
@echo off
REM Activation script for geo-stack (Windows cmd.exe) — self-contained
REM Does NOT call uv-shipped activate.bat (which uv often skips creating).
set "HERE=%~dp0"
set "VIRTUAL_ENV=%HERE%.venv"
set "GEO_SCRIPTS=%VIRTUAL_ENV%\\Scripts"

REM Save originals once so deactivate.bat can restore them.
if not defined _GEO_OLD_PATH   set "_GEO_OLD_PATH=%PATH%"
if not defined _GEO_OLD_PROMPT set "_GEO_OLD_PROMPT=%PROMPT%"

REM Always rebuild PATH/PROMPT from saved originals so re-activation is idempotent.
set "PATH=%GEO_SCRIPTS%;%_GEO_OLD_PATH%"
if not defined PROMPT set "_GEO_OLD_PROMPT=$P$G"
set "PROMPT=(geo-stack) %_GEO_OLD_PROMPT%"

set "PYTHONNOUSERSITE=1"
set "PYTHONPATH="

echo [ok] geo-stack activated
"%GEO_SCRIPTS%\\python.exe" --version
"""

DEACTIVATE_BAT = """\
@echo off
REM Deactivate geo-stack — restores PATH/PROMPT, unsets VIRTUAL_ENV.
REM Use this instead of `deactivate` (which conda hijacks on Windows).

if defined _GEO_OLD_PATH (
    set "PATH=%_GEO_OLD_PATH%"
    set "_GEO_OLD_PATH="
)
if defined _GEO_OLD_PROMPT (
    set "PROMPT=%_GEO_OLD_PROMPT%"
    set "_GEO_OLD_PROMPT="
)
set "VIRTUAL_ENV="
set "PYTHONNOUSERSITE="
set "GEO_SCRIPTS="
echo [ok] geo-stack deactivated
"""

def write_activation(install_dir: pathlib.Path, platform: str, gdal_lib_dir: str | None) -> None:
    if platform == "windows":
        (install_dir / "activate.ps1").write_text(ACTIVATE_PS1)
        (install_dir / "activate.bat").write_text(ACTIVATE_BAT)
        (install_dir / "deactivate.bat").write_text(DEACTIVATE_BAT)
        ok(f"Wrote activate.ps1, activate.bat, deactivate.bat in {install_dir}")
        return

    if platform == "umd_hpc":
        # Confirmed exact module names on gsapp (no short-form aliases like
        # `python/3.12/anaconda` exist; the only valid IDs are dotted versions).
        module_loads = "\n    ".join([
            'for m in python/3.12.9/anaconda python/3.11.7/anaconda; do module load "$m" 2>/dev/null && break; done',
            'for m in rh9/gdal/3.11.0 rh9/gdal/3.5.3 gdal/3.1.0 gdal; do module load "$m" 2>/dev/null && break; done',
        ])
        body = ACTIVATE_SH_HPC_TEMPLATE.format(
            module_loads=module_loads,
            gdal_lib=gdal_lib_dir or "",
        )
        path = install_dir / "activate.sh"
        path.write_text(body)
        path.chmod(0o755)
        ok(f"Wrote activate.sh (HPC) in {install_dir}")
        return

    # Generic Linux / macOS
    path = install_dir / "activate.sh"
    path.write_text(ACTIVATE_SH_LOCAL)
    path.chmod(0o755)
    ok(f"Wrote activate.sh (local) in {install_dir}")

# -------- ~/.bashrc (HPC only, minimal) --------

BASHRC_BEGIN = "# BEGIN geo-stack installer"
BASHRC_END = "# END geo-stack installer"

def write_bashrc_block(force: bool) -> None:
    bashrc = pathlib.Path.home() / ".bashrc"
    if not bashrc.exists() and not force:
        return
    existing = bashrc.read_text() if bashrc.exists() else ""
    # Strip prior block (idempotent)
    if BASHRC_BEGIN in existing:
        lines = existing.splitlines(keepends=True)
        out, skipping = [], False
        for ln in lines:
            if BASHRC_BEGIN in ln:
                skipping = True
                continue
            if BASHRC_END in ln:
                skipping = False
                continue
            if not skipping:
                out.append(ln)
        existing = "".join(out)
    block = f'\n{BASHRC_BEGIN}\nexport PATH="$HOME/.local/bin:$PATH"\n{BASHRC_END}\n'
    bashrc.write_text(existing + block)
    ok(f"Updated {bashrc} (uv on PATH)")

# -------- Verification --------

def verify(venv_dir: pathlib.Path, platform: str, env: dict | None) -> None:
    py = venv_python(venv_dir, platform)
    info("Verifying installation...")
    script = textwrap.dedent("""
        import sys
        import traceback
        failed = []
        # Top-level imports (with version reporting)
        for mod in ("numpy", "pandas", "osgeo.gdal", "rasterio", "geopandas",
                    "geoprepare", "geocif"):
            try:
                parts = mod.split(".")
                m = __import__(mod)
                for p in parts[1:]:
                    m = getattr(m, p)
                v = getattr(m, "__version__", "?")
                print(f"[ok] {mod} {v}")
            except Exception as e:
                print(f"[err] {mod}: {type(e).__name__}: {e}")
                failed.append(mod)
                # For osgeo specifically: dlopen the .so directly to surface
                # the real loader error (Python sometimes masks it as
                # "ModuleNotFoundError: No module named '_gdal'").
                if mod == "osgeo.gdal":
                    import os, glob, ctypes
                    print("    [diag] full traceback:")
                    traceback.print_exc()
                    so_glob = os.path.join(
                        sys.prefix, "lib",
                        f"python{sys.version_info.major}.{sys.version_info.minor}",
                        "site-packages", "osgeo", "_gdal*.so",
                    )
                    sos = sorted(glob.glob(so_glob))
                    print(f"    [diag] osgeo/_gdal*.so files found: {len(sos)}")
                    for so in sos:
                        print(f"      {os.path.basename(so)} ({os.path.getsize(so)} bytes)")
                    # Try ctypes.CDLL to get the real OSError dlopen message
                    main_so = next(
                        (s for s in sos if "_gdal.cpython" in s or s.endswith("/_gdal.so")),
                        None,
                    )
                    if main_so:
                        print(f"    [diag] ctypes.CDLL({main_so!r}):")
                        try:
                            ctypes.CDLL(main_so)
                            print("      LOAD OK (then why did import fail?)")
                        except OSError as dlerr:
                            print(f"      OSError: {dlerr}")
                    print(f"    [diag] LD_LIBRARY_PATH = {os.environ.get('LD_LIBRARY_PATH', '<unset>')}")
                    print(f"    [diag] PYTHONPATH = {os.environ.get('PYTHONPATH', '<unset>')}")
                    print(f"    [diag] sys.path[:6] = {sys.path[:6]}")
        # geocif submodules that pull in the bulk of production deps
        # (cartopy via viz.plot, Rbeast via production_analysis, sklearn via geocif.geocif)
        for mod in ("geocif.viz.plot", "geocif.yield_outlook",
                    "geocif.production_analysis.beast_runner"):
            try:
                __import__(mod)
                print(f"[ok] {mod}")
            except Exception as e:
                print(f"[err] {mod}: {type(e).__name__}: {e}")
                failed.append(mod)
        sys.exit(1 if failed else 0)
    """)
    # Use the run() helper so its output is captured + relayed through
    # the (potentially log-teed) sys.stdout. Direct subprocess.run inherits
    # fd 1/2 and bypasses Python-level logging.
    result = run([str(py), "-c", script], env=env, check=False)
    if result.returncode != 0:
        warn("Some packages failed to import (see above)")
    else:
        ok("All critical packages imported successfully")

# -------- install_info.txt --------

def write_install_info(install_dir: pathlib.Path, platform: str, python_spec: str,
                       gdal_lib_dir: str | None) -> None:
    lines = [
        "geo-stack installation summary",
        "=" * 40,
        f"Platform: {platform}",
        f"Install dir: {install_dir}",
        f"Python: {python_spec}",
        f"GDAL lib dir: {gdal_lib_dir or '(n/a)'}",
        f"OS: {platform_mod.platform()}",
        "",
        "Activation:",
    ]
    if platform == "windows":
        lines.append(f"  PowerShell:   . {install_dir / 'activate.ps1'}")
        lines.append(f"  cmd.exe:      {install_dir / 'activate.bat'}")
        lines.append("")
        lines.append("Deactivation:")
        lines.append(f"  cmd.exe:      {install_dir / 'deactivate.bat'}")
        lines.append( "  PowerShell:   deactivate   (function set by activate.ps1)")
        lines.append( "  NOTE: do NOT use plain 'deactivate' in cmd.exe — conda hijacks it.")
    else:
        lines.append(f"  source {install_dir / 'activate.sh'}")
        lines.append("")
        lines.append("Deactivation: deactivate")
    lines += [
        "",
        "Day-to-day usage:",
        "  - Activate the env each new shell (command above).",
        "  - Add/upgrade packages: uv pip install [--upgrade] <pkg>",
        "  - Upgrade geocif:       uv pip install --upgrade geocif",
        "",
        "Re-run install.py ONLY to rebuild from scratch (e.g. broken env,",
        "switching Python version). It will prompt before deleting the venv.",
    ]
    (install_dir / "installation_info.txt").write_text("\n".join(lines) + "\n")

# -------- Default install base --------

def default_install_base(platform: str) -> pathlib.Path:
    if platform == "umd_hpc":
        gpfs_user = UMD_HPC_MARKER / os.environ.get("USER", "")
        if gpfs_user.parent.exists():
            return gpfs_user
    if platform == "windows":
        return pathlib.Path(os.environ.get("USERPROFILE", "C:\\")) / "geo-stack-env"
    return pathlib.Path.home() / "geo-stack-env"

# -------- CLI --------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Cross-platform geocif/geoprepare installer.")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--install-base", type=pathlib.Path, default=None,
                   help="Parent dir for the geo-stack env (default per platform).")
    p.add_argument("--editable", type=str, default=None,
                   help="Install geocif as editable from this local path.")
    p.add_argument("--editable-geoprepare", type=str, default=None,
                   help="Install geoprepare as editable from this local path.")
    p.add_argument("--platform", choices=["auto", "windows", "umd_hpc", "linux", "macos"],
                   default="auto", help="Override platform detection.")
    p.add_argument("--write-shell-rc", action="store_true",
                   help="On non-HPC, write a uv-PATH line to ~/.bashrc.")
    p.add_argument("--yes", "-y", action="store_true",
                   help="Skip interactive confirmation.")
    p.add_argument("--log-file", type=pathlib.Path, default=None,
                   help="Tee all output (including subprocess stdout/stderr) to this file.")
    return p.parse_args()

def main() -> None:
    args = parse_args()

    # Fail fast in non-interactive shells without --yes (e.g. SLURM batch jobs);
    # the input() prompts would otherwise hang waiting on stdin forever.
    if not args.yes and not sys.stdin.isatty():
        raise SystemExit(
            "Non-interactive shell detected (no TTY). Re-run with --yes."
        )

    # Set up log file tee BEFORE any other output so the log captures
    # everything from the platform-detection step onward.
    global _LOG_FH
    if args.log_file:
        log_path = args.log_file.expanduser().resolve()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        _LOG_FH = open(log_path, "a", buffering=1)
        sys.stdout = _Tee(sys.__stdout__, _LOG_FH)
        sys.stderr = _Tee(sys.__stderr__, _LOG_FH)
        info(f"Logging to: {log_path}")

    info(f"installer version: {__version__}")
    platform = args.platform if args.platform != "auto" else detect_platform()
    info(f"Detected platform: {platform}")

    install_base = args.install_base or default_install_base(platform)
    install_base = install_base.expanduser().resolve()
    install_dir = install_base / "geo-stack"
    venv_dir = install_dir / ".venv"

    print("=" * 50)
    print(f"Platform:     {platform}")
    print(f"Install dir:  {install_dir}")
    print(f"Editable geocif:     {args.editable or '(install from PyPI)'}")
    print(f"Editable geoprepare: {args.editable_geoprepare or '(transitive)'}")
    print("=" * 50)
    if not args.yes:
        reply = input("Continue? [y/N] ").strip().lower()
        if reply not in ("y", "yes"):
            raise SystemExit("Aborted.")

    install_dir.mkdir(parents=True, exist_ok=True)

    # HPC: redirect uv/pip caches to GPFS. Home dirs on gsapp have a ~10GB
    # quota; pyarrow alone is ~100MB extracted and uv pulls 150+ packages.
    # Default ~/.cache/uv would fill the quota fast. Also: cache on the same
    # filesystem as the venv enables hardlinks (no "Failed to hardlink"
    # warnings, faster installs).
    if platform == "umd_hpc":
        uv_cache = install_dir / ".uv-cache"
        pip_cache = install_dir / ".pip-cache"
        uv_cache.mkdir(parents=True, exist_ok=True)
        pip_cache.mkdir(parents=True, exist_ok=True)
        os.environ["UV_CACHE_DIR"] = str(uv_cache)
        os.environ["PIP_CACHE_DIR"] = str(pip_cache)
        info(f"uv cache: {uv_cache}")

    if venv_dir.exists():
        # Partial venv (missing pyvenv.cfg) = no usable env — auto-rebuild
        # without prompting. Catches the "antivirus ate Lib/" / Ctrl-C-mid-install
        # case where the dir exists but the env is unusable.
        if not (venv_dir / "pyvenv.cfg").exists():
            warn(f"Partial venv at {venv_dir} (no pyvenv.cfg) — rebuilding")
            shutil.rmtree(venv_dir)
        else:
            warn(f"Existing venv found at {venv_dir}")
            if not args.yes:
                reply = input("Delete and reinstall? [y/N] ").strip().lower()
                if reply not in ("y", "yes"):
                    raise SystemExit("Aborted (existing venv preserved).")
            shutil.rmtree(venv_dir)

    uv = ensure_uv(platform)

    base_env: dict | None = None
    gdal_lib_dir: str | None = None
    if platform == "umd_hpc":
        python_cmd, base_env, gdal_lib_dir = load_hpc_modules()
        python_spec = python_cmd
    else:
        python_spec = resolve_python_311(platform, uv)

    create_venv(uv, venv_dir, python_spec, env=base_env)

    install_geocif(
        uv, venv_dir, platform,
        editable_geocif=args.editable,
        editable_geoprepare=args.editable_geoprepare,
        gdal_lib_dir=gdal_lib_dir,
        base_env=base_env,
    )

    write_activation(install_dir, platform, gdal_lib_dir)
    write_install_info(install_dir, platform, python_spec, gdal_lib_dir)

    if platform == "umd_hpc":
        write_bashrc_block(force=True)
    elif args.write_shell_rc and platform in ("linux", "macos"):
        write_bashrc_block(force=True)

    verify(venv_dir, platform, base_env)

    print()
    print("=" * 50)
    ok("Installation complete!")
    print("=" * 50)
    if platform == "windows":
        print(f"Activate (PowerShell):   . '{install_dir / 'activate.ps1'}'")
        print(f"Activate (cmd):          {install_dir / 'activate.bat'}")
        print(f"Deactivate (cmd):        {install_dir / 'deactivate.bat'}")
        print(f"Deactivate (PowerShell): deactivate   (function defined by activate.ps1)")
    else:
        print(f"Activate:   source {install_dir / 'activate.sh'}")
        print(f"Deactivate: deactivate")
    print()
    print("Day-to-day usage:")
    print("  - Activate the env each new shell (command above).")
    print("  - Install/upgrade packages: uv pip install [--upgrade] <pkg>")
    print()
    print("You do NOT need to re-run install.py for normal use.")
    print("Run it again only to rebuild the env from scratch")
    print("(broken env, switching Python version, etc.).")
    print()
    print(f"Full notes: {install_dir / 'installation_info.txt'}")
    print()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        err("Interrupted")
        sys.exit(130)
