#!/usr/bin/env bash
# Task-scoped Linux prerequisites. No experiments, disks or SSH configuration.
set -euo pipefail

prepare_estimator() {
    local estimator_dir=$1
    local estimator_revision=53da5982597709ba0fdf94ea37a84d822310fd84
    if [ ! -d "$estimator_dir/.git" ]; then
        if [ -d "$estimator_dir" ] && [ -n "$(ls -A -- "$estimator_dir")" ]; then
            echo "Existing estimator directory is not an empty checkout" >&2
            return 1
        fi
        git init -q "$estimator_dir"
    fi
    if ! git -C "$estimator_dir" remote get-url origin >/dev/null 2>&1; then
        git -C "$estimator_dir" remote add origin https://github.com/malb/lattice-estimator.git
    fi
    test -z "$(git -C "$estimator_dir" status --porcelain --untracked-files=all)"
    # A failed fetch leaves .git behind. Resume from object availability,
    # rather than mistaking that directory for a completed installation.
    if ! git -C "$estimator_dir" cat-file -e "$estimator_revision^{commit}" 2>/dev/null; then
        git -C "$estimator_dir" fetch --depth=1 origin "$estimator_revision"
    fi
    git -C "$estimator_dir" checkout --detach "$estimator_revision"
    test "$(git -C "$estimator_dir" rev-parse HEAD)" = "$estimator_revision"
    test -z "$(git -C "$estimator_dir" status --porcelain --untracked-files=all)"
}

ensure_sage_environment() {
    local conda_binary=$1
    local sage_prefix=$2
    local operation=create
    if [ -d "$sage_prefix/conda-meta" ]; then
        # `conda create -y` removes an existing environment in current Conda.
        # Resume by installing missing requirements into its existing prefix.
        operation=install
    elif [ -e "$sage_prefix" ]; then
        echo "Existing Sage prefix is not a conda environment" >&2
        return 1
    fi
    "$conda_binary" "$operation" -y -p "$sage_prefix" \
        --override-channels -c conda-forge --strict-channel-priority \
        python=3.12 sage numpy scipy pytest psutil gmpy2 'cryptography>=49,<51'
}

task_dir=${1:?Usage: prepare_environment.sh TASK_DIRECTORY}
mkdir -p "$task_dir/environment"
task_dir=$(cd -- "$task_dir" && pwd -P)
# Preserve old evidence, but remove its active-ready meaning before changing
# packages. A failed/resumed preparation must never leave a stale ready flag.
for previous in environment-ready.json runtime.env; do
    if [ -e "$task_dir/environment/$previous" ] || [ -L "$task_dir/environment/$previous" ]; then
        mkdir -p "$task_dir/environment/history"
        previous_dir=$(mktemp -d "$task_dir/environment/history/previous.XXXXXX")
        mv -- "$task_dir/environment/$previous" "$previous_dir/$previous"
    fi
done
exec > >(tee -a "$task_dir/environment/prepare-all.log") 2>&1
date -u +%FT%TZ
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq build-essential pkg-config ca-certificates curl git \
    python3-venv libssl-dev libmpfr-dev libgmp-dev libmpc-dev \
    libopenblas-dev libquadmath0 time
python3 -m venv "$task_dir/venv"
"$task_dir/venv/bin/python" -m pip install --only-binary=:all: \
    'setuptools>=68' wheel numpy scipy pytest psutil gmpy2 'cryptography>=49,<51'
"$task_dir/venv/bin/python" -m pip freeze > "$task_dir/environment/requirements.lock.txt"
if [ ! -x "$HOME/miniconda3/bin/conda" ]; then
    installer=Miniforge3-Linux-x86_64.sh
    cd "$task_dir/environment"
    # Frozen from the publisher's release API on 2026-10-19; a mirror is
    # accepted only if its bytes match the publisher's pinned SHA-256.
    expected=281b0ac7d550802efc81af633225a5e6116d29ae72f3ab4eae7168c3931a4c05
    if ! curl -fL --retry 1 --speed-limit 1048576 --speed-time 15 -o "$installer" \
        "https://github.com/conda-forge/miniforge/releases/download/26.7.2-0/$installer"; then
        curl -fL --retry 1 --max-time 180 -o "$installer" \
            "https://mirrors.tuna.tsinghua.edu.cn/github-release/conda-forge/miniforge/LatestRelease/$installer"
    fi
    printf '%s  %s\n' "$expected" "$installer" | sha256sum -c -
    bash "$installer" -b -p "$HOME/miniconda3"
fi
ensure_sage_environment "$HOME/miniconda3/bin/conda" "$HOME/miniconda3/envs/sage"
"$HOME/miniconda3/bin/conda" list -p "$HOME/miniconda3/envs/sage" --explicit \
    > "$task_dir/environment/sage-explicit.lock.txt"
"$HOME/miniconda3/envs/sage/bin/python" -c \
    'import sage.all,numpy,scipy,pytest,psutil,gmpy2,cryptography; print("all task imports passed")'
estimator_dir="$task_dir/environment/lattice-estimator"
prepare_estimator "$estimator_dir"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$estimator_dir" \
    "$HOME/miniconda3/envs/sage/bin/python" -B -c 'import sage.all,estimator; print("estimator import passed; no cost estimate executed")'
pkg-config --modversion openssl mpfr gmp openblas
g++ --version | head -1
df -h "$task_dir"
date -u +%FT%TZ
