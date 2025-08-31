
. venv/bin/activate
uvicorn src.ui.main:app --reload --port 1174 --host 0.0.0.0 --workers 3

