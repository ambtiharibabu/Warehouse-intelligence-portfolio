# prompting/result_types.py
# Shared data structure returned by every prompting strategy.

from dataclasses import dataclass, field
from typing import List

@dataclass
class StrategyResult:
    answer:             str
    chunks:             list          # List[RetrievedChunk]
    strategy:           str
    prompt_tokens:      int = 0
    completion_tokens:  int = 0
    total_tokens:       int = 0
    extra_info:         dict = field(default_factory=dict)