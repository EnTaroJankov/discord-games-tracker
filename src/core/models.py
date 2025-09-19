from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Union


@dataclass
class Result:
    number: int
    score: Union[int, str]
    timestamp: datetime
    meta: Dict[str, Any]
