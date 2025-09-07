# How to use
# PYTHONPATH=. python src/manager_api/debug.py
import uvicorn
import os

if __name__ == "__main__":
    debug = "debug" if os.environ.get("DEBUG") else None
    uvicorn.run("src.manager_api.main:app", host="0.0.0.0", port=1173, reload=True, log_level=debug)
