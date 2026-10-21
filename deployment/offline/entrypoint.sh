#!/bin/sh
set -eu
# Conda packages and LATTE require this explicit CPU feature level.
if ! grep -qm1 ' avx2 ' /proc/cpuinfo || ! grep -qm1 ' aes ' /proc/cpuinfo; then
    echo 'This image requires an x86-64-v3 CPU with AVX2 and AES-NI.' >&2
    exit 64
fi
case "${1:-web}" in
    web)
        if [ "$#" -gt 0 ]; then shift; fi
        exec /opt/sage/bin/python -m ibme.webui --host 0.0.0.0 --port 8765 "$@"
        ;;
    check)
        shift
        exec /opt/sage/bin/python /opt/ibme/check_runtime.py "$@"
        ;;
    cli)
        shift
        exec /opt/sage/bin/python -m ibme.cli "$@"
        ;;
    python)
        shift
        exec /opt/sage/bin/python "$@"
        ;;
    *) exec "$@" ;;
esac
