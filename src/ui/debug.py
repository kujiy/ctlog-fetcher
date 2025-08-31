# How to use
# PYTHONPATH=. python src/ui/debug.py
import uvicorn

if __name__ == "__main__":
    uvicorn.run("src.ui.main:app", host="0.0.0.0", port=1174, reload=True)
