import sys
import os
import asyncio

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.manager_api.db import get_async_session
from src.manager_api.models import CTLogSTH, WorkerStatus
from sqlalchemy import desc, func
from src.manager_api.main import BATCH_SIZE


async def main():
    async for session in get_async_session():
        # Get all unique ct_log_url from CTLogSTH
        ct_logs = await session.execute(
            CTLogSTH.__table__.select().with_only_columns([CTLogSTH.ct_log_url]).distinct()
        )
        ct_logs = [row[0] for row in ct_logs.fetchall()]

        for ct_log_url in ct_logs:
            # Get latest tree_size for this ct_log_url
            latest_sth_result = await session.execute(
                CTLogSTH.__table__.select()
                .where(CTLogSTH.ct_log_url == ct_log_url)
                .order_by(desc(CTLogSTH.fetched_at))
                .limit(1)
            )
            latest_sth = latest_sth_result.fetchone()
            if not latest_sth:
                print(f"[{ct_log_url}] No STH found.")
                continue
            tree_size = latest_sth.tree_size

            # reuse the logic from /next_task

            # get log_name
            log_name_result = await session.execute(
                WorkerStatus.__table__.select()
                .with_only_columns([WorkerStatus.log_name])
                .where(WorkerStatus.ct_log_url == ct_log_url)
                .limit(1)
            )
            log_name_row = log_name_result.fetchone()
            log_name = log_name_row[0] if log_name_row else None

            if not log_name:
                print(f"[{ct_log_url}] No log_name found.")
                continue

            # get end_list and sort ascending
            end_results = await session.execute(
                WorkerStatus.__table__.select()
                .with_only_columns([WorkerStatus.end])
                .where(WorkerStatus.log_name == log_name)
                .distinct()
                .order_by(WorkerStatus.end.asc())
            )
            end_list = [row[0] for row in end_results.fetchall() if row[0] is not None]

            # search for the largest contiguous end
            i = BATCH_SIZE - 1
            max_end = tree_size - 1
            last_contiguous_end = -1

            while i <= max_end:
                if i in end_list:
                    last_contiguous_end = i
                    i += BATCH_SIZE
                else:
                    break

            # how much has been collected: the next start to be assigned
            next_start = last_contiguous_end + 1

            # criteria for completion: next_start > tree_size
            is_complete = next_start > tree_size

            print(f"CT Log Endpoint: {ct_log_url}")
            print(f"  Latest tree_size: {tree_size}")
            print(f"  Next start (collected): {next_start}")
            print(f"  Next start > tree_size?: {is_complete}")
            print(f"  Collection complete?: {'YES' if is_complete else 'NO'}")
            print("")

if __name__ == "__main__":
    asyncio.run(main())
