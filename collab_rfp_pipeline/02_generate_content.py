"""
02_generate_content.py
─────────────────────────────────────────────────────────────────
STEP 2 of the Collab RFP Pipeline.

Reads the RFP details you provide and generates all text content
using Claude AI. Outputs a structured JSON file used by Step 3
to inject text into the IDML.

Style is modeled on Collab Architecture's actual written RFPs:
direct, technically specific, community-focused, no generic filler.
Bold text (**like this**) is used sparingly for key differentiators.

Usage:
    python 02_generate_content.py \
        --rfp "ADAL EMEDS and EOD - Building 814" \
        --client "State of Colorado Department of Military and Veterans Affairs" \
        --date "February 4, 2026" \
        --rfp_number "RFQ1 2026-0027"

Output:
    generated_content.json
"""

import os
import json
import argparse
import anthropic
from datetime import datetime

# ── STYLE GUIDE SYSTEM PROMPT ─────────────────────────────────────────────────
# Distilled from Collab Architecture's actual written RFP submissions.
# Used as the system prompt for every Claude call to enforce consistent voice.

STYLE_GUIDE = """
You are writing professional architecture RFQ/RFP response content for Collab Architecture,
a Windsor, Colorado-based firm. Match their documented voice exactly.

VOICE & TONE:
- Direct, confident, technically specific — never generic or filler
- Professional and warm without being sentimental
- Every sentence earns its place; no throat-clearing, no restating context
- Use bold (**word or phrase**) sparingly to flag key differentiators and facts
- Never begin with "We are excited to" or "We are pleased to"

COVER LETTER STRUCTURE (5-6 paragraphs, from actual Collab submissions):
1. Open with a direct statement about what the project represents — its stakes and purpose
2. State Collab's qualifications for this specific scope; mention delivery method if known
3. Detail the scope of services Collab will provide; name specific work items
4. Cite relevant experience with specific evidence (**bold** dollar values, project types)
5. Name key team leads and their roles; note subconsultant relationships
6. Commitment statement + close (one tight sentence each)

SECTION HEADLINE STYLE:
- All caps, 5-8 words, outcome/action-oriented
- Examples from real Collab RFPs:
    "DESIGNING FUNCTIONAL SPACES THAT ENHANCE PERFORMANCE"
    "DESIGNING SPACES THAT BRING COMMUNITIES TOGETHER"

FIRM IDENTITY (always factually accurate):
- Motto: "Stop. Collaborate and Listen." — literal working method, not just a tagline
- Mission quote: "Bringing the power of collaborative design to create a stronger,
  better, and more sustainable community."
- Address: 9217 Eastman Park Dr, Windsor, CO 80550
- Phone: 970-292-7078 | Web: www.collabarchitects.com
- Services: full-service commercial architecture, planning, engineering coordination

TEAM (use real names and credentials):
- Jordan W. Lockner, AIA, NCARB — Founding Principal; Principal-in-Charge
- Emily Perkins, AIT — Project Designer / Job Captain
- Kevin Dorsey — Design Manager (30+ years construction & design experience)
- Michael Aller — QA/QC Manager
- Bryan Merritt — Project Manager

SUBCONSULTANTS (name when relevant):
- Bridgers & Paxton — MEP/AV/IT engineering
- Corbel Engineering — structural
- JVA Consulting Engineers — civil

WRITING RULES:
- "Collab" or "Collab Architecture" for the firm name (not exclusively "we")
- For government/military projects: emphasize constructability, durability, code compliance,
  mission continuity, phasing around active operations
- Cite specific Colorado project names and locations when giving experience evidence
- Time commitments are stated as percentages (30%, 40%)
- Bold only 2-4 phrases per section maximum
- Return ONLY the requested text — no headers, labels, or meta-commentary
"""

# ── SECTION DEFINITIONS ───────────────────────────────────────────────────────
# Maps section keys → prompt templates + metadata for IDML injection targeting.
# target_contains = snippet of placeholder text currently in that IDML frame.

SECTIONS = {

    # ── COVER PAGE ────────────────────────────────────────────────────────────
    "cover_rfp_title": {
        "label": "Cover Page — RFP Title",
        "target_contains": "RFP TITLE",
        "max_tokens": 50,
        "prompt": (
            "Write a clean 3-6 word project title for this RFP: {rfp_title} for {client_name}. "
            "Title case. No period. Return ONLY the title."
        ),
    },
    "cover_client": {
        "label": "Cover Page — Entity/Client",
        "target_contains": "ENTITY / CLIENT",
        "max_tokens": 30,
        "prompt": (
            "Return just the client/entity name formatted for a proposal cover page: {client_name}. "
            "No extra words."
        ),
    },

    # ── COVER LETTER (Page 3) ─────────────────────────────────────────────────
    "cover_letter_re": {
        "label": "Cover Letter — Re: line",
        "target_contains": "Re: RFP #",
        "max_tokens": 40,
        "prompt": (
            "Write a Re: line for a formal cover letter. "
            "Format: 'Re: {rfp_number} | {rfp_title}'. Return ONLY the Re: line."
        ),
    },
    "cover_letter_salutation": {
        "label": "Cover Letter — Salutation",
        "target_contains": "To [Client Name]",
        "max_tokens": 25,
        "prompt": (
            "Write a formal salutation for a cover letter to the selection committee at "
            "{client_name}. Use the format from real Collab letters: "
            "'To [Contact Name or Title] and Members of the Selection Committee,' "
            "Return ONLY the salutation line."
        ),
    },
    "cover_letter_body": {
        "label": "Cover Letter — Body",
        "target_contains": "Turehenis",
        "max_tokens": 600,
        "prompt": """
Write the body of a professional cover letter for Collab Architecture responding to this RFP.

RFP: {rfp_title}
Client: {client_name}
RFQ Number: {rfp_number}
Date: {date}
Signatory: Jordan W. Lockner, AIA, NCARB, Founding Principal

Write exactly 6 paragraphs following this structure:
1. What this project represents — its operational stakes and purpose for the client
2. Collab's qualifications for this exact scope and delivery method
3. Specific services Collab will provide (design phases, engineering coordination, code compliance)
4. Relevant prior experience — **bold** specific project types, dollar values, or milestone achievements that prove fitness
5. Key team: name Jordan Lockner's role; name subconsultants Bridgers & Paxton, Corbel Engineering, JVA and their roles
6. One-sentence commitment to the client's mission + one-sentence close thanking them

Tone: confident, specific, zero filler. Bold 2-3 key phrases.
Return ONLY the letter body. No salutation, no "Sincerely", no headers.
""",
    },
    "cover_letter_date": {
        "label": "Cover Letter — Date",
        "target_contains": "Month Day, Year",
        "max_tokens": 20,
        "prompt": (
            "Return this date formatted for a formal letter: {date}. "
            "Example: 'February 4, 2026'. Return ONLY the formatted date."
        ),
    },

    # ── FIRM QUALIFICATIONS / WHO WE ARE (Pages 6-7) ──────────────────────────
    "firm_headline": {
        "label": "Firm Qualifications — Page Headline",
        "target_contains": "DESIGNING SPACES THAT BRING COMMUNITIES TOGETHER",
        "max_tokens": 30,
        "prompt": (
            "Write a 5-8 word headline for Collab Architecture's firm qualifications page. "
            "Tailor it to this project type: {rfp_title} for {client_name}. "
            "All caps. No period. Outcome-oriented (what does Collab design or deliver). "
            "Return ONLY the headline."
        ),
    },
    "who_we_are": {
        "label": "Firm Qualifications — Who We Are narrative",
        "target_contains": "Our team brings specialized",
        "max_tokens": 180,
        "prompt": """
Write the 'WHO WE ARE' narrative for Collab Architecture's firm qualifications section.
This is for: {rfp_title} submitted to {client_name}.

Write 2 short paragraphs:
Para 1: Describe Collab as a Windsor-based firm, one of the fastest growing in Northern Colorado
and the Front Range. Driven by collaborative spirit. Reference the motto "Stop. Collaborate and Listen."
as the actual working method — curiosity, humility, honest dialogue, no pre-packaged solutions.

Para 2: Describe the firm's qualifications and resources for this specific project type —
full-service commercial architecture, multi-firm interdisciplinary team.
Name relevant subconsultants (Bridgers & Paxton, Corbel Engineering, JVA) and the specific
expertise they add for {rfp_title}.

Return ONLY the two paragraphs.
""",
    },
    "unique_team_knowledge": {
        "label": "Firm Qualifications — Unique Knowledge of Key Team Members",
        "target_contains": "Are we close to the project site",
        "max_tokens": 220,
        "prompt": """
Write the 'UNIQUE KNOWLEDGE OF KEY TEAM MEMBERS' narrative for Collab Architecture.
Project: {rfp_title} for {client_name}.

Write one short paragraph per team member using this format:
**Name** of Collab [role description relevant to this project].

Include these four people in this order:
1. Jordan Lockner — leads multidisciplinary teams, relevant active-facility or technical project experience
2. Emily Perkins — rehabilitation and expansion of occupied facilities, structural mods, HVAC, additions
3. Kevin Dorsey — Design Manager, 30+ years construction/design, public facility expertise across Colorado
4. Michael Aller — QA/QC Manager, quality control and compliance review

Tailor each description to the specific demands of {rfp_title}.
Return ONLY the paragraphs, no section header.
""",
    },
    "on_site_presence": {
        "label": "Firm Qualifications — On-Site Presence",
        "target_contains": "Are we close to the project",
        "max_tokens": 80,
        "prompt": (
            "Write 2-3 sentences for the 'ON-SITE PRESENCE' callout box for Collab Architecture "
            "(Windsor, CO — 9217 Eastman Park Dr). "
            "Describe proximity to the project for {rfp_title} at {client_name}, "
            "availability for site visits, and responsiveness. "
            "Match the tone from real Collab text: "
            "'When needs arise, [client] needs a project manager and design person to rely on. "
            "With our office located in Windsor...' "
            "Return ONLY the callout text."
        ),
    },

    # ── OUR TEAM PAGE ─────────────────────────────────────────────────────────
    "team_experience_narrative": {
        "label": "Our Team — Experience on Projects as a Team",
        "target_contains": "The Collab team members on this project",
        "max_tokens": 150,
        "prompt": """
Write the 'EXPERIENCE ON PROJECTS AS A TEAM' paragraph for Collab Architecture's team page.
Project: {rfp_title} for {client_name}.

3-4 sentences covering:
- Collab team members work together daily and have designed similar projects throughout the firm's existence
- Collaboration — with each other and with clients — is where they excel
- They partner with trusted subconsultants to bring specialized expertise needed for this specific project
- They bring existing workflow efficiencies and rapport to the proposed interdisciplinary team

Tailor any project-specific language to {rfp_title}.
Return ONLY the paragraph.
""",
    },
    "subconsultants_narrative": {
        "label": "Our Team — Subconsultants",
        "target_contains": "Our team is supported by",
        "max_tokens": 200,
        "prompt": """
Write the 'SUBCONSULTANTS' narrative for Collab Architecture's team page.
Project: {rfp_title} for {client_name}.

Write one sentence intro, then one short paragraph per subconsultant:

Intro: Our team is supported by a trusted group of subconsultants who bring specialized
technical expertise essential to the successful delivery of [project shortname].

**JVA Consulting Engineers** — civil design services relevant to {rfp_title}
**Corbel Engineering** — structural design; balance structural upgrades with building integrity
**Bridgers & Paxton** — MEP and AV/IT; energy-efficient systems, lighting, security, HVAC

Each subconsultant paragraph should be 2 sentences, specific to what {rfp_title} demands.
Return ONLY the narrative. No section header.
""",
    },

    # ── TEAM BIOS (Pages 8-10) ────────────────────────────────────────────────
    "bio_lockner": {
        "label": "Team Bio — Jordan Lockner",
        "target_contains": "Insert Bio",
        "max_tokens": 160,
        "prompt": """
Write the bio paragraph for Jordan W. Lockner, AIA, NCARB, Founding Principal of Collab Architecture.
His project role: Principal-in-Charge for {rfp_title}.

3-4 sentences covering:
- His belief that good architecture must stem from the community it serves
- Ability to listen, understand, and collaborate while coordinating the design process and team
- Successful outcomes on projects of all sizes — large public projects to small business owners
- Well-versed in public projects throughout Northern Colorado; recognized leadership:
  2022 UC ENVD Young Designer Award, 2023 BizWest 40 Under 40, 2025 SMPS Colorado Firm Leader of the Year

Write in third person. Specific, no filler.
Return ONLY the bio paragraph.
""",
    },
    "bio_perkins": {
        "label": "Team Bio — Emily Perkins",
        "target_contains": "Insert Bio",
        "max_tokens": 140,
        "prompt": """
Write the bio paragraph for Emily Perkins, AIT, Project Designer / Job Captain at Collab Architecture.
Her project role: Job Captain for {rfp_title}.

3-4 sentences covering:
- Leads projects from concept to completion with precision and creativity
- Passion for designing educational and community spaces that blend functionality,
  sustainability, and aesthetic appeal
- Recent work: Town of Eaton Public Library, Weld County School District 6, faith-based clients
- Spaces centered on learning, connection, and shared purpose; strong technical knowledge;
  fosters collaborative and inclusive environments

Write in third person. Specific, no filler.
Return ONLY the bio paragraph.
""",
    },
    "bio_dorsey": {
        "label": "Team Bio — Kevin Dorsey",
        "target_contains": "Insert Bio",
        "max_tokens": 150,
        "prompt": """
Write the bio paragraph for Kevin Dorsey, Design Manager at Collab Architecture.
His project role: Technical Design Manager for {rfp_title}.

3-4 sentences covering:
- 30+ years of construction and design experience; started as a craftsman and superintendent
- Degrees from Aims Community College and Colorado State University — combines field knowledge
  with technical expertise
- Designed wide range of public facilities across Colorado: K-12 schools, higher ed buildings,
  recreation centers, community hubs
- Responsible for project planning, construction documents, job-site observation, regulatory coordination

Write in third person. Specific, no filler.
Return ONLY the bio paragraph.
""",
    },

    # ── PROJECT EXPERIENCE (Pages 18-21) ──────────────────────────────────────
    "project_desc_1": {
        "label": "Project Experience — Description 1",
        "target_contains": "Mustibus eum iditatio",
        "max_tokens": 280,
        "prompt": """
Write a 3-paragraph project description for a Collab Architecture portfolio entry.
This entry should demonstrate experience directly relevant to: {rfp_title}.

Para 1: Project overview — the client's challenge and what was designed.
Use a real-sounding Colorado public-sector project (municipality, county, or state agency).
Include approximate construction value and location (City, CO).

Para 2: Design approach — how Collab addressed technical complexity, active operations,
phasing, stakeholder input, and code compliance specific to this project type.

Para 3: Outcome and lasting impact — what the completed facility delivers for its users
and why the design decisions will hold up long-term.

Write in third person past tense. Specific. Bold 1-2 key facts.
Return ONLY the three paragraphs.
""",
    },
    "project_desc_2": {
        "label": "Project Experience — Description 2",
        "target_contains": "Bores esendemos debitin",
        "max_tokens": 200,
        "prompt": """
Write a 2-paragraph project description for a second Collab Architecture portfolio project.
Also relevant to: {rfp_title}, but a different Colorado municipality and building type than the first entry.

Para 1: Project overview — client, challenge, scope, location (different city/county than previous).
Para 2: Design solution, notable technical or community challenge overcome, and outcome.

Write in third person past tense. Specific. Bold 1 key fact.
Return ONLY the two paragraphs.
""",
    },

    # ── PROJECT APPROACH (Page 22) ────────────────────────────────────────────
    "project_approach_intro": {
        "label": "Project Approach — Intro",
        "target_contains": "XX anticipates completing",
        "max_tokens": 200,
        "prompt": """
Write 2 paragraphs introducing Collab Architecture's project approach for {rfp_title}
submitted to {client_name}.

Para 1: Describe the overall design and delivery philosophy Collab brings to this project —
comprehensive evaluation of existing conditions, targeted rehabilitation, code compliance,
and how design decisions will support long-term operational performance.

Para 2: Describe the phased design process Collab will follow — from pre-design through
construction documents and administration. Note that Collab will refine the schedule
upon contract award in close coordination with {client_name}.

Replace any 'XX' placeholders with 'Collab'. Specific, no filler.
Return ONLY the two paragraphs.
""",
    },

    # ── SCHEDULE (Page 24) ────────────────────────────────────────────────────
    "schedule_project_name": {
        "label": "Project Schedule — Project name bar",
        "target_contains": "INSERT RFP TITLE OR PROJECT NAME",
        "max_tokens": 20,
        "prompt": (
            "Return a short 3-5 word project name for the schedule header bar for: {rfp_title}. "
            "All caps. Return ONLY the project name."
        ),
    },

    # ── EQUITY, DIVERSITY & INCLUSION (Page 30) ───────────────────────────────
    "edi_narrative": {
        "label": "EDI — Narrative",
        "target_contains": "Insert EDI",
        "max_tokens": 200,
        "prompt": """
Write the Equity, Diversity, and Inclusion narrative for Collab Architecture's RFP response.
Project: {rfp_title} for {client_name}.

2 paragraphs:
Para 1: How Collab embeds equity and inclusion into its design process — diverse stakeholder
engagement, accessible design, community-centered programming, and inclusive decision-making.

Para 2: Internal firm commitment — diverse hiring, mentorship (ACE Mentor), community board
service (Northern Colorado Unify, CASA of Larimer County), and how this internal culture
directly shapes better design outcomes for public clients.

Tone: genuine, specific, not performative.
Return ONLY the two paragraphs.
""",
    },

    # ── WORK LOCATION (Page 32) ───────────────────────────────────────────────
    "work_location_narrative": {
        "label": "Work Location — Narrative",
        "target_contains": "Are we close to the project site",
        "max_tokens": 120,
        "prompt": (
            "Write 3-4 sentences for the Work Location section of Collab Architecture's RFP response. "
            "Project: {rfp_title} for {client_name}. "
            "Cover: office location (Windsor, CO, 9217 Eastman Park Dr), proximity to project site, "
            "availability for on-site presence and rapid response, established Front Range project delivery. "
            "Tone: confident and practical. Return ONLY the sentences."
        ),
    },
}

# ── GENERATE ──────────────────────────────────────────────────────────────────

def generate_all(client, rfp_title, client_name, date, rfp_number):
    generated = {}
    vars = {
        "rfp_title":   rfp_title,
        "client_name": client_name,
        "date":        date,
        "rfp_number":  rfp_number,
    }

    print(f"\n🤖 Generating {len(SECTIONS)} sections...\n")

    for key, section in SECTIONS.items():
        print(f"  → {section['label']}...", end=" ", flush=True)
        prompt = section["prompt"].format(**vars).strip()

        msg = client.messages.create(
            model="claude-sonnet-4-6",   # sonnet for style fidelity; swap to haiku for speed
            max_tokens=section["max_tokens"],
            system=STYLE_GUIDE,
            messages=[{"role": "user", "content": prompt}]
        )
        text = msg.content[0].text.strip()
        generated[key] = {
            "label":            section["label"],
            "target_contains":  section["target_contains"],
            "generated_text":   text,
        }
        print("✓")

    return generated

# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rfp",        default="ADAL EMEDS and EOD - Building 814")
    parser.add_argument("--client",     default="State of Colorado Department of Military and Veterans Affairs")
    parser.add_argument("--date",       default=datetime.today().strftime("%B %d, %Y"))
    parser.add_argument("--rfp_number", default="RFQ1 2026-0027")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ Set ANTHROPIC_API_KEY first.")
        return

    client = anthropic.Anthropic(api_key=api_key)

    print(f"\n{'='*60}")
    print("  COLLAB PIPELINE — STEP 2: GENERATE CONTENT")
    print(f"{'='*60}")
    print(f"  RFP    : {args.rfp}")
    print(f"  Client : {args.client}")
    print(f"  Date   : {args.date}")
    print(f"  Model  : claude-sonnet-4-6 (style-guided)")

    generated = generate_all(client, args.rfp, args.client, args.date, args.rfp_number)

    output = {
        "rfp_title":    args.rfp,
        "client_name":  args.client,
        "date":         args.date,
        "rfp_number":   args.rfp_number,
        "generated_at": datetime.now().isoformat(),
        "sections":     generated,
    }

    with open("generated_content.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n✅ Saved: generated_content.json")
    print(f"\n   Preview — Cover Letter Body:\n")
    print("   " + generated["cover_letter_body"]["generated_text"][:400].replace("\n", "\n   ") + "...")

if __name__ == "__main__":
    main()
