import importlib.util
import os


def load_module():
    path = os.path.join(
        os.path.dirname(__file__), "..", "scripts", "migrate_sanitize_ids.py"
    )
    path = os.path.normpath(path)
    spec = importlib.util.spec_from_file_location("migrate_sanitize_ids", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_detect_non_ascii_and_conversion():
    mod = load_module()

    rows = [
        {
            "id": "A5087556046_Spin–phonon interactions in sili",
            "researcher_id": "A5087556046",
            "title": "Spin–phonon interactions in silicon",
            "year": 2020,
            "venue": "Phys Rev",
            "abstract": None,
            "embedding_id": "A5087556046_Spin–phonon interactions in sili",
        },
        {
            "id": "A5087556046_Cafe Learning",
            "researcher_id": "A5087556046",
            "title": "Café Learning",
            "year": 2021,
            "venue": "MLConf",
            "abstract": None,
            "embedding_id": "A5087556046_Café Learning",
        },
    ]

    affected = mod.find_unsafe(rows)
    assert len(affected) == 2

    # Check sanitized mapping produces ASCII-safe ids
    for r in affected:
        new_pid, new_eid = mod.compute_sanitized_mapping(r)
        # ASCII only
        assert all(ord(c) < 128 for c in new_pid)
        assert all(ord(c) < 128 for c in new_eid)
        # Only allowed chars
        import re

        assert re.fullmatch(r"[A-Za-z0-9_\-]+", new_pid)
        assert re.fullmatch(r"[A-Za-z0-9_\-]+", new_eid)


def test_no_raw_title_used_as_id():
    mod = load_module()
    row = {
        "id": "Spin–phonon interactions in sili",
        "researcher_id": "A1",
        "title": "Spin–phonon interactions in sili",
        "year": 2020,
        "venue": "Phys",
        "abstract": None,
        "embedding_id": "Spin–phonon interactions in sili",
    }
    new_pid, new_eid = mod.compute_sanitized_mapping(row)
    # Ensure the new id is not the raw title and is ascii-safe
    assert new_pid != row["title"]
    assert all(ord(c) < 128 for c in new_pid)
