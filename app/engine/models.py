from dataclasses import dataclass
from typing import List,Optional


@dataclass
class ReviewFindings:
  severity: str
  category: str
  message: str
  file_name: Optional[str] = None

