# CT Log Collection Manager API (manager_api) Setup Guide

This directory provides the management API (FastAPI) for CT log collection.

---

## Requirements
- Python 3.9 or later
- MySQL server (database name: ct)
- Dependency packages in `requirements.txt`

---

## Example MySQL Setup

1. Start MySQL
2. Create database

```
CREATE DATABASE ct DEFAULT CHARACTER SET utf8mb4;
```

3. Create user (example: root, no password)

---

## Start API Server with Python

1. Install dependencies

```
pip install -r requirements.txt
```

2. Initialize DB (only the first time)

```
python -c "from src.manager_api import models; models.Base.metadata.create_all(models.engine)"
```

3. Start API server

```
uvicorn src.manager_api.main:app --host 0.0.0.0 --port 1173
```

---

## Notes
- API/DB connection info is set in `MYSQL_URL` in `src/manager_api/main.py`
- If the DB schema changes, run `create_all` again

---

If you have any issues, please contact the developer.
