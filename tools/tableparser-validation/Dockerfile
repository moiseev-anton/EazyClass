# Build context contains only requirements.txt and one explicitly selected wheel.
# The optional base override permits using a cached Python 3.12 application image;
# the venv never inherits that image's installed Python packages.
ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}
USER root
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc-dev libpq-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /validation
COPY requirements.txt ./requirements.txt
COPY eazyclass_tableparser-*.whl ./
RUN python -m venv /validation/venv
ENV PATH="/validation/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
RUN set -- ./eazyclass_tableparser-*.whl && test "$#" -eq 1 \
    && python -m pip install --no-cache-dir --report /validation/install-report.json \
    -r requirements.txt "${1}[ml]" \
    && python -m pip check \
    && python -m pip freeze --all > /validation/installed.txt
WORKDIR /workspace
ENTRYPOINT ["/validation/venv/bin/python"]
CMD ["-m", "pip", "check"]
