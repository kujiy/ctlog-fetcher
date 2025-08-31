# How to use
# PYTHONPATH=. python src/manager_api/debug.py
import uvicorn

if __name__ == "__main__":
    uvicorn.run("src.manager_api.main:app", host="0.0.0.0", port=1173, reload=True)
