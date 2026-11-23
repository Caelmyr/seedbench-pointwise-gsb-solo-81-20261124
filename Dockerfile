ARG SEEDBENCH_RUNTIME_IMAGE=python:3.12-slim
FROM ${SEEDBENCH_RUNTIME_IMAGE}
USER root
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 HOST=0.0.0.0 PORT=8000 SEEDBENCH_DATA=/var/lib/seedbench
WORKDIR /opt/seedbench
COPY requirements.txt scripts/check_dependencies.py ./
RUN (python check_dependencies.py || python -m pip install --disable-pip-version-check --no-cache-dir --only-binary=:all: -r requirements.txt) \
    && python check_dependencies.py && python -m pip check
COPY seedbench ./seedbench
COPY image_lab ./image_lab
COPY static ./static
COPY templates ./templates
RUN useradd -U -u 11538 seedbench && install -d -o seedbench -g seedbench /var/lib/seedbench
USER seedbench
EXPOSE 8000
CMD ["python", "-m", "seedbench"]
