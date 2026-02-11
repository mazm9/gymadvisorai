from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def _read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _try_import_yaml():
    try:
        import yaml  # type: ignore
        return yaml
    except Exception:
        return None

def _try_import_jsonschema():
    try:
        import jsonschema  # type: ignore
        return jsonschema
    except Exception:
        return None

@dataclass
class LoadedData:
    profiles: List[Dict[str, Any]]
    catalog: Optional[Dict[str, Any]]
    query_suite: List[Dict[str, Any]]
    profile_schema: Optional[Dict[str, Any]]
    warnings: List[str]

def load_project_data(root_dir: str = ".") -> LoadedData:
    warnings: List[str] = []
    data_dir = os.path.join(root_dir, "data")
    input_dir = os.path.join(data_dir, "input")
    queries_dir = os.path.join(root_dir, "queries")
    schemas_dir = os.path.join(root_dir, "schemas")

    profiles: List[Dict[str, Any]] = []
    p_profiles = os.path.join(input_dir, "profiles.json")
    p_profile_json = os.path.join(input_dir, "profile.json")
    p_profile_yaml = os.path.join(input_dir, "profile.yaml")

    if os.path.exists(p_profiles):
        raw = _read_json(p_profiles)
        if isinstance(raw, list):
            profiles = raw
        else:
            warnings.append("data/input/profiles.json exists but is not a JSON list; ignoring.")
    elif os.path.exists(p_profile_json):
        raw = _read_json(p_profile_json)
        if isinstance(raw, dict):
            profiles = [raw]
        else:
            warnings.append("data/input/profile.json exists but is not a JSON object; ignoring.")
    elif os.path.exists(p_profile_yaml):
        yaml = _try_import_yaml()
        if yaml is None:
            warnings.append("Found data/input/profile.yaml but PyYAML is not installed (pip install pyyaml).")
        else:
            raw = yaml.safe_load(_read_text(p_profile_yaml))
            if isinstance(raw, dict):
                profiles = [raw]
            else:
                warnings.append("data/input/profile.yaml exists but is not a mapping; ignoring.")
    else:
        warnings.append("No profile found (expected data/input/profiles.json or profile.json or profile.yaml).")

    catalog: Optional[Dict[str, Any]] = None
    p_catalog = os.path.join(input_dir, "exercise_catalog.json")
    if os.path.exists(p_catalog):
        raw = _read_json(p_catalog)
        if isinstance(raw, dict):
            catalog = raw
        else:
            warnings.append("data/input/exercise_catalog.json exists but is not a JSON object; ignoring.")
    else:
        warnings.append("No exercise catalog found (expected data/input/exercise_catalog.json).")

    query_suite: List[Dict[str, Any]] = []
    p_qs = os.path.join(queries_dir, "query_suite.json")
    if os.path.exists(p_qs):
        raw = _read_json(p_qs)
        if isinstance(raw, list):
            query_suite = raw
        else:
            warnings.append("queries/query_suite.json exists but is not a JSON list; ignoring.")

    profile_schema: Optional[Dict[str, Any]] = None
    p_schema = os.path.join(schemas_dir, "profile.schema.json")
    if os.path.exists(p_schema):
        raw = _read_json(p_schema)
        if isinstance(raw, dict):
            profile_schema = raw
        else:
            warnings.append("schemas/profile.schema.json exists but is not a JSON object; ignoring.")

    # optional validation
    if profiles and profile_schema:
        jsonschema = _try_import_jsonschema()
        if jsonschema is None:
            warnings.append("schemas/profile.schema.json found but jsonschema is not installed (pip install jsonschema).")
        else:
            for i, prof in enumerate(profiles):
                try:
                    jsonschema.validate(instance=prof, schema=profile_schema)
                except Exception as e:
                    warnings.append(f"Profile[{i}] does not match schema: {e}")

    return LoadedData(
        profiles=profiles,
        catalog=catalog,
        query_suite=query_suite,
        profile_schema=profile_schema,
        warnings=warnings,
    )
