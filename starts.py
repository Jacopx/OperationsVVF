from dataclasses import dataclass
from typing import Optional


@dataclass
class Start:
    id: int
    op_id: int
    vehicle: str
    exit: Optional[str]
    inplace: Optional[str]
    back: Optional[str]
    nom: str