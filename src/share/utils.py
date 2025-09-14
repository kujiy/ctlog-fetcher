# python
import hashlib
import random

def probabilistic_round_to_int(value) -> int:
    """
    Probabilistically rounds a float to the nearest integer.
    E.g., 2.5 -> returns 2 or 3, with probability 0.5 for each.
    """
    integer_part = int(value)
    fractional_part = value - integer_part
    if random.random() < fractional_part:
        return integer_part + 1
    else:
        return integer_part

# worker.py and manager_api/routers/worker_pings.py
def convert_ip_address_hash(ip):
    return hashlib.sha256(ip.encode()).hexdigest()[:7]  # f0f1bcd

