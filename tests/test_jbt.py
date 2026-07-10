import pytest

from nexus import jbt


def test_roundtrip(tmp_path):
    doc = jbt.new("nexus_device_registry", {"devices": []}, name="Test Registry")
    path = tmp_path / "registry.jbt"
    jbt.save(path, doc)
    loaded = jbt.load(path)
    assert loaded["jbt_type"] == "nexus_device_registry"
    assert loaded["name"] == "Test Registry"
    assert loaded["payload"] == {"devices": []}
    assert "modified_at" not in loaded  # first save is a create


def test_save_over_existing_sets_modified_at(tmp_path):
    path = tmp_path / "x.jbt"
    doc = jbt.new("app_prefs", {"a": 1})
    jbt.save(path, doc)
    jbt.save(path, jbt.load(path))
    assert "modified_at" in jbt.load(path)


def test_load_rejects_non_jbt(tmp_path):
    path = tmp_path / "plain.json"
    path.write_text('{"just": "json"}')
    with pytest.raises(jbt.JBTError, match="missing required"):
        jbt.load(path)
