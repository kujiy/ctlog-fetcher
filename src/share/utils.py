# python
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
