# Collab Architecture — RFP AI Pipeline

Automatically fills the Collab Architecture InDesign master template
with AI-generated proposal text using Claude, then saves as a filled
`.idml` ready to open in InDesign.

---

## How it works

```
2026_Master_Template.idml
        │
        ▼
01_discover_frames.py     → frame_map.json      (what's in each text frame)
        │
        ▼
02_generate_content.py    → generated_content.json   (Claude-generated text)
        │
        ▼
03_inject_idml.py         → template_filled.idml     (ready for InDesign)
        │
        ▼
   Open in InDesign → swap photos → Export PDF → Submit
```

---

## Setup

```bash
pip install anthropic pdfplumber lxml reportlab
export ANTHROPIC_API_KEY="sk-ant-..."
```

---

## Usage

### Full pipeline (one command)

```bash
python run_pipeline.py \
  --idml "2026_Master_Template.idml" \
  --rfp "Design and Construction of Rifle Field House" \
  --client "City of Rifle, Colorado" \
  --date "June 15, 2025" \
  --rfp_number "2025-014"
```

### Run steps individually

```bash
# Step 1: See all text frames in the template (run once)
python 01_discover_frames.py --idml template.idml

# Search for specific placeholder text
python 01_discover_frames.py --idml template.idml --search "lorem"
python 01_discover_frames.py --idml template.idml --search "Insert Bio"

# Step 2: Generate content for a specific RFP
python 02_generate_content.py \
  --rfp "New Senior Center" \
  --client "Town of Berthoud, CO"

# Step 3: Inject into IDML
python 03_inject_idml.py \
  --idml template.idml \
  --content generated_content.json
```

### Re-run injection only (after editing generated_content.json)

```bash
python run_pipeline.py \
  --idml template.idml \
  --skip-discovery \
  --skip-generate
```

---

## Output files

| File | Description |
|------|-------------|
| `frame_map.json` | Every text frame with ID, position, page, preview |
| `frame_map.txt` | Human-readable version of frame map |
| `generated_content.json` | All AI-generated text, keyed by section |
| `*_filled.idml` | Final output — open this in InDesign |

---

## What gets generated

| Section | Template Location |
|---------|-------------------|
| Cover page RFP title | Page 1 |
| Cover page client name | Page 1 |
| Cover letter Re: line | Page 3 |
| Cover letter salutation | Page 3 |
| Cover letter body (4 paragraphs) | Page 3 |
| Cover letter date | Page 3 |
| Firm headline | Page 7 |
| Expertise section title | Page 9 |
| Expertise narrative | Page 9 |
| Work location proximity | Page 7 |
| Project descriptions (×2) | Pages 16-21 |
| Team bio — Jordan Lockner | Pages 12-14 |
| Team bio — Bryan Merritt | Pages 12-14 |
| Schedule intro sentence | Page 24 |
| Schedule project name bar | Page 24 |

---

## Adding new sections

Edit `02_generate_content.py` — add an entry to the `SECTIONS` dict:

```python
"my_new_section": {
    "label": "My New Section",
    "target_contains": "exact text currently in that InDesign frame",
    "max_tokens": 200,
    "prompt": "Write ... for {rfp_title} submitted to {client_name}."
},
```

The `target_contains` value is the key — it's how the injector
finds the right story file inside the IDML ZIP. Use Step 1
(frame discovery) to find the exact current text in any frame.

---

## After running the pipeline

1. Open `*_filled.idml` in Adobe InDesign
2. Review all generated text — proofread and adjust tone
3. Replace yellow-highlighted placeholder images with real project photos
4. Update the project team org chart (page 11) with real subcontractor names
5. Fill in fee proposal table (page 25) manually
6. File → Export → Adobe PDF (Print) for final submission

---

## Cost

~$0.01 per RFP run using Claude Haiku.
Switch to `claude-sonnet-4-6` in `02_generate_content.py` for
higher quality text (~$0.04/run).
