# CT Log Collection UI (ui) Setup Guide

This directory provides the visualization UI for CT log collection (FastAPI + Jinja2).

---

## Requirements
- Python 3.9 or later
- Dependency packages in `requirements.txt`
- The manager_api server must be running

---

## Start the UI Server with Python

1. Install dependencies

```
pip install -r requirements.txt
```

2. Start the UI server

```
uvicorn src.ui.main:app --host 0.0.0.0 --port 1194
```

- The UI can be accessed at http://localhost:1194/
- It refers to endpoints such as `/api/status` of manager_api

---

## Notes
- The manager_api server must be started first
- If you want to change the port number, edit the `--port` option in the `uvicorn` command

---

If you have any issues, please contact the developer.
