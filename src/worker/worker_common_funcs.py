from typing import List
from pydantic import BaseModel


def list_model_to_list_dict(lst: List[BaseModel]) -> List[dict]:
    return [item.dict() for item in lst]
