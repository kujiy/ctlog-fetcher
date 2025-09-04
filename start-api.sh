
. venv/bin/activate

#uvicorn src.manager_api.main:app --port 1173 --host 0.0.0.0 --workers 12
mkdir -p /tmp/metrics;rm -rf /tmp/metrics/*;  nohup env PROMETHEUS_MULTIPROC_DIR=/tmp/metrics uvicorn src.manager_api.main:app --port 1173 --host 0.0.0.0 --workers 3 &
