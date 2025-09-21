import re
import sys
import time
from src.manager_api.base_models import WorkerNextTask
from src.worker import ordered_categories, MAX_CONSOLE_LINES
from src.worker.worker_base_models import WorkerArgs
from src.worker.worker_common_funcs import sleep_with_stop_check


def get_console_refresh_time(start_time):
    """
    Returns the refresh interval (in seconds) for the console screen based on elapsed time.
    - 0-5 min: 5 sec
    - 5-10 min: 30 sec
    - 10-15 min: 60 sec
    - 15+ min: 120 sec
    """
    elapsed = time.time() - start_time
    if elapsed < 1 * 60:
        return 5
    elif elapsed < 2 * 60:
        return 30
    elif elapsed < 3 * 60:
        return 60
    else:
        return 120


def update_console_screen(args: WorkerArgs, handle_terminate, status_lines):
    # Main loop for top-like progress display
    start_time = time.time()
    try:
        while True:
            sys.stdout.write(f"\033[{len(status_lines) + 1}F")  # Move cursor up to start position

            # --- Always display the worker name here ---
            refresh_time = get_console_refresh_time(start_time)
            sys.stdout.write(f"\r[WorkerName] {args.worker_name} | Refresh: {refresh_time}s\033[K\n")

            # Loop through all keys in status_lines (category-log_name)
            shown = set()
            for key, line in status_lines.items():
                if '-' in key:
                    cat, log_name = key.split('-', 1)
                else:
                    cat, log_name = key, ''
                # 22 chars + []
                if log_name:
                    disp = f"{cat}: {log_name}"
                    cat_disp = f"[{disp:<22}]"
                else:
                    cat_disp = f"[{cat:<22}]"
                # Replace the first category name
                line_disp = re.sub(r"^\[.*?\]", cat_disp, line)
                sys.stdout.write(f"\r{line_disp}\033[K\n")
                shown.add(cat)
            # Fill in categories not displayed with 'waiting...'
            for cat in ordered_categories:
                if cat not in shown:
                    cat_disp = f"[{cat:<22}]"
                    line = f"{cat_disp} waiting..."
                    sys.stdout.write(f"\r{line}\033[K\n")
            sys.stdout.flush()
            sleep_with_stop_check(refresh_time)
    except KeyboardInterrupt:
        handle_terminate(None, None)


def update_console_message(status_lines, category, log_name, req_count, current, worker_jp_count, worker_total_count, end,
                           task: WorkerNextTask, start_time, omikuji, retry_count):
    # Clear status_lines if it gets too large
    if len(status_lines) > MAX_CONSOLE_LINES:
        status_lines.clear()

    retry_str = f" | ⏳Retry: {retry_count}" if retry_count > 0 else ""
    jp_ratio = (worker_jp_count / worker_total_count) if worker_total_count > 0 else 0
    total_count = end - task.start + 1
    done_count = current - task.start
    progress_pct = (done_count / total_count) * 100 if total_count > 0 else 0
    elapsed = time.time() - start_time
    speed = done_count / elapsed if elapsed > 0 else 0
    remain = total_count - done_count
    eta_sec = remain / speed if speed > 0 else 0
    if eta_sec > 0 and eta_sec < 86400:
        eta_h = int(eta_sec // 3600)
        eta_m = int((eta_sec % 3600) // 60)
        eta_str = f"{eta_h}h {eta_m}m"
        if eta_sec < 300:
            face = "🤩"
        elif eta_sec < 600:
            face = "😊"
        else:
            face = "🙂"
    elif eta_sec >= 86400:
        eta_d = int(eta_sec // 86400)
        eta_h = int((eta_sec % 86400) // 3600)
        eta_str = f"{eta_d}d {eta_h}h"
        face = "😥"
    else:
        eta_str = "--"
        face = "😩"
    status_key = f"{category}-{log_name}"
    status_lines[status_key] = (
        f"[{category}] 🌐 Req: {req_count} | 📍 Index: {current} | 🇯🇵 Domain: {worker_jp_count}({jp_ratio*100:.2f}%) | Progress: {progress_pct:.2f}% | ⏱️ ETA: {eta_str} {face} | {omikuji}{retry_str}"
    )
