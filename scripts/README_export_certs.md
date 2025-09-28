# Certificate Export Script

## Overview
`export_certs_to_pending.py` is a Python script that exports MySQL "certs" table data in batches of 32 records and saves them as JSON files in the "pending/upload_failure/" directory. After successful save, the processed records are deleted from the database.

## Features
- Exports certificates in batches of 32 records
- Saves data in JSON format matching the expected structure
- Automatically deletes processed records from the database
- Sleeps for 2 seconds between each batch iteration
- Handles errors gracefully with rollback functionality
- Creates timestamped filenames with random suffixes

## Usage

### Prerequisites
1. Ensure MySQL database is accessible
2. Configure database connection in `src/config_secret.py` (copy from `src/config_secret.py.example`)
3. Install required Python dependencies

### Running the Script
```bash
# From the project root directory
python3 scripts/export_certs_to_pending.py
```

Or make it executable and run directly:
```bash
chmod +x scripts/export_certs_to_pending.py
./scripts/export_certs_to_pending.py
```

### Output
- JSON files are saved to `pending/upload_failure/` directory
- Filename format: `upload_failure_YYYYMMDD_HHMMSS_XXXX.json`
- Each file contains an array of certificate objects with the following structure:

```json
[
  {
    "ct_entry": "...",
    "ct_log_url": "https://...",
    "log_name": "...",
    "worker_name": "...",
    "ct_index": 123456,
    "ip_address": null
  }
]
```

### Script Behavior
1. Fetches the oldest 32 records from the `certs` table (ordered by ID)
2. Converts the data to the expected JSON format
3. Saves the batch to a timestamped JSON file
4. Deletes the processed records from the database
5. Sleeps for 2 seconds
6. Repeats until no more records are found

### Error Handling
- If file saving fails, records are not deleted from the database
- If database deletion fails, the transaction is rolled back
- The script continues processing even if individual batches fail
- Use Ctrl+C to interrupt the script gracefully

### Configuration
You can modify the following constants in the script:
- `BATCH_SIZE`: Number of records per batch (default: 32)
- `SLEEP_INTERVAL`: Sleep time between batches in seconds (default: 2)
- `OUTPUT_DIR`: Output directory path (default: "pending/upload_failure")

## Database Requirements
The script uses the `Cert` model from `src/manager_api/models.py` which maps to the `certs` table. The required fields for export are:
- `id` (primary key)
- `ct_entry` (TEXT) - Entire CT log entry as JSON string
- `ct_log_url` (VARCHAR) - CT log URL
- `log_name` (VARCHAR) - Log name identifier
- `worker_name` (VARCHAR) - Worker that processed the certificate
- `ct_index` (BIGINT) - Index within the CT log
- `ip_address` (VARCHAR, nullable) - IP address information

## Safety Features
- Uses SQLAlchemy ORM with the Cert model for type safety
- Uses database transactions to ensure data consistency
- Only deletes records after successful file save
- Provides detailed logging of operations
- Handles database connection issues gracefully
- Leverages existing database connection configuration
