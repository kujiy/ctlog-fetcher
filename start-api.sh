
. venv/bin/activate
uvicorn src.manager_api.main:app --port 1173 --host 0.0.0.0 --workers 12
