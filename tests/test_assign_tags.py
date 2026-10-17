import sys
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from assign_tags_to_manifest import (
    COLOR_SHORTCUTS,
    discover_boolean_attributes,
    parse_cli_mapping,
    process_manifest_tags,
    save_mapping_to_file,
)
import yaml


def test_discover_boolean_attributes():
    manifest_docs = [
        {"doc_id": "doc1", "scan_has_dots": True, "page_number": 1, "languages": ["English"]},
        {"doc_id": "doc2", "scan_has_tilt": False, "has_tables": True},
    ]
    bools = discover_boolean_attributes(manifest_docs)
    assert bools == {"scan_has_dots", "scan_has_tilt", "has_tables"}


def test_parse_cli_mapping_numbers_and_names(tmp_path):
    valid_attrs = {"scan_has_dots", "scan_has_tilt", "has_tables"}

    # Numeric shortcut keys
    mapping = parse_cli_mapping("1=scan_has_dots,2=scan_has_tilt", None, valid_attrs)
    assert mapping == {"Red": "scan_has_dots", "Orange": "scan_has_tilt"}

    # Color name keys
    mapping2 = parse_cli_mapping("Red=scan_has_dots,Orange=scan_has_tilt", None, valid_attrs)
    assert mapping2 == {"Red": "scan_has_dots", "Orange": "scan_has_tilt"}

    # Mapping file
    map_file = tmp_path / "map.yaml"
    map_file.write_text("3: has_tables\n")
    mapping3 = parse_cli_mapping(None, map_file, valid_attrs)
    assert mapping3 == {"Yellow": "has_tables"}


def test_closed_world_process_manifest_tags(tmp_path, monkeypatch):
    manifest_path = tmp_path / "documents.yaml"
    manifest_docs = [
        {"doc_id": "doc1", "scan_has_dots": False, "scan_has_tilt": True},
        {"doc_id": "doc2", "scan_has_dots": True, "scan_has_tilt": True},
        {"doc_id": "doc3", "scan_has_dots": True, "scan_has_tilt": False},
    ]
    manifest_path.write_text(yaml.safe_dump(manifest_docs))

    # Mock scan_image_directory
    def mock_scan(image_dir):
        # doc1 has Red, doc2 has Orange, doc3 has no tags
        doc_tags = {
            "doc1": {"Red"},
            "doc2": {"Orange"},
            "doc3": set(),
        }
        tag_counts = {"Red": 1, "Orange": 1}
        unknown_tags = []
        return doc_tags, tag_counts, unknown_tags

    import assign_tags_to_manifest

    monkeypatch.setattr(assign_tags_to_manifest, "scan_image_directory", mock_scan)

    mapping = {
        "Red": "scan_has_dots",
        "Orange": "scan_has_tilt",
    }

    updated_docs, report = process_manifest_tags(manifest_path, tmp_path, mapping)

    # doc1: Red present -> scan_has_dots = True. Orange absent -> scan_has_tilt = False
    doc1 = next(d for d in updated_docs if d["doc_id"] == "doc1")
    assert doc1["scan_has_dots"] is True
    assert doc1["scan_has_tilt"] is False

    # doc2: Red absent -> scan_has_dots = False. Orange present -> scan_has_tilt = True
    doc2 = next(d for d in updated_docs if d["doc_id"] == "doc2")
    assert doc2["scan_has_dots"] is False
    assert doc2["scan_has_tilt"] is True

    # doc3: both absent -> both False
    doc3 = next(d for d in updated_docs if d["doc_id"] == "doc3")
    assert doc3["scan_has_dots"] is False
    assert doc3["scan_has_tilt"] is False

    assert report["field_counts_after"]["scan_has_dots"] == 1
    assert report["field_counts_after"]["scan_has_tilt"] == 1
