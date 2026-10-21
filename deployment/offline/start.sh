#!/bin/sh
set -eu
cd -- "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
port=${1:-8765}
name=${2:-cacr2026t4pmr7-web}
case "$port" in ''|*[!0-9]*) echo 'Port must be an integer.' >&2; exit 2 ;; esac
[ "$port" -ge 1024 ] && [ "$port" -le 65535 ] || exit 2
command -v docker >/dev/null || { echo 'Install and start Docker first.' >&2; exit 1; }
[ "$(docker info --format '{{.OSType}}')" = linux ] || exit 1
# These three one-line metadata files accompany the JSON release manifest.
image=$(tr -d '\r' < IMAGE_ID)
archive=$(tr -d '\r' < IMAGE_ARCHIVE)
case "$archive" in ''|*/*|*\\*) echo 'Invalid archive name.' >&2; exit 2 ;; esac
if command -v sha256sum >/dev/null; then
    sha256sum --check IMAGE_SHA256SUMS.txt
else
    shasum -a 256 --check IMAGE_SHA256SUMS.txt
fi
if ! docker image inspect "$image" >/dev/null 2>&1; then
    docker load --input "$archive"
fi
[ "$(docker image inspect "$image" --format '{{.Id}}')" = "$image" ] || exit 1
if [ -n "$(docker container ls -a --filter "name=^/$name\$" --format '{{.Names}}')" ]; then
    echo "Container $name already exists. Choose another name or explicitly remove it." >&2
    exit 1
fi
docker run --detach --pull=never --init --name "$name" --shm-size=256m \
    --publish "127.0.0.1:$port:8765" "$image" web
i=0
until docker exec "$name" /opt/sage/bin/python /opt/ibme/check_runtime.py --health >/dev/null 2>&1; do
    [ "$(docker inspect --format '{{.State.Running}}' "$name")" = true ] || { docker logs "$name"; exit 1; }
    i=$((i + 1))
    [ "$i" -lt 90 ] || { docker logs "$name"; exit 1; }
    sleep 1
done
printf 'Open http://127.0.0.1:%s/\nStop: docker stop %s\nRemove after stopping: docker rm %s\n' "$port" "$name" "$name"
