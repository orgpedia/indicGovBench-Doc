#!/usr/bin/env python3
"""
assign_tags_to_manifest.py — Assign Apple Finder tag annotations from an image directory
to documents.yaml with interactive/CLI attribute mapping, validation, error checking,
and dry-run mode.

macOS Finder Tag Shortcuts:
  1 -> Red
  2 -> Orange
  3 -> Yellow
  4 -> Green
  5 -> Blue
  6 -> Purple
  7 -> Grey / Gray

Usage:
  # Interactive mode with dry-run (safe default)
  python3 scripts/assign_tags_to_manifest.py --image-dir tag_images

  # With CLI mapping (non-interactive)
  python3 scripts/assign_tags_to_manifest.py --image-dir tag_images --map 1=scan_has_dots,2=scan_has_tilt --non-interactive

  # Apply changes to manifest in-place
  python3 scripts/assign_tags_to_manifest.py --image-dir tag_images --map 1=scan_has_dots --apply

  # Save mapping to file for re-use
  python3 scripts/assign_tags_to_manifest.py --image-dir tag_images --save-mapping mapping.yaml
"""

from __future__ import annotations

import argparse
import ctypes
import plistlib
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

# macOS libc xattr setup for fast, zero-dependency extended attribute reading
libc: Any = None
if sys.platform == "darwin":
    try:
        libc = ctypes.cdll.LoadLibrary("/usr/lib/libc.dylib")
        # ssize_t getxattr(const char *path, const char *name, void *value, size_t size, u_int32_t position, int options);
        libc.getxattr.argtypes = [
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.c_uint32,
            ctypes.c_int,
        ]
        libc.getxattr.restype = ctypes.c_ssize_t
    except Exception:
        libc = None

# macOS Finder keyboard shortcut colors (1-7)
COLOR_SHORTCUTS: list[tuple[int, str]] = [
    (1, "Red"),
    (2, "Orange"),
    (3, "Yellow"),
    (4, "Green"),
    (5, "Blue"),
    (6, "Purple"),
    (7, "Grey"),
]

COLOR_NAME_TO_SHORTCUT: dict[str, tuple[int, str]] = {
    "red": (1, "Red"),
    "orange": (2, "Orange"),
    "yellow": (3, "Yellow"),
    "green": (4, "Green"),
    "blue": (5, "Blue"),
    "purple": (6, "Purple"),
    "grey": (7, "Grey"),
    "gray": (7, "Grey"),
}

SHORTCUT_TO_COLOR: dict[int, str] = {
    num: name for num, name in COLOR_SHORTCUTS
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}


def get_apple_tags(file_path: Path) -> list[str]:
    """Extracts macOS Finder user tags from file extended attributes.

    Returns a list of raw tag label strings.
    """
    if sys.platform != "darwin" or not libc:
        return []

    attr = b"com.apple.metadata:_kMDItemUserTags"
    path_bytes = str(file_path.resolve()).encode("utf-8")
    size = libc.getxattr(path_bytes, attr, None, 0, 0, 0)
    if size <= 0:
        return []

    buf = ctypes.create_string_buffer(size)
    bytes_read = libc.getxattr(path_bytes, attr, buf, size, 0, 0)
    if bytes_read <= 0:
        return []

    try:
        data = plistlib.loads(buf.raw[:bytes_read])
        if isinstance(data, list):
            tags: list[str] = []
            for item in data:
                # Raw Finder tag item can be e.g. "Red\n6" or "Red"
                tag_label = str(item).split("\n")[0].strip()
                if tag_label:
                    tags.append(tag_label)
            return tags
    except Exception:
        pass

    return []


def scan_image_directory(
    image_dir: Path,
) -> tuple[dict[str, set[str]], Counter[str], list[str]]:
    """Scans image directory for files and their Apple tags.

    Returns:
      - doc_tags: mapping doc_id -> set of canonical color names
      - tag_counts: Counter mapping canonical color name -> total tagged files
      - unknown_tags: list of tags that do not match the 7 Finder colors
    """
    if not image_dir.exists():
        raise FileNotFoundError(f"Image directory not found: {image_dir}")

    doc_tags: dict[str, set[str]] = {}
    tag_counts: Counter[str] = Counter()
    unknown_tags: list[str] = []

    for file_path in sorted(image_dir.iterdir()):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue

        doc_id = file_path.stem
        raw_tags = get_apple_tags(file_path)

        file_canonical_colors: set[str] = set()
        for raw in raw_tags:
            match = COLOR_NAME_TO_SHORTCUT.get(raw.lower())
            if match:
                canonical_color = match[1]
                file_canonical_colors.add(canonical_color)
            else:
                unknown_tags.append(f"{file_path.name}: {raw}")

        doc_tags[doc_id] = file_canonical_colors
        for c in file_canonical_colors:
            tag_counts[c] += 1

    return doc_tags, tag_counts, unknown_tags


def discover_boolean_attributes(manifest_docs: list[dict[str, Any]]) -> set[str]:
    """Discovers all boolean attribute names from the manifest documents."""
    bool_attrs: set[str] = set()
    for doc in manifest_docs:
        for k, v in doc.items():
            if isinstance(v, bool):
                bool_attrs.add(k)
    return bool_attrs


def parse_cli_mapping(
    cli_map_str: str | None,
    mapping_file: Path | None,
    valid_attributes: set[str],
) -> dict[str, str]:
    """Parses mapping from CLI string or mapping file.

    Returns a dict mapping canonical color name -> valid boolean attribute.
    """
    mapping: dict[str, str] = {}

    if mapping_file and mapping_file.exists():
        with open(mapping_file, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f) or {}
            for k, v in raw_data.items():
                if not v:
                    continue
                # k could be an integer shortcut (1..7) or color name string
                canonical_color: str | None = None
                if isinstance(k, int) and k in SHORTCUT_TO_COLOR:
                    canonical_color = SHORTCUT_TO_COLOR[k]
                elif str(k).strip().lower() in COLOR_NAME_TO_SHORTCUT:
                    canonical_color = COLOR_NAME_TO_SHORTCUT[str(k).strip().lower()][1]

                if not canonical_color:
                    raise ValueError(f"Invalid color/shortcut key '{k}' in mapping file: {mapping_file}")
                attr_name = str(v).strip()
                if attr_name not in valid_attributes:
                    raise ValueError(
                        f"Attribute '{attr_name}' for color '{canonical_color}' is not a valid boolean attribute."
                    )
                mapping[canonical_color] = attr_name

    if cli_map_str:
        pairs = [p.strip() for p in cli_map_str.split(",") if p.strip()]
        for pair in pairs:
            if "=" not in pair:
                raise ValueError(f"Invalid mapping pair '{pair}'. Expected format '1=attribute' or 'Red=attribute'")
            k, v = pair.split("=", 1)
            k, v = k.strip(), v.strip()
            canonical_color = None
            if k.isdigit() and int(k) in SHORTCUT_TO_COLOR:
                canonical_color = SHORTCUT_TO_COLOR[int(k)]
            elif k.lower() in COLOR_NAME_TO_SHORTCUT:
                canonical_color = COLOR_NAME_TO_SHORTCUT[k.lower()][1]

            if not canonical_color:
                raise ValueError(f"Unrecognized color or shortcut key '{k}' in --map argument")
            if v not in valid_attributes:
                raise ValueError(f"Attribute '{v}' is not a valid boolean attribute in documents.yaml")
            mapping[canonical_color] = v

    return mapping


def resolve_interactive_mapping(
    tag_counts: Counter[str],
    preset_mapping: dict[str, str],
    valid_attributes: set[str],
    non_interactive: bool = False,
) -> dict[str, str]:
    """Prompts user for attribute mapping for each color found in the images."""
    final_mapping: dict[str, str] = dict(preset_mapping)

    # Filter and sort colors present in the images by their shortcut number (1..7)
    present_colors = [
        (num, color)
        for num, color in COLOR_SHORTCUTS
        if tag_counts.get(color, 0) > 0
    ]

    unmapped_colors = [
        (num, color)
        for num, color in present_colors
        if color not in final_mapping
    ]

    if not unmapped_colors or non_interactive:
        return final_mapping

    print("\n" + "=" * 75)
    print("🎨 APPLE TAG TO MANIFEST ATTRIBUTE MAPPING")
    print("=" * 75)
    print("Specify which boolean attribute in documents.yaml corresponds to each tag.")
    print("Press [Enter] with empty input to ignore / skip that tag.")
    print("-" * 75)

    for num, color in unmapped_colors:
        count = tag_counts.get(color, 0)
        file_label = "file" if count == 1 else "files"
        prompt_text = f"[{num}] {color} ({count} {file_label}) -> attribute [Enter to skip]: "

        while True:
            try:
                user_val = input(prompt_text).strip()
            except EOFError:
                return final_mapping
            except KeyboardInterrupt:
                print("\n\nOperation cancelled by user.")
                sys.exit(0)

            if not user_val:
                # Ignored / skipped
                break

            if user_val in valid_attributes:
                final_mapping[color] = user_val
                print(f"   ✓ Mapped [{num}] {color} -> {user_val}")
                break
            else:
                print(f"   ❌ '{user_val}' is not a valid boolean attribute in documents.yaml. Try again:")

    return final_mapping


def save_mapping_to_file(mapping: dict[str, str], output_file: Path) -> None:
    """Saves resolved mapping to a YAML file."""
    output_file.parent.mkdir(parents=True, exist_ok=True)
    # Output ordered by shortcut number
    ordered_dict: dict[str, str] = {}
    for num, color in COLOR_SHORTCUTS:
        if color in mapping:
            ordered_dict[color] = mapping[color]

    with open(output_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(ordered_dict, f, sort_keys=False)
    print(f"💾 Saved mapping configuration to: {output_file}")


def process_manifest_tags(
    manifest_path: Path,
    image_dir: Path,
    mapping: dict[str, str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Updates manifest documents using closed-world assumption for mapped tags."""
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest_docs: list[dict[str, Any]] = yaml.safe_load(f)

    doc_tags, tag_counts, unknown_tags = scan_image_directory(image_dir)
    manifest_map = {d["doc_id"]: d for d in manifest_docs}
    manifest_doc_ids = set(manifest_map.keys())
    image_doc_ids = set(doc_tags.keys())

    all_issues: list[dict[str, Any]] = []

    for unk in unknown_tags:
        all_issues.append({"type": "WARNING", "msg": f"Non-standard tag ignored: {unk}"})

    # Check for images without manifest record
    images_not_in_manifest = image_doc_ids - manifest_doc_ids
    for img_id in sorted(images_not_in_manifest):
        all_issues.append({
            "type": "WARNING",
            "msg": f"Image file '{img_id}' not found in manifest doc_ids",
        })

    # Invert mapping: attribute -> set of colors that trigger True
    attr_to_colors: dict[str, set[str]] = {}
    for color, attr in mapping.items():
        attr_to_colors.setdefault(attr, set()).add(color)

    mapped_attributes = sorted(attr_to_colors.keys())

    # Diff and field tracking
    diffs: dict[str, list[dict[str, Any]]] = {}
    field_counts_before: Counter[str] = Counter()
    field_counts_after: Counter[str] = Counter()

    for doc in manifest_docs:
        doc_id = doc["doc_id"]
        doc_diffs: list[dict[str, Any]] = []

        # Count before
        for attr in mapped_attributes:
            if doc.get(attr) is True:
                field_counts_before[attr] += 1

        # Apply closed-world update if document was in image_dir
        if doc_id in image_doc_ids:
            file_colors = doc_tags[doc_id]
            for attr in mapped_attributes:
                trigger_colors = attr_to_colors[attr]
                old_val = doc.get(attr, False)
                # Closed-world: True if tagged with any mapped color for this attr, False otherwise
                new_val = any(c in file_colors for c in trigger_colors)

                if old_val != new_val:
                    doc_diffs.append({
                        "field": attr,
                        "old": old_val,
                        "new": new_val,
                    })
                doc[attr] = new_val

        # Count after
        for attr in mapped_attributes:
            if doc.get(attr) is True:
                field_counts_after[attr] += 1

        if doc_diffs:
            diffs[doc_id] = doc_diffs

    report = {
        "manifest_path": str(manifest_path),
        "image_dir": str(image_dir),
        "total_manifest_docs": len(manifest_docs),
        "images_in_dir": len(image_doc_ids),
        "docs_modified_count": len(diffs),
        "docs_unchanged_count": len(manifest_docs) - len(diffs),
        "mapping": mapping,
        "mapped_attributes": mapped_attributes,
        "field_counts_before": dict(field_counts_before),
        "field_counts_after": dict(field_counts_after),
        "issues": all_issues,
        "diffs": diffs,
    }

    return manifest_docs, report


def print_report(report: dict[str, Any], dry_run: bool, max_diffs: int = 10) -> None:
    """Prints formatted report with mapping summary, field counts, and diffs."""
    print("\n" + "=" * 75)
    print("📋 MANIFEST TAG ASSIGNMENT & VALIDATION REPORT")
    print("=" * 75)
    mode_str = "🛡️  DRY RUN (No changes written to disk)" if dry_run else "✍️  APPLY MODE (Writing changes to disk)"
    print(f"Execution Mode           : {mode_str}")
    print(f"Manifest Path            : {report['manifest_path']}")
    print(f"Image Directory          : {report['image_dir']}")
    print(f"Total Manifest Documents : {report['total_manifest_docs']}")
    print(f"Images Processed         : {report['images_in_dir']}")
    print(f"Documents Modified       : {report['docs_modified_count']}")
    print(f"Documents Unchanged      : {report['docs_unchanged_count']}")

    # Active Mapping Table
    mapping = report.get("mapping", {})
    print("\n" + "-" * 75)
    print("🎯 ACTIVE TAG MAPPINGS")
    print("-" * 75)
    if not mapping:
        print("  (No tags mapped to attributes; manifest unchanged)")
    else:
        for num, color in COLOR_SHORTCUTS:
            if color in mapping:
                attr = mapping[color]
                print(f"  [{num}] {color:<10} ➔  {attr}")

    # Issues & Validation
    issues = report.get("issues", [])
    errors = [i for i in issues if i.get("type") == "ERROR"]
    warnings = [i for i in issues if i.get("type") == "WARNING"]

    print("\n" + "-" * 75)
    print(f"🔍 VALIDATION & SANITY CHECKS: {len(errors)} error(s), {len(warnings)} warning(s)")
    print("-" * 75)
    if not issues:
        print("  ✅ All records processed with 0 errors and 0 warnings.")
    else:
        for err in errors:
            print(f"  ❌ ERROR: {err['msg']}")
        for warn in warnings:
            print(f"  ⚠️  WARNING: {warn['msg']}")

    # Field Counts Comparison Table
    mapped_attributes = report.get("mapped_attributes", [])
    if mapped_attributes:
        print("\n" + "-" * 75)
        print(f"{'Field Name':<36} | {'Before (True)':<15} | {'After (True)':<15} | {'Net Change':<10}")
        print("-" * 75)
        for field in mapped_attributes:
            before = report["field_counts_before"].get(field, 0)
            after = report["field_counts_after"].get(field, 0)
            net = after - before
            net_str = f"+{net}" if net > 0 else str(net)
            print(f"{field:<36} | {before:>13} | {after:>13} | {net_str:>10}")
        print("-" * 75)

    # Sample Diffs
    diffs = report.get("diffs", {})
    if diffs and max_diffs != 0:
        display_count = len(diffs) if max_diffs < 0 else min(max_diffs, len(diffs))
        print(f"\n📝 SAMPLE MODIFICATIONS (First {display_count} of {len(diffs)} documents):")
        for i, (doc_id, field_diffs) in enumerate(list(diffs.items())[:display_count], 1):
            print(f"\n  [{i}] Document: {doc_id}")
            for d in field_diffs:
                print(f"      • {d['field']:<34} : {str(d['old']):<5} ➔ {str(d['new']):<5}")

    print("\n" + "=" * 75)


def get_default_image_dir() -> Path:
    for candidate in [Path("tag_images"), Path("indicGovBench/tag_images")]:
        if candidate.exists():
            return candidate
    return Path("tag_images")


def get_default_manifest() -> Path:
    return Path("data/manifests/documents.yaml")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Assign Apple Finder tag annotations from image directory to documents.yaml",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--image-dir",
        "-i",
        type=Path,
        default=get_default_image_dir(),
        help="Path to directory containing tagged image files (default: tag_images or indicGovBench/tag_images)",
    )
    parser.add_argument(
        "--manifest",
        "-m",
        type=Path,
        default=get_default_manifest(),
        help="Path to input manifest YAML file (default: data/manifests/documents.yaml)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=None,
        help="Path to output updated YAML file. If omitted and --apply is used, updates --manifest in-place.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Dry run mode: validate and report diffs without modifying files (default behavior)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Apply changes and write updated manifest to disk in-place",
    )
    parser.add_argument(
        "--map",
        type=str,
        default=None,
        help="CLI mapping string e.g. '1=scan_has_dots,2=scan_has_tilt' or 'Red=scan_has_dots'",
    )
    parser.add_argument(
        "--mapping-file",
        type=Path,
        default=None,
        help="Path to existing YAML mapping file",
    )
    parser.add_argument(
        "--save-mapping",
        type=Path,
        default=None,
        help="Path to save the resolved mapping to a YAML file",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        default=False,
        help="Run without interactive prompt (skips any unmapped colors)",
    )
    parser.add_argument(
        "--max-diffs",
        type=int,
        default=10,
        help="Maximum sample diffs to print (-1 for all, default: 10)",
    )

    args = parser.parse_args()

    # Determine execution mode
    if args.dry_run:
        dry_run = True
    elif args.output or args.apply:
        dry_run = False
    else:
        dry_run = True

    output_path = args.output or (args.manifest if args.apply else None)

    # 1. Load manifest and discover valid boolean attributes
    if not args.manifest.exists():
        sys.exit(f"❌ Manifest file not found: {args.manifest}")

    with open(args.manifest, "r", encoding="utf-8") as f:
        manifest_docs = yaml.safe_load(f)

    if not isinstance(manifest_docs, list):
        sys.exit(f"❌ Invalid manifest format in {args.manifest}: expected a list of documents")

    valid_attributes = discover_boolean_attributes(manifest_docs)

    # 2. Scan image directory
    try:
        doc_tags, tag_counts, unknown_tags = scan_image_directory(args.image_dir)
    except Exception as e:
        sys.exit(f"❌ Error scanning image directory: {e}")

    # 3. Resolve mapping (CLI / file / interactive)
    try:
        preset_mapping = parse_cli_mapping(args.map, args.mapping_file, valid_attributes)
    except Exception as e:
        sys.exit(f"❌ Error parsing mapping: {e}")

    mapping = resolve_interactive_mapping(
        tag_counts=tag_counts,
        preset_mapping=preset_mapping,
        valid_attributes=valid_attributes,
        non_interactive=args.non_interactive,
    )

    if args.save_mapping and mapping:
        save_mapping_to_file(mapping, args.save_mapping)

    # 4. Process updates
    try:
        updated_manifest, report = process_manifest_tags(
            manifest_path=args.manifest,
            image_dir=args.image_dir,
            mapping=mapping,
        )
    except Exception as e:
        sys.exit(f"❌ Error processing tags: {e}")

    print_report(report, dry_run=dry_run, max_diffs=args.max_diffs)

    has_errors = any(i.get("type") == "ERROR" for i in report.get("issues", []))

    if dry_run or not output_path:
        print("💡 Dry run complete. No files were modified.")
        if output_path:
            print(f"   (Target output path: {output_path})")
        if has_errors:
            print("❌ Cannot write: Please resolve the validation errors above first.")
        else:
            print("✅ Dry run passed cleanly! To apply changes in-place, run with --apply:")
            print(f"   python3 scripts/assign_tags_to_manifest.py --image-dir {args.image_dir} --apply\n")
    else:
        if has_errors:
            print("❌ Aborted writing: Validation errors detected. Fix errors before writing.")
            sys.exit(1)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(updated_manifest, f, allow_unicode=True, sort_keys=False)
        print(f"✅ Successfully wrote updated manifest to: {output_path}\n")


if __name__ == "__main__":
    main()
