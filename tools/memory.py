from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple

@dataclass
class Memory:
    turns: List[Tuple[str, str]] = field(default_factory=list)

    def add(self, user: str, assistant: str) -> None:
        self.turns.append((user, assistant))
        self.turns = self.turns[-8:]

    def as_text(self) -> str:
        if not self.turns:
            return ""
        lines = []
        for u, a in self.turns[-6:]:
            lines.append(f"User: {u}")
            lines.append(f"Assistant: {a}")
        return "\n".join(lines)
