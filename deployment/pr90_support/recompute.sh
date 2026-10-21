#!/bin/sh
set -eu
section=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
materials=$(dirname -- "$section")
output=${1:-"$(dirname -- "$materials")/$(basename -- "$materials")-recomputed-$(date +%Y%m%d-%H%M%S)"}
control=${2:-}
case "$control" in ''|--self-test) ;; *) echo 'Second argument must be --self-test.' >&2; exit 2 ;; esac
set -- "$materials"/06_*
[ "$#" -eq 1 ] && [ -d "$1" ] || { echo 'Expected one 06 runtime directory.' >&2; exit 2; }
runtime=$1
image=$(tr -d '\r' < "$runtime/IMAGE_ID")
archive=$(tr -d '\r' < "$runtime/IMAGE_ARCHIVE")
[ "$(docker info --format '{{.OSType}}')" = linux ] || exit 1
if ! docker image inspect "$image" >/dev/null 2>&1; then
    (cd -- "$runtime" && sha256sum --check IMAGE_SHA256SUMS.txt && docker load --input "$archive")
fi
[ "$(docker image inspect "$image" --format '{{.Id}}')" = "$image" ] || exit 1
mkdir -p -- "$output"
output=$(CDPATH= cd -- "$output" && pwd)
case "$output/" in "$materials/"*) echo 'Output must be outside submitted materials.' >&2; exit 2 ;; esac
[ -z "$(ls -A -- "$output")" ] || { echo 'Output directory must be empty.' >&2; exit 2; }
set -- docker run --rm --pull=never --network none --read-only --tmpfs /tmp:rw,exec,size=1g \
    --user "$(id -u):$(id -g)" \
    --mount "type=bind,source=$materials,target=/submission,readonly" \
    --mount "type=bind,source=$output,target=/output" "$image" python \
    "/submission/$(basename -- "$section")/recompute.py" --materials /submission --output /output
if [ -n "$control" ]; then set -- "$@" "$control"; fi
"$@"
printf 'Recomputed results: %s\n' "$output"
