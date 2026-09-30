from pydantic import BaseModel
from typing import Dict, List

from shared.models import Difficulty

class ProblemResponse(BaseModel):
    id: str
    title: str
    difficulty: Difficulty
    tags: List[str]
    accepted_submissions: int = 0
    total_submissions: int = 0

    model_config = {
      "from_attributes": True
    }

class ProblemListResponse(BaseModel):
    items: List[ProblemResponse]
    total: int
    page: int
    limit: int
    has_more: bool

class ProblemDetailResponse(ProblemResponse):
    description: str
    constraints: List[str]
    input_desc: str
    output_desc: str
    sample_io: Dict[str, str]
    explanation: str | None = None

    memory_limit_mb: int
    time_limit_sec: int

    source: str | None = None
    editorial: str | None = None
    visibility: bool

class ProblemArrayDataValidator(BaseModel):
    tags: List[str]
    constraints: List[str]
    sample_io: Dict[str, str]

class ProblemUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    difficulty: Difficulty | None = None
    constraints: List[str] | None = None
    tags: List[str] | None = None
    sample_io: Dict[str, str] | None = None
    input_desc: str | None = None
    output_desc: str | None = None
    explanation: str | None = None
    memory_limit_mb: int | None = None
    time_limit_sec: int | None = None
    visibility: bool | None = None
    source: str | None = None
    editorial: str | None = None

class TagCreate(BaseModel):
    name: str
    slug: str

class ProblemCreateResponse(BaseModel):
    id: str
    title: str
    difficulty: Difficulty
    tags: List[str]
    testcases: int