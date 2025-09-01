import os
import time
import logging
import sys

import pymysql
import json
from datetime import datetime
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.share.cert_parser import JPCertificateParser

# Load environment variables from .env if present
load_dotenv()

DB_HOST = os.getenv("MYSQL_HOST", "localhost")
DB_PORT = int(os.getenv("MYSQL_PORT", "3306"))
DB_USER = os.getenv("MYSQL_USER", "root")
DB_PASS = os.getenv("MYSQL_PASSWORD", "")
DB_NAME = os.getenv("MYSQL_DATABASE", "ct")

BATCH_SIZE = 10
TOTAL_ROWS = 2720000
SECONDS_IN_WEEK = 7 * 24 * 60 * 60
SLEEP_PER_BATCH = SECONDS_IN_WEEK / (TOTAL_ROWS / BATCH_SIZE)  # ~19 seconds

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

def get_db_connection():
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True
    )

def main():
    parser = JPCertificateParser()
    processed = 0

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT MIN(id) AS min_id, MAX(id) AS max_id FROM Certs")
            ids = cur.fetchone()
            min_id = ids["min_id"] or 1
            max_id = ids["max_id"] or 1

    current_id = min_id
    while current_id <= max_id:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, ct_entry FROM Certs WHERE id BETWEEN %s AND %s AND ct_log_timestamp IS NULL",
                    (current_id, current_id + BATCH_SIZE - 1)
                )
                rows = cur.fetchall()

                if not rows:
                    current_id += BATCH_SIZE
                    continue

                for row in rows:
                    cert_id = row["id"]
                    ct_entry = row["ct_entry"]
                    try:
                        ct_entry_obj = json.loads(ct_entry)
                        cert_data = parser.parse_ct_entry_to_certificate_data(ct_entry_obj)
                        if cert_data and cert_data.get("ct_log_timestamp"):
                            ct_log_timestamp = cert_data["ct_log_timestamp"]
                            issued_at_night = cert_data.get("issued_at_night", False)
                            # Convert to UTC datetime string for MySQL
                            if isinstance(ct_log_timestamp, datetime):
                                ct_log_timestamp_str = ct_log_timestamp.strftime("%Y-%m-%d %H:%M:%S")
                            else:
                                ct_log_timestamp_str = None
                            cur.execute(
                                "UPDATE Certs SET ct_log_timestamp=%s, issued_at_night=%s WHERE id=%s",
                                (ct_log_timestamp_str, int(issued_at_night), cert_id)
                            )
                            logging.info(f"Updated Cert id={cert_id} ct_log_timestamp={ct_log_timestamp_str} issued_at_night={issued_at_night}")
                        else:
                            logging.warning(f"Could not parse ct_log_timestamp for Cert id={cert_id}")
                    except Exception as e:
                        logging.error(f"Error processing Cert id={cert_id}: {e}")

                processed += len(rows)
                logging.info(f"Processed {processed} rows so far. Sleeping {SLEEP_PER_BATCH:.1f} seconds.")
                time.sleep(SLEEP_PER_BATCH)
        current_id += BATCH_SIZE

if __name__ == "__main__":
    main()
