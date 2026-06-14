from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectAction:
    name: str
    description: str
    path: Path
    command: tuple[str, ...]
    window_title: str
