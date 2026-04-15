"""
run_pipeline.py
─────────────────────────────────────────────────────────────────
MASTER RUNNER — Collab Architecture RFP Pipeline

Runs all 3 steps in sequence:
  Step 1: Discover IDML frames (optional but recommended first time)
  Step 2: Generate AI content with Claude
  Step 3: Inject content into IDML template

Usage:
    # Full pipeline
    python run_pipeline.py \
        --idml "2026_Master_Template.idml" \
        --rfp "Design of New Recreation Center" \
        --client "Town of Windsor, CO" \
        --date "June 15, 2025" \
        --rfp_number "2025-014"

    # Skip discovery (after first run)
    python run_pipeline.py \
        --idml "2026_Master_Template.idml" \
        --rfp "..." --client "..." \
        --skip-discovery

    # Use existing generated_content.json (re-inject only)
    python run_pipeline.py \
        --idml "2026_Master_Template.idml" \
        --skip-generate

Requirements:
    pip install anthropic pdfplumber lxml reportlab
    export ANTHROPIC_API_KEY="sk-ant-..."
"""

import argparse
import subprocess
import sys
import os
from pathlib import Path
from datetime import datetime

def run_step(script, args_list, step_name):
    print(f"\n{'─'*60}")
    print(f"  RUNNING: {step_name}")
    print(f"{'─'*60}")
    cmd = [sys.executable, script] + args_list
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"\n❌ {step_name} failed. Stopping pipeline.")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Collab Architecture RFP Pipeline")
    parser.add_argument("--idml",           required=True, help="Path to .idml template")
    parser.add_argument("--rfp",            default="Design and Construction of New Community Recreation Center")
    parser.add_argument("--client",         default="Town of Windsor, Colorado")
    parser.add_argument("--date",           default=datetime.today().strftime("%B %d, %Y"))
    parser.add_argument("--rfp_number",     default="2025-001")
    parser.add_argument("--skip-discovery", action="store_true", help="Skip Step 1 frame discovery")
    parser.add_argument("--skip-generate",  action="store_true", help="Skip Step 2, use existing generated_content.json")
    args = parser.parse_args()

    pipeline_dir = Path(__file__).parent

    print(f"\n{'='*60}")
    print("  COLLAB ARCHITECTURE — RFP AI PIPELINE")
    print(f"{'='*60}")
    print(f"  IDML   : {args.idml}")
    print(f"  RFP    : {args.rfp}")
    print(f"  Client : {args.client}")
    print(f"  Date   : {args.date}")
    print(f"{'='*60}")

    # ── STEP 1: Frame Discovery ───────────────────────────────────────────────
    if not args.skip_discovery:
        run_step(
            str(pipeline_dir / "01_discover_frames.py"),
            ["--idml", args.idml],
            "Step 1: IDML Frame Discovery"
        )
    else:
        print("\n  ⏭  Skipping Step 1 (frame discovery)")

    # ── STEP 2: Generate Content ──────────────────────────────────────────────
    if not args.skip_generate:
        run_step(
            str(pipeline_dir / "02_generate_content.py"),
            [
                "--rfp",        args.rfp,
                "--client",     args.client,
                "--date",       args.date,
                "--rfp_number", args.rfp_number,
            ],
            "Step 2: AI Content Generation"
        )
    else:
        print("\n  ⏭  Skipping Step 2 (using existing generated_content.json)")
        if not Path("generated_content.json").exists():
            print("  ❌ generated_content.json not found. Run without --skip-generate first.")
            sys.exit(1)

    # ── STEP 3: Inject into IDML ──────────────────────────────────────────────
    frame_map_arg = []
    if Path("frame_map.json").exists():
        frame_map_arg = ["--frame-map", "frame_map.json"]

    run_step(
        str(pipeline_dir / "03_inject_idml.py"),
        ["--idml", args.idml, "--content", "generated_content.json"] + frame_map_arg,
        "Step 3: IDML Injection"
    )

    # ── DONE ──────────────────────────────────────────────────────────────────
    idml_p = Path(args.idml)
    output_file = idml_p.parent / f"{idml_p.stem}_filled.idml"

    print(f"\n{'='*60}")
    print("  🎉 PIPELINE COMPLETE")
    print(f"{'='*60}")
    print(f"  Output : {output_file}")
    print(f"\n  Next steps:")
    print(f"  1. Open {output_file} in Adobe InDesign")
    print(f"  2. Review all generated text sections")
    print(f"  3. Swap placeholder images for real project photos")
    print(f"  4. File → Export → Adobe PDF (Print) for final submission")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
