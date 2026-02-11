from __future__ import annotations
import json, os
from typing import Any, Dict, List, Union
from pydantic import BaseModel, Field, field_validator

class UserProfile(BaseModel):
    id: str | None = None
    goal: str = "hypertrophy"
    days_per_week: int = 3
    session_minutes: int = 60
    level: str = "intermediate"
    equipment_available: List[str] = Field(default_factory=list)
    injuries_limitations: List[str] = Field(default_factory=list)
    avoid: List[str] = Field(default_factory=list)
    preferences: List[str] = Field(default_factory=list)

class Exercise(BaseModel):
    id: str
    name: str
    muscles_primary: List[str] = Field(default_factory=list)
    muscles_secondary: List[str] = Field(default_factory=list)
    movement: str = ""
    equipment: List[str] = Field(default_factory=list)

    # Accept both numeric and string difficulty (dataset uses ints).
    # Mapping: 1->beginner, 2->intermediate, 3->advanced
    difficulty: Union[str, int] = "intermediate"

    contraindications: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    alternatives: List[str] = Field(default_factory=list)

    @field_validator("difficulty", mode="before")
    @classmethod
    def _coerce_difficulty(cls, v: Any) -> str:
        if v is None:
            return "intermediate"
        if isinstance(v, int):
            mapping = {1: "beginner", 2: "intermediate", 3: "advanced"}
            return mapping.get(v, "intermediate")
        # allow strings like "1"/"2"/"3"
        if isinstance(v, str):
            s = v.strip().lower()
            if s.isdigit():
                mapping = {"1": "beginner", "2": "intermediate", "3": "advanced"}
                return mapping.get(s, "intermediate")
            if s in ("beginner", "intermediate", "advanced"):
                return s
            # fallback
            return "intermediate"
        return "intermediate"

class ExerciseCatalog(BaseModel):
    exercises: List[Exercise] = Field(default_factory=list)

def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_profile(path: str) -> UserProfile:
    return UserProfile.model_validate(load_json(path))

def load_catalog(path: str) -> ExerciseCatalog:
    return ExerciseCatalog.model_validate(load_json(path))

def default_profile_path() -> str:
    return os.getenv("PROFILE_JSON", "data/input/profile.json")

def default_catalog_path() -> str:
    return os.getenv("CATALOG_JSON", "data/input/exercise_catalog.json")
