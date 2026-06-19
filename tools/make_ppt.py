"""
Generate TechnologyAgent_Showcase.pptx with simple diagrams.
Run in the project virtualenv after installing dependencies:

python -m pip install python-pptx Pillow
python tools/make_ppt.py

The script creates two PNG diagrams and a PPTX in the current working directory.
"""

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_PARAGRAPH_ALIGNMENT
from PIL import Image, ImageDraw, ImageFont
import os

OUT_PPT = "TechnologyAgent_Showcase.pptx"
IMG1 = "system_architecture.png"
IMG2 = "ingestion_flow.png"
IMG3 = "appendix_flow.png"

slides = [
    {
        "title": "Lam Research TechnologyAgent",
        "bullets": [
            "Project: Lam Research TechnologyAgent",
            "Team members: [List team names]",
            "Faculty advisor: Michele Samorani",
            "Sponsor: Lam Research",
        ],
        "notes": "Hello — we’re presenting Lam Research TechnologyAgent, a prototype platform to accelerate identification of academic partners. I’m [name] and our team includes [names]. Michele Samorani advised this work and Lam Research sponsored it. Over the next ten minutes I’ll outline the scope, approach, architecture, results, and business impact.",
    },
    {
        "title": "Project Scope",
        "bullets": [
            "Make partnership discovery fast, consistent, and scalable",
            "Target users: technology scouts and research partnerships teams",
            "Manual search is slow, subjective, and misses emerging researchers",
        ],
        "notes": "Lam needed a repeatable way to find academic partners aligned to future technology directions. Analysts today rely on manual Google Scholar searches which are slow and subjective. Our aim: surface relevant researchers quickly while preserving signals for impact and recency.",
    },
    {
        "title": "Key Use Cases",
        "bullets": [
            "Find candidates for sponsored research and collaborations",
            "Identify rising researchers and cross-disciplinary matches",
            "Produce concise summaries for outreach and evaluation",
        ],
        "notes": "We focused on three practical use cases: building candidate shortlists for sponsored projects, discovering rising talent and cross-disciplinary fits, and generating distilled summaries to speed outreach.",
    },
    {
        "title": "Work Steps / Analysis",
        "bullets": [
            "Requirements: stakeholder interviews and success criteria",
            "Data-source evaluation: selected OpenAlex for coverage",
            "Pipeline design: ingestion, identity resolution, KB construction",
        ],
        "notes": "Our approach began with requirements and stakeholder interviews, followed by data-source evaluation. We chose OpenAlex for breadth. We designed a pipeline to ingest metadata, resolve identities, and create a normalized researcher knowledge base.",
    },
    {
        "title": "Ingestion & Retrieval Flow",
        "bullets": [
            "Ingestion → normalization → identity resolution → embeddings → index",
            "Semantic retrieval + structured metadata boosting",
            "Ranking and AI summarization produce actionable lists",
        ],
        "notes": "This flowchart shows how OpenAlex records are fetched, cleaned, and mapped to canonical researcher profiles. We generate embeddings for semantic retrieval, index them in Pinecone, then apply structured filters and ranking to produce actionable candidate lists.",
        "image": IMG2,
    },
    {
        "title": "System Architecture",
        "bullets": [
            "OpenAlex ingestion, Researcher KB, Embedding service, Pinecone",
            "Backend services for ranking, AI insights, and auth",
            "Frontend for search, saved lists, and exports; deployed on GCP",
        ],
        "notes": "The architecture is modular: ingestion feeds a researcher KB and embedding pipeline; embeddings live in Pinecone; backend services handle ranking, APIs, and AI summarization; the frontend lets users search, save lists, and export. We deploy on Google Cloud for scale and security.",
        "image": IMG1,
    },
    {
        "title": "Researcher Ranking & Retrieval",
        "bullets": [
            "Q: query relevance via semantic similarity and topical match",
            "R: impact/recency metric — citations, recent activity, venue strength",
            "Hybrid blend (tunable) surfaces relevant, credible researchers",
        ],
        "notes": "Our ranking merges Q (how well the researcher’s work matches the query) and R (impact and momentum). This hybrid gives results that are topically relevant and credible. We tune weights per use case so the product surfaces either exploratory or conservative matches.",
    },
    {
        "title": "Key Deliverables",
        "bullets": [
            "Researcher discovery platform with search, filters, save/export",
            "Semantic search backed by Pinecone vector DB",
            "Ranking engine exposing Q/R tuning and AI summaries",
        ],
        "notes": "The deliverables include a searchable discovery UI, the semantic retrieval backend, a hybrid ranking engine with tunable parameters, and AI summaries that save analyst time and jumpstart outreach.",
    },
    {
        "title": "Benefits to Lam Research",
        "bullets": [
            "Faster identification of academic experts",
            "Improved discovery of emerging and cross-disciplinary researchers",
            "Reduced manual research effort; better strategic scouting",
        ],
        "notes": "For Lam Research this means faster partner identification, discovery of promising emerging researchers, reduced analyst time, and stronger, more strategic partnership pipelines — enabling quicker decisions on sponsored research and collaborations.",
    },
    {
        "title": "Results, Next Steps & Close",
        "bullets": [
            "Current: ranked lists, saved candidates, AI summaries, APIs",
            "Future: add grants/patents, collaboration graphs, automated alerts",
            "Closing: TechnologyAgent enables scalable, data-driven partnerships",
        ],
        "notes": "Today we can generate ranked candidate lists with summaries and saved shortlists. Next steps include adding additional data sources, improving ranking with funding and network signals, and automating alerts for emerging researchers.",
    },
]

# Simple diagram drawing using Pillow


def draw_system_architecture(path):
    w, h = 1200, 700
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    # boxes
    boxes = [
        ((50, 80, 350, 160), "OpenAlex\nIngestion"),
        ((400, 60, 760, 160), "Normalize\n& KB"),
        ((820, 60, 1120, 160), "Embedding Service\n+ Pinecone"),
        ((400, 240, 760, 320), "Backend: API & Ranking"),
        ((400, 380, 760, 460), "AI Insights\n& Auth"),
        ((50, 500, 350, 600), "Frontend\n(UI)"),
    ]
    for b, text in boxes:
        d.rectangle(b, outline="black", width=2)
        # centered text
        x0, y0, x1, y1 = b
        tw = x1 - x0
        th = y1 - y0
        lines = text.split("\n")
        # simple centering
        y_text = y0 + 10
        for line in lines:
            d.text((x0 + 10, y_text), line, fill="black")
            y_text += 18
    # arrows
    d.line((350, 120, 400, 120), fill="black", width=2)
    d.line((760, 120, 820, 120), fill="black", width=2)
    d.line((580, 160, 580, 240), fill="black", width=2)
    d.line((580, 320, 580, 380), fill="black", width=2)
    d.line((200, 460, 200, 500), fill="black", width=2)
    img.save(path)


def draw_ingestion_flow(path):
    w, h = 1200, 700
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    steps = [
        "Topic Query",
        "Fetch OpenAlex",
        "Normalize & Clean",
        "Identity Resolution",
        "Embeddings",
        "Index (Pinecone)",
        "Semantic Retrieval",
        "Filters & Boosts",
        "Ranking (Q+R)",
        "AI Summaries",
    ]
    x = 60
    y = 80
    for i, s in enumerate(steps):
        box = (x, y, x + 200, y + 60)
        d.rectangle(box, outline="black", width=2)
        d.text((x + 10, y + 20), s, fill="black")
        x += 220
        if (i + 1) % 4 == 0:
            x = 60
            y += 120
    img.save(path)


def draw_appendix_flow(path):
    w, h = 1200, 700
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    # boxes coordinates
    boxes = [
        ((460, 40, 740, 120), "User Query"),
        ((460, 150, 740, 230), "Local KB Search"),
        ((460, 270, 740, 330), "Results Found?"),
        ((200, 350, 440, 420), "Return Results"),
        ((480, 410, 760, 470), "Query OpenAlex"),
        ((480, 500, 760, 560), "Ingest & Normalize"),
        ((480, 600, 760, 660), "Update Researcher KB"),
        ((480, 700 - 60, 760, 760 - 60), "Return Results"),
    ]
    # draw boxes with soft colors
    for i, (b, text) in enumerate(boxes):
        fill = (208, 236, 255) if i in (0, 1, 2, 3, 7) else (223, 247, 230)
        d.rectangle(b, outline=(51, 51, 51), fill=fill, width=2)
        x0, y0, x1, y1 = b
        # center text
        d.text((x0 + 10, y0 + 10), text, fill=(0, 0, 0))
    # arrows
    d.line((600, 120, 600, 150), fill=(51, 51, 51), width=2)
    d.line((600, 230, 600, 270), fill=(51, 51, 51), width=2)
    # branching arrows
    d.line((460, 300, 440, 360), fill=(51, 51, 51), width=2)
    d.line((740, 300, 760, 360), fill=(51, 51, 51), width=2)
    # from query openalex down
    d.line((620, 470, 620, 500), fill=(51, 51, 51), width=2)
    d.line((620, 560, 620, 600), fill=(51, 51, 51), width=2)
    d.line((620, 660, 620, 700 - 60), fill=(51, 51, 51), width=2)
    img.save(path)


def make_ppt():
    # create images
    draw_system_architecture(IMG1)
    draw_ingestion_flow(IMG2)
    draw_appendix_flow(IMG3)

    prs = Presentation()
    for s in slides:
        layout = prs.slide_layouts[1]
        slide = prs.slides.add_slide(layout)
        slide.shapes.title.text = s["title"]
        body = slide.placeholders[1].text_frame
        body.clear()
        for i, b in enumerate(s["bullets"]):
            if i == 0:
                body.text = b
            else:
                p = body.add_paragraph()
                p.text = b
                p.level = 1
        if s.get("image"):
            try:
                slide.shapes.add_picture(
                    s["image"], Inches(5.8), Inches(1.1), width=Inches(3.5)
                )
            except Exception:
                pass
        # notes
        notes = slide.notes_slide.notes_text_frame
        notes.text = s["notes"]

    prs.save(OUT_PPT)
    print("Saved", OUT_PPT)


if __name__ == "__main__":
    try:
        make_ppt()
    except Exception as e:
        print("Error creating PPTX:", e)
        print(
            "Ensure python-pptx and Pillow are installed: python -m pip install python-pptx Pillow"
        )
