. venv/bin/activate
uvicorn src.manager_api.main:app --reload --port 1173 --host 0.0.0.0 --workers 8
uvicorn src.ui.main:app --reload --port 1174 --host 0.0.0.0 --workers 4
# ---
gunicorn src.manager_api.main:app \
    -k uvicorn.workers.UvicornWorker \
    --access-logfile gunicorn_access_api.log \
    --error-logfile gunicorn_error_api.log \
    --log-level info \
    -w 8 \
    -b 0.0.0.0:1173

gunicorn src.ui.main:app \
    -k uvicorn.workers.UvicornWorker \
    --access-logfile gunicorn_access_ui.log \
    --error-logfile gunicorn_error_ui.log \
    --log-level info \
    -w 4 \
    -b 0.0.0.0:1174
