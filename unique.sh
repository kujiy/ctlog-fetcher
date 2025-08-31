#!/bin/bash
. venv/bin/activate

while true; do
  python -m src.manager_api.background_jobs.unique_certs_updater
  sleep 1
done

