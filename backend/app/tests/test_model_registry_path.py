"""
Regression tests for the ModelRegistry registry-path resolution.

Covers the CI failure where ModelRegistry() unconditionally resolved to the
hard-coded "/app/ml_models" (only writable inside the Docker image) and
crashed with PermissionError on any other host, including GitHub Actions
runners. See app.core.config.Settings.MODEL_REGISTRY_PATH / BASE_DIR.
"""

import os

import pytest

from app.core.config import BASE_DIR, Settings
from app.ml.inference import ModelRegistry


def test_model_registry_path_default_is_not_hardcoded_app_root():
    """The default must be derived from the actual project location, not a
    literal "/app" that only exists inside the Docker image."""
    default_path = Settings.model_fields["MODEL_REGISTRY_PATH"].default
    assert default_path == str(BASE_DIR / "ml_models")
    # Would only equal the old hard-coded literal if this checkout happens to
    # live at /app (true inside Docker, never true on a CI runner or a
    # Windows/macOS/Linux dev machine).
    if str(BASE_DIR) != "/app":
        assert default_path != "/app/ml_models"


def test_model_registry_path_default_is_writable(tmp_path, monkeypatch):
    """Constructing a fresh Settings() with no env override must not point
    somewhere the current process can't create directories in — this is
    the exact condition that raised PermissionError in CI."""
    monkeypatch.delenv("MODEL_REGISTRY_PATH", raising=False)
    default_settings = Settings()

    # Directory may not exist yet on a clean checkout; what matters is that
    # *creating* it doesn't raise, same call ModelRegistry.__init__ makes.
    os.makedirs(default_settings.MODEL_REGISTRY_PATH, exist_ok=True)
    assert os.path.isdir(default_settings.MODEL_REGISTRY_PATH)
    assert os.access(default_settings.MODEL_REGISTRY_PATH, os.W_OK)


def test_model_registry_path_is_configurable_via_env_var(tmp_path, monkeypatch):
    custom_path = str(tmp_path / "custom_registry")
    monkeypatch.setenv("MODEL_REGISTRY_PATH", custom_path)

    configured = Settings()

    assert configured.MODEL_REGISTRY_PATH == custom_path


def test_model_registry_construction_never_raises_permission_error(
    tmp_path, monkeypatch
):
    """Direct regression test for the reported CI failure: constructing
    ModelRegistry() must not raise PermissionError when the configured path
    is a writable directory rather than a hard-coded /app."""
    import app.ml.inference as inference_module

    writable_path = str(tmp_path / "registry")
    monkeypatch.setattr(inference_module.settings, "MODEL_REGISTRY_PATH", writable_path)

    registry = inference_module.ModelRegistry()

    assert os.path.isdir(writable_path)
    assert registry._active_version == "none"


def test_model_registry_still_discovers_existing_committed_model():
    """The real backend/ml_models/xgb_forecast_*.joblib artifact must still
    be found under the new default path (project-relative, same directory
    the artifact is actually committed in)."""
    registry = ModelRegistry()
    loaded = registry.load_latest()

    ml_models_dir = BASE_DIR / "ml_models"
    has_committed_model = any(ml_models_dir.glob("xgb_forecast_*.joblib"))

    if has_committed_model:
        assert loaded is True
        assert registry._active_version.startswith("xgb-")
    else:
        # Nothing committed in this checkout — falling back cleanly (no
        # crash) is the correct, already-tested behavior.
        assert loaded is False


@pytest.mark.parametrize("platform_style_path", ["relative_dir", "./relative_dir"])
def test_model_registry_path_works_with_relative_style_paths(
    tmp_path, monkeypatch, platform_style_path
):
    """Sanity check that a relative-style override (as a user might set
    locally on Windows or Linux) doesn't break directory creation."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MODEL_REGISTRY_PATH", platform_style_path)

    configured = Settings()
    os.makedirs(configured.MODEL_REGISTRY_PATH, exist_ok=True)

    assert os.path.isdir(configured.MODEL_REGISTRY_PATH)
