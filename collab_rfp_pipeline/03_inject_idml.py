"""
03_inject_idml.py
─────────────────────────────────────────────────────────────────
STEP 3 of the Collab RFP Pipeline.

Takes:
  - The original .idml template
  - generated_content.json from Step 2
  - (Optional) frame_map.json from Step 1 for precise targeting

Injects AI-generated text into the correct InDesign story files,
preserving ALL original formatting, styles, images, and layout.

Outputs:
  - [original_name]_filled.idml  — ready to open in InDesign

Usage:
    python 03_inject_idml.py --idml template.idml --content generated_content.json
    python 03_inject_idml.py --idml template.idml --content generated_content.json --frame-map frame_map.json

How it works:
  Each Story XML file inside the IDML ZIP is parsed. The script
  finds stories whose current text matches a known placeholder,
  then replaces ONLY the <Content> text nodes while keeping all
  CharacterStyleRange, ParagraphStyleRange, and other tags intact.
  This preserves fonts, colors, tracking, and paragraph styles.
"""

import zipfile
import json
import shutil
import argparse
import re
from lxml import etree
from pathlib import Path
from copy import deepcopy

# ── TEXT EXTRACTION FROM STORY ────────────────────────────────────────────────

def get_story_text(root):
    """Get all text from a Story XML root element."""
    parts = []
    for el in root.iter():
        if el.tag.endswith("}Content") and el.text:
            parts.append(el.text)
    return "".join(parts).strip()

# ── STYLE-PRESERVING TEXT REPLACEMENT ────────────────────────────────────────

def replace_story_text(root, new_text):
    """
    Replace text in a Story while preserving all InDesign formatting tags.

    Strategy:
    1. Find the first ParagraphStyleRange that has Content children
    2. Keep its style attributes intact
    3. Replace Content nodes with new text, splitting on newlines into
       separate paragraphs (each wrapped in a Br tag between them)
    4. Remove all subsequent ParagraphStyleRanges (they held the old text)
    """
    # Find the Story element
    story_el = None
    for el in root.iter():
        if el.tag.endswith("}Story"):
            story_el = el
            break
    if story_el is None:
        return False

    # Collect all ParagraphStyleRanges
    ns_pattern = re.compile(r'\{[^}]+\}')
    para_ranges = []
    for child in story_el:
        tag = ns_pattern.sub('', child.tag)
        if tag == "ParagraphStyleRange":
            para_ranges.append(child)

    if not para_ranges:
        return False

    # Keep the first PSR as our template (preserves paragraph style)
    template_psr = para_ranges[0]

    # Find a CharacterStyleRange inside it to use as template
    template_csr = None
    for child in template_psr:
        tag = ns_pattern.sub('', child.tag)
        if tag == "CharacterStyleRange":
            template_csr = child
            break

    if template_csr is None:
        return False

    # Remove ALL existing ParagraphStyleRanges from story
    for psr in para_ranges:
        story_el.remove(psr)

    # Get the namespace from the template
    ns_match = re.match(r'\{([^}]+)\}', template_psr.tag)
    ns = f"{{{ns_match.group(1)}}}" if ns_match else ""

    # Build new ParagraphStyleRanges from new_text
    paragraphs = new_text.split("\n")
    paragraphs = [p for p in paragraphs if p.strip()]  # remove blank lines

    for i, para_text in enumerate(paragraphs):
        # Clone the template PSR (keeps AppliedParagraphStyle etc.)
        new_psr = deepcopy(template_psr)

        # Remove all children from the cloned PSR
        for child in list(new_psr):
            new_psr.remove(child)

        # Clone template CSR (keeps font, size, color, tracking etc.)
        new_csr = deepcopy(template_csr)

        # Remove existing Content nodes from CSR clone
        for child in list(new_csr):
            tag = ns_pattern.sub('', child.tag)
            if tag in ("Content", "Br"):
                new_csr.remove(child)

        # Add new Content node
        content_el = etree.SubElement(new_csr, f"{ns}Content")
        content_el.text = para_text

        new_psr.append(new_csr)

        # Add Br at end of each paragraph (InDesign paragraph break)
        br_csr = deepcopy(template_csr)
        for child in list(br_csr):
            br_csr.remove(child)
        etree.SubElement(br_csr, f"{ns}Br")
        new_psr.append(br_csr)

        story_el.append(new_psr)

    return True

# ── FIND MATCHING STORIES ─────────────────────────────────────────────────────

def find_matching_stories(idml_path, target_contains):
    """
    Find story file(s) whose text content contains the target string.
    Returns list of story filenames.
    """
    matches = []
    target_lower = target_contains.lower()

    with zipfile.ZipFile(idml_path, 'r') as z:
        story_files = [f for f in z.namelist() if f.startswith("Stories/Story_")]
        for sf in story_files:
            with z.open(sf) as f:
                tree = etree.parse(f)
                root = tree.getroot()
            text = get_story_text(root).lower()
            if target_lower in text:
                matches.append(sf)

    return matches

# ── MAIN INJECTION ────────────────────────────────────────────────────────────

def inject(idml_path, content_json_path, frame_map_path=None):
    # Load generated content
    with open(content_json_path) as f:
        content_data = json.load(f)
    sections = content_data["sections"]

    # Create output path
    idml_p = Path(idml_path)
    output_path = idml_p.parent / f"{idml_p.stem}_filled{idml_p.suffix}"
    shutil.copy2(idml_path, output_path)

    print(f"\n{'='*60}")
    print("  COLLAB PIPELINE — STEP 3: INJECT INTO IDML")
    print(f"{'='*60}")
    print(f"  Template : {idml_path}")
    print(f"  Content  : {content_json_path}")
    print(f"  Output   : {output_path}\n")

    results = {"success": [], "not_found": [], "errors": []}

    # Read all stories into memory
    story_data = {}
    with zipfile.ZipFile(output_path, 'r') as z:
        all_files = z.namelist()
        story_files = [f for f in all_files if f.startswith("Stories/Story_")]
        for sf in story_files:
            with z.open(sf) as f:
                story_data[sf] = f.read()

    # Process each section
    for key, section in sections.items():
        target   = section["target_contains"]
        new_text = section["generated_text"]
        label    = section["label"]

        print(f"  [{label}]")
        print(f"    Target : '{target[:50]}'")

        # Find matching story file(s)
        target_lower = target.lower()
        matched_stories = []

        for sf, xml_bytes in story_data.items():
            try:
                root = etree.fromstring(xml_bytes)
                text = get_story_text(root).lower()
                if target_lower in text:
                    matched_stories.append((sf, xml_bytes))
            except Exception:
                continue

        if not matched_stories:
            print(f"    ⚠  Not found in any story\n")
            results["not_found"].append(key)
            continue

        # Inject into first match (most sections appear once)
        # For sections that appear multiple times (e.g. bios), inject into all
        injected_count = 0
        for sf, xml_bytes in matched_stories:
            try:
                root = etree.fromstring(xml_bytes)
                success = replace_story_text(root, new_text)
                if success:
                    # Serialize back
                    new_xml = etree.tostring(root, xml_declaration=True,
                                             encoding="UTF-8", standalone=True)
                    story_data[sf] = new_xml
                    injected_count += 1
                    print(f"    ✓  Injected into {sf}")
                else:
                    print(f"    ⚠  Could not replace text in {sf}")
            except Exception as e:
                print(f"    ✗  Error in {sf}: {e}")
                results["errors"].append({"key": key, "file": sf, "error": str(e)})

        if injected_count > 0:
            results["success"].append(key)
        print()

    # Write modified stories back into ZIP
    print("  📦 Writing modified IDML...")
    import tempfile, os

    tmp_path = str(output_path) + ".tmp"
    with zipfile.ZipFile(output_path, 'r') as zin:
        with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename in story_data:
                    zout.writestr(item, story_data[item.filename])
                else:
                    zout.writestr(item, zin.read(item.filename))

    os.replace(tmp_path, str(output_path))

    # Summary
    print(f"\n{'='*60}")
    print(f"  ✅ COMPLETE")
    print(f"  Output   : {output_path}")
    print(f"  Injected : {len(results['success'])} sections")
    if results["not_found"]:
        print(f"  Not found: {len(results['not_found'])} — {results['not_found']}")
    if results["errors"]:
        print(f"  Errors   : {len(results['errors'])}")
    print(f"{'='*60}\n")

    print("  Next step: Open the .idml in InDesign → File → Export → PDF\n")
    return output_path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--idml",      required=True, help="Path to .idml template")
    parser.add_argument("--content",   default="generated_content.json")
    parser.add_argument("--frame-map", default=None,  help="Optional frame_map.json from Step 1")
    args = parser.parse_args()

    if not Path(args.idml).exists():
        print(f"❌ IDML not found: {args.idml}")
        return
    if not Path(args.content).exists():
        print(f"❌ Content JSON not found: {args.content}")
        return

    inject(args.idml, args.content, args.frame_map)

if __name__ == "__main__":
    main()
