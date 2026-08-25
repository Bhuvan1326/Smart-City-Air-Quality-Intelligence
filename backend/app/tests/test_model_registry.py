"""Unit tests for ModelRegistry's path handling.

No DB dependency — these test filesystem/config behavior only. Uses
tmp_path (pytest's built-in temp-directory fixture) so nothing here ever
touches the real backend/ml_models/ directory or its committed model
artifact.
"""

from pathlib import Path

from app.core.config import _DEFAULT_MODEL_REGISTRY_PATH
from app.ml.inference import ModelRegistry


def test_default_registry_path_is_not_root_app():
    """Regression test for the CI failure: the default must never be a
    hardcoded, non-portable path like "/app/ml_models" that only exists
    inside a specific Docker container."""
    assert _DEFAULT_MODEL_REGISTRY_PATH != "/app/ml_models"
    assert not _DEFAULT_MODEL_REGISTRY_PATH.startswith("/app")


def test_default_registry_path_resolves_to_project_ml_models_dir():
    # backend/app/core/config.py -> parents[2] is backend/
    expected = Path(__file__).resolve().parents[2] / "ml_models"
    assert Path(_DEFAULT_MODEL_REGISTRY_PATH) == expected


def test_registry_accepts_injected_temp_directory(tmp_path):
    """Tests must be able to use a temp writable directory instead of the
    real registry — this is what makes the registry safe to instantiate
    in CI without touching backend/ml_models/."""
    custom_path = tmp_path / "custom_model_registry"
    registry = ModelRegistry(registry_path=str(custom_path))
    assert custom_path.exists()
    assert registry._registry_path == str(custom_path)


def test_registry_with_empty_temp_dir_has_no_model_to_load(tmp_path):
    registry = ModelRegistry(registry_path=str(tmp_path / "empty_registry"))
    loaded = registry.load_latest()
    assert loaded is False


def test_registry_never_needs_root_permissions(tmp_path):
    """Constructing a registry anywhere under a normal writable temp
    directory must never raise PermissionError — this is the exact
    failure mode being regression-tested (PermissionError on '/app')."""
    try:
        ModelRegistry(registry_path=str(tmp_path / "nested" / "registry"))
    except PermissionError:
        raise AssertionError(
            "ModelRegistry raised PermissionError on a normal writable temp path"
        )


def test_base_dir_is_importable_and_is_the_project_root():
    """Regression test for `from app.core.config import BASE_DIR, Settings`
    — a real ImportError observed on a Windows/Python 3.12.10 run. BASE_DIR
    must exist, be a directory, and match the value the model-registry
    default is actually built from (no drift between the two)."""
    from app.core.config import _DEFAULT_MODEL_REGISTRY_PATH, BASE_DIR

    assert BASE_DIR.is_dir()
    assert str(BASE_DIR / "ml_models") == _DEFAULT_MODEL_REGISTRY_PATH
