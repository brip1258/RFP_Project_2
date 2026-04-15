"""
01_discover_frames.py
─────────────────────────────────────────────────────────────────
STEP 1 of the Collab RFP Pipeline.

Reads the .idml file and outputs a map of every text frame:
  - Frame ID
  - Spread / page it lives on
  - Current text content (first 120 chars)
  - Geometric position (x, y, width, height)

This lets you identify WHICH frame IDs correspond to the
lorem ipsum / placeholder sections so they can be targeted
in Step 3 (injection).

Usage:
    python 01_discover_frames.py --idml template.idml
    python 01_discover_frames.py --idml template.idml --search "lorem"
    python 01_discover_frames.py --idml template.idml --search "Insert Bio"

Output:
    frame_map.json   — full frame inventory
    frame_map.txt    — human-readable summary
"""

import zipfile
import json
import argparse
import re
from lxml import etree
from pathlib import Path

IDML_NS = {
    "idPkg": "http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging",
}

def parse_bounds(element):
    """Extract GeometricBounds as (y1, x1, y2, x2) → convert to x,y,w,h."""
    bounds = element.get("GeometricBounds", "")
    if bounds:
        parts = [float(v) for v in bounds.split()]
        if len(parts) == 4:
            y1, x1, y2, x2 = parts
            return {"x": round(x1,2), "y": round(y1,2),
                    "w": round(x2-x1,2), "h": round(y2-y1,2)}
    return {}

def extract_text_content(story_xml):
    """Pull all text content from a Story XML element."""
    texts = []
    for elem in story_xml.iter():
        if elem.tag.endswith("}Content") and elem.text:
            texts.append(elem.text)
        elif elem.tag.endswith("}Br"):
            texts.append("\n")
    return "".join(texts).strip()

def discover_frames(idml_path, search_term=None):
    frames = []

    with zipfile.ZipFile(idml_path, 'r') as z:
        file_list = z.namelist()

        # Build story content map: storyID → text
        story_texts = {}
        story_files = [f for f in file_list if f.startswith("Stories/Story_")]
        for sf in story_files:
            story_id = Path(sf).stem.replace("Story_", "")
            with z.open(sf) as f:
                tree = etree.parse(f)
                root = tree.getroot()
                text = extract_text_content(root)
                story_texts[story_id] = text

        # Walk each Spread to find TextFrames
        spread_files = sorted([f for f in file_list if f.startswith("Spreads/Spread_")])
        for spread_idx, spread_file in enumerate(spread_files):
            spread_name = Path(spread_file).stem.replace("Spread_", "")
            with z.open(spread_file) as f:
                tree = etree.parse(f)
                root = tree.getroot()

            # Find all TextFrame elements
            for tf in root.iter():
                if not tf.tag.endswith("}TextFrame"):
                    continue

                frame_id   = tf.get("Self", "")
                story_ref  = tf.get("ParentStory", "")
                bounds     = parse_bounds(tf)
                story_text = story_texts.get(story_ref, "")
                preview    = story_text[:120].replace("\n", " ").strip()

                frame = {
                    "frame_id":   frame_id,
                    "story_id":   story_ref,
                    "spread":     spread_name,
                    "spread_idx": spread_idx + 1,
                    "bounds":     bounds,
                    "preview":    preview,
                    "char_count": len(story_text),
                }
                frames.append(frame)

    # Optional filter
    if search_term:
        term = search_term.lower()
        frames = [f for f in frames if term in f["preview"].lower()]

    return frames

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--idml",   required=True, help="Path to .idml file")
    parser.add_argument("--search", default=None,  help="Filter frames by text content")
    args = parser.parse_args()

    if not Path(args.idml).exists():
        print(f"❌ File not found: {args.idml}")
        return

    print(f"\n{'='*60}")
    print("  COLLAB PIPELINE — STEP 1: FRAME DISCOVERY")
    print(f"{'='*60}")
    print(f"  File   : {args.idml}")
    if args.search:
        print(f"  Filter : '{args.search}'")
    print()

    frames = discover_frames(args.idml, args.search)

    print(f"  Found {len(frames)} text frame(s)\n")

    # Save JSON map
    with open("frame_map.json", "w") as f:
        json.dump(frames, f, indent=2)

    # Write human-readable summary
    lines = []
    lines.append(f"COLLAB ARCHITECTURE — IDML FRAME MAP")
    lines.append(f"Source: {args.idml}")
    lines.append(f"Total frames: {len(frames)}")
    lines.append("="*60)

    for i, frame in enumerate(frames):
        b = frame["bounds"]
        lines.append(f"\n[{i+1}] Frame ID : {frame['frame_id']}")
        lines.append(f"     Story ID : {frame['story_id']}")
        lines.append(f"     Spread   : {frame['spread']} (page ~{frame['spread_idx']})")
        lines.append(f"     Position : x={b.get('x')} y={b.get('y')} w={b.get('w')} h={b.get('h')}")
        lines.append(f"     Chars    : {frame['char_count']}")
        lines.append(f"     Preview  : {frame['preview'][:100]}")

    summary = "\n".join(lines)
    with open("frame_map.txt", "w") as f:
        f.write(summary)

    print(summary)
    print(f"\n✅ Saved: frame_map.json + frame_map.txt")

    # Highlight likely placeholder frames
    placeholder_keywords = [
        "lorem", "ipsum", "mustibus", "turehenis", "insert bio",
        "rfp title", "entity", "first last", "xx", "insert caption",
        "project title", "city, state", "firm name"
    ]
    placeholders = []
    for f in frames:
        preview_lower = f["preview"].lower()
        if any(kw in preview_lower for kw in placeholder_keywords):
            placeholders.append(f)

    if placeholders:
        print(f"\n🎯 LIKELY PLACEHOLDER FRAMES ({len(placeholders)} found):")
        print("-"*40)
        for f in placeholders:
            print(f"  {f['frame_id']} | spread {f['spread_idx']} | {f['preview'][:80]}")

if __name__ == "__main__":
    main()
