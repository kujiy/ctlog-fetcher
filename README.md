# CT Log Distributed Collection System - Main README

This repository is a system for distributed collection and visualization of Certificate Transparency logs. **It corrects only the .jp domain certificates.**

- `src/manager_api/` ... Collection management API (FastAPI, MySQL)
- `src/ui/`  ... Collection status visualization UI (FastAPI + Jinja2)
- `src/worker/`      ... Collection script for each worker node
- `src/share/`       ... Shared logic and parsers

## Overview
```mermaid
flowchart LR
    subgraph CTLogs["CT Log APIs (Public Log Servers)"]
        L1["CT Log Server 1"]
        L2["CT Log Server 2"]
        L3["CT Log Server n"]
    end

    W["Worker (Collaborator's PC/Server)"]

    M["Manager API (Researcher's Server)"]
    D["Dashboard / UI"]

    %% Arrow flow
    W -->|Obtain certificates via HTTP request| CTLogs
    W -->|Upload only `.jp` domains| M
    M --> D
```

```mermaid
graph TD
    subgraph Workers
        W1[Worker 1]
        W2[Worker 2]
        W3[Worker 3]
    end

    M[Manager API<br>Async + Caching]
    DB[(MySQL Database)]

    W1 --> M
    W2 --> M
    W3 --> M

    M --> DB
```

```mermaid
flowchart TB
    subgraph Col1["Worker Layer"]
        W["Worker (Certificate Collector)"]
    end

    subgraph Col2["API / Parser Layer"]
        U["Upload API (Input Certificates)"]
        P["Parser"]
    end

    subgraph Col3["DB / Analysis Layer"]
        DB["Database (Certificates + Analysis Info)"]
        AS["Analysis Script"]
        R["Related Certificates / Relationships Analysis"]
    end

    %% Arrow flow
    W -->|Send certificates| U
    U -->|Forward to parser| P
    P -->|Parse & add analysis info| DB
    DB -->|Read for analysis| AS
    AS -->|Link related/updated certificates| R
```

Worker Multi-Thread / Multi-Log Overview
```mermaid
flowchart TB
    M["Manager Server"]

    subgraph WorkerBox["Worker (Main Process)"]
        TM["Thread Manager"]

        subgraph Threads["Worker Threads"]
            T1["Thread 1\n(Google CT Log)"]
            T2["Thread 2\n(DigiCert CT Log)"]
            T3["Thread 3\n(Let's Encrypt CT Log)"]
            T4["Thread n-1\n(...)"]
            T5["Thread n\n(...)"]
        end

        %% Each thread runs Worker State Flow
        T1 -->|Runs| WS1["Worker State Flow"]
        T2 -->|Runs| WS2["Worker State Flow"]
        T3 -->|Runs| WS3["Worker State Flow"]
        T4 -->|Runs| WS4["Worker State Flow"]
        T5 -->|Runs| WS5["Worker State Flow"]

        TM --> Threads
    end

    %% Manager controls thread scaling
    M -->|Increase / Decrease threads| TM

```

Worker State Flow
```mermaid
flowchart TB
    Start["Start / Idle"] 
    Fetch["Fetch task from Manager"]
    Exec["Execute Task"]
    Ping["Send periodic ping"]
    Upload["Upload certificates (threshold reached)"]
    Error["Send error to Manager"]
    Completed["Send completed to Manager"]

    %% Flow arrows
    Start --> Fetch
    Fetch --> Exec
    Exec --> Ping
    Ping --> Exec
    Exec --> Upload
    Upload --> Exec
    Exec --> Completed
    Exec --> Error
    Completed --> Fetch
    Error --> Fetch

```
---

## Setup Steps (General Overview)

1. Start the MySQL server and create the `ct` database
2. **Configure database connection**: Copy `src/config_secret.py.example` to `src/config_secret.py` and configure your MySQL connection URL
3. Start manager_api (API server)
4. Start ui (UI server)
5. Start `worker.py` on each worker node

---

## Reference
- Please refer to each directory's `README.md`
- Docker Compose and command examples are also described in each README

## How to run
### Python
```sh
PYTHONPATH=. python src/manager_api/debug.py
PYTHONPATH=. python src/ui/debug.py
PYTHONPATH=. python src/worker/worker.py
---

Note: Only Python 3.11 works. Some libraries for Python 3.12+ are not supported yet.

```
### Docker Compose
```sh
sudo docker compose up
```

### Docker run
```sh
sudo docker run -d --name ct-log-manager -p 1173:1173 \
    docker.io/kujiy/ct-api
sudo docker run -d --name ct-log-ui -p 1174:1174 \
    --link ct-log-manager:manager-api \
    docker.io/kujiy/ct-ui
sudo docker run -d --name ct-log-worker --restart unless-stopped \
    --link ct-log-manager:manager-api \
    docker.io/kujiy/ct-worker
```

# Worker Users README
Helping with this research is easy.

## If you can use Docker
```shell
$ sudo docker run -d --name ct-log-worker --restart always docker.io/kujiy/ct-worker:20250929-213931
```
If you give the worker a name, your name will be published on the Dashboard.

```shell
MY_NAME=your-public-name
sudo docker run -d --name ct-log-worker --restart always -e WORKER_NAME=$MY_NAME docker.io/kujiy/ct-worker:20250929-213931
```

## If you want to run on Kubernetes (k8s)
If you already have a k8s environment, you can easily run it with a Deployment manifest like below. Please set `WORKER_NAME` to your nickname.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ct-log-worker
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ct-log-worker
  template:
    metadata:
      labels:
        app: ct-log-worker
    spec:
      containers:
      - name: worker
        image: docker.io/kujiy/ct-worker:20250929-213931
        restartPolicy: Always
        env:
        - name: WORKER_NAME
          value: "your-public-name"  # Change this to your nickname        
```

```bash
kubectl apply -f ct-log-worker.yaml
```

## If you can use Python
Please install Python 3.11

For Mac
e.g.
```shell
brew install pyenv
pyenv install 3.11.8
```

If using pyenv
```shell
git clone ...
cd ct
pyenv shell 3.11.8
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Run
```shell
bash start-worker-python.sh
# or
bash start-worker-python.sh <your-public-name>
```
`<your-public-name>`: This is the name displayed on the dashboard. If omitted, it will be auto-generated.

Dashboard
${DASHBOARD_URL} in `src.config.py`

## Support
- Unfortunatelly, we have no support for this library

---

## License
- This system is intended for research and educational use
