# CT Log Fetcher Worker

This Python worker is a tool for distributed collection of Japan-related certificates from Certificate Transparency (CT) logs and uploading them to the Manager API.

---

## Requirements

- Python 3.11 or higher
- `requests`, `python-dotenv`, etc. (see `requirements.txt`)

---

## Installation

```bash
pip install -r requirements.txt
```

---

## How to Run

### 1. Command Line Execution

```bash
python src/worker/worker.py [--proxies http://proxy1,http://proxy2] [--worker-name NAME] [--manager http://manager-url] [--debug]
```

### 2. Environment Variable Configuration

All options can also be specified via environment variables (CLI arguments take precedence).

| Environment Variable | Description                              | Example                            |
|:-------------------- |:-----------------------------------------|:-----------------------------------|
| PROXIES              | Proxy URLs (comma-separated, multiple)    | `http://proxy1,http://proxy2`      |
| WORKER_NAME          | Worker name                               | `my-worker`                        |
| MANAGER_URL          | Manager API base URL                      | `http://localhost:8000`            |
| DEBUG                | Enable debug logging (1/true/yes)         | `1`                                |

Example:
```bash
export PROXIES="http://proxy1,http://proxy2"
export WORKER_NAME="my-worker"
export MANAGER_URL="http://localhost:8000"
export DEBUG=1
python src/worker/worker.py
```

---

## Options

- `--proxies`: Proxy URLs (comma-separated, multiple allowed)
- `--worker-name`: Worker name (auto-generated if omitted)
- `--manager`: Manager API base URL
- `--debug`: Enable debug logging

---

## Main Features

- Fetch jobs from Manager API and batch fetch certificates from CT logs
- Extract and upload only Japan-related certificates
- Report progress, completion, and errors via API
- Failed requests are saved in the `pending/` directory and retried automatically
- Safe shutdown with Ctrl+C, sending resume requests for unfinished jobs
- Supports .env file

---

## Architecture Overview

- Multi-threaded (ThreadPoolExecutor) for parallel processing of multiple job categories
- Real-time progress display in the console
- Automated certificate parsing, uploading, and error handling

---

## Troubleshooting

- Failed uploads are saved as JSON in the `pending/` directory and retried automatically
- Error details are sent to logs or Manager API endpoints
- Check disk space, network connectivity, and Manager API availability

---

## Development & Testing

- See the `tests/` directory for tests
- Main logic is in `src/worker/worker.py`

---

## License

MIT License
