# syntax=docker/dockerfile:1
ARG BASE=mambaorg/micromamba:2.3.3@sha256:800e7ade3ffe29c9a9ac2026163131495f8197c3852e572c5835beb4e8a33cd6
FROM ${BASE} AS environment
USER root
COPY environment-linux-64.lock environment-sources.json collect_licenses.py /tmp/
COPY conda-cache/ /opt/conda/pkgs/
RUN micromamba create -y -p /opt/sage --file /tmp/environment-linux-64.lock && \
    /opt/sage/bin/python /tmp/collect_licenses.py && \
    micromamba clean --all --yes

FROM ${BASE} AS builder
USER root
COPY --from=environment /opt/sage /opt/sage
COPY --from=environment /opt/ibme/licenses /opt/ibme/licenses
ENV PATH=/opt/ibme/toolchain:/opt/sage/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    HOME=/home/mambauser
COPY wheelhouse/ /tmp/wheelhouse/
COPY ibme-0.1.0-py3-none-any.whl python-runtime.lock /tmp/
COPY source-info.json build_native.py check_runtime.py entrypoint.sh /opt/ibme/
COPY environment-linux-64.lock environment-sources.json /opt/ibme/
RUN /opt/sage/bin/python -m pip install --no-cache-dir --no-index --no-deps --require-hashes \
      --find-links=/tmp/wheelhouse -r /tmp/python-runtime.lock && \
    /opt/sage/bin/python -m pip install --no-cache-dir --no-index --no-deps /tmp/ibme-0.1.0-py3-none-any.whl && \
    mkdir -p /home/mambauser/miniconda3/envs /opt/ibme/toolchain && \
    ln -s /opt/sage /home/mambauser/miniconda3/envs/sage && \
    printf '#!/bin/sh\nexec /opt/sage/bin/x86_64-conda-linux-gnu-gcc "$@"\n' > /opt/ibme/toolchain/gcc && \
    printf '#!/bin/sh\nexec /opt/sage/bin/x86_64-conda-linux-gnu-g++ "$@"\n' > /opt/ibme/toolchain/g++ && \
    chmod 755 /opt/ibme/toolchain/* /opt/ibme/entrypoint.sh && \
    /opt/sage/bin/python /opt/ibme/build_native.py

FROM ${BASE} AS runtime
USER root
COPY --from=builder /opt/sage /opt/sage
COPY --from=builder /opt/ibme /opt/ibme
ENV PATH=/opt/sage/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    ENV_NAME=ibme \
    HOME=/home/mambauser \
    PYTHONNOUSERSITE=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    IBME_LATTE3_EXECUTABLE=/opt/ibme/native/latte/bin/ibme-latte3 \
    IBME_CERTIFIED_SIGNATURE_BIN_DIR=/opt/ibme/native/mldsa/bin \
    IBME_CERTIFIED_FALCON_BIN_DIR=/opt/ibme/native/falcon/bin \
    IBME_SAGELOLI_RING_NATIVE=/opt/ibme/native/sageloli/ring.so
RUN mkdir -p /home/mambauser/miniconda3/envs /data && \
    ln -s /opt/sage /home/mambauser/miniconda3/envs/sage && \
    chown -R 57439:57439 /home/mambauser /data
USER 57439:57439
WORKDIR /data
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s \
    CMD ["/opt/sage/bin/python", "/opt/ibme/check_runtime.py", "--health"]
ENTRYPOINT ["/opt/ibme/entrypoint.sh"]
CMD ["web"]
