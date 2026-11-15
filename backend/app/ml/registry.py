"""Persist fitted models with their metadata.

v0 writes to local disk (``ML_ARTIFACT_DIR``); switch to Supabase Storage when
the API runs on more than one instance.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import joblib


def save_model(model, name: str, metadata: dict | None = None, artifact_dir: str = "./artifacts") -> Path:
    directory = Path(artifact_dir)
    directory.mkdir(parents=True, exist_ok=True)

    path = directory / f"{name}.joblib"
    joblib.dump(model, path)
    (directory / f"{name}.json").write_text(
        json.dumps(
            {
                "name": name,
                "saved_at": int(time.time()),
                "metadata": metadata or {},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def load_model(name: str, artifact_dir: str = "./artifacts"):
    return joblib.load(Path(artifact_dir) / f"{name}.joblib")
