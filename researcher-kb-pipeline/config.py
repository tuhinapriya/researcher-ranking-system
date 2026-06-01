"""
Configuration for the Researcher Knowledge Base Pipeline.
Edit the constants below to change the field/concept, pagination limits, etc.
"""

import os

# ============================================================
# API Endpoints
# ============================================================


OPENALEX_BASE = "https://api.openalex.org"
S2_BASE = "https://api.semanticscholar.org/graph/v1"


# ============================================================
# User-Agent  (required by OpenAlex polite pool for faster limits)
# Replace with your actual email to get ~10 req/s instead of ~1 req/s
# ============================================================


CONTACT_EMAIL = os.environ.get("OPENALEX_CONTACT_EMAIL", "your_email@example.com")
# ^ Set OPENALEX_CONTACT_EMAIL to a real address to use OpenAlex polite pool
#   (~10 req/s instead of ~1 req/s for anonymous requests).


HEADERS = {"User-Agent": f"researcher-kb-pipeline/0.1 (contact: {CONTACT_EMAIL})"}


# ============================================================
# Retrieval Target Configuration
# ============================================================
# Add or remove entries to query multiple fields in one pipeline run.
# Each dict needs an "id" and a "label".
#
# Preferred IDs (Topic IDs):
#   Quantum Computing Topic  : T10682
#   Computer Vision Topic    : T10017
#
# Legacy IDs (OpenAlex concept IDs) are still supported by Stage 1:
#   Artificial Intelligence  : C154945302
#   Semiconductors           : C205649164
#   Machine Learning         : C119857082
#
# NOTE: Variable name `CONCEPTS` is kept for backward compatibility with
# existing stages, but entries may contain either topic IDs (preferred)
# or legacy concept IDs.


CONCEPTS = [
    {"id": "T10472", "label": "Semiconductor materials and devices"},
    {"id": "T10022", "label": "Semiconductor Quantum Structures and Devices"},
    {"id": "T10099", "label": "GaN-based semiconductor devices and materials"},
    {"id": "T10590", "label": "Chalcogenide Semiconductor Thin Films"},
    {"id": "T11853", "label": "Semiconductor materials and interfaces"},
    {"id": "T11429", "label": "Semiconductor Lasers and Optical Devices"},
    {"id": "T10361", "label": "Silicon Carbide Semiconductor Technologies"},
    {"id": "T11637", "label": "Advanced Semiconductor Detectors and Materials"},
    {
        "id": "T10558",
        "label": "Advancements in Semiconductor Devices and Circuit Design",
    },
    {"id": "T14117", "label": "Integrated Circuits and Semiconductor Failure Analysis"},
    {"id": "T10078", "label": "Advanced Photocatalysis Techniques"},
    {"id": "T10247", "label": "Perovskite Materials and Applications"},
    {"id": "T10090", "label": "ZnO doping and properties"},
    {"id": "T10275", "label": "2D Materials and Applications"},
    {"id": "T10461", "label": "Gas Sensing Nanomaterials and Sensors"},
    {"id": "T10382", "label": "Quantum and electron transport phenomena"},
    {"id": "T10623", "label": "Thin-Film Transistor Technologies"},
    {"id": "T11272", "label": "Nanowire Synthesis and Applications"},
    {"id": "T10781", "label": "Plasma Diagnostics and Applications"},
    {"id": "T13889", "label": "Advanced Materials and Semiconductor Technologies"},
    {"id": "T12111", "label": "Industrial Vision Systems and Defect Detection"},
    {"id": "T12529", "label": "Ga2O3 and related materials"},
    {"id": "T11216", "label": "Radiation Detection and Scintillator Technologies"},
    {"id": "T12579", "label": "Muon and positron interactions and applications"},
    {"id": "T12612", "label": "Strong Light-Matter Interactions"},
    {"id": "T12611", "label": "Neural Networks and Reservoir Computing"},
    {"id": "T12309", "label": "solar cell performance optimization"},
    {"id": "T13093", "label": "Electric Power Systems and Control"},
    {"id": "T11920", "label": "Pulsed Power Technology Applications"},
    {"id": "T10024", "label": "TiO2 Photocatalysis and Solar Cells"},
    {"id": "T10321", "label": "Quantum Dots Synthesis And Properties"},
    {
        "id": "T14363",
        "label": "Optical properties and cooling technologies in crystalline materials",
    },
    {"id": "T14158", "label": "Optical Systems and Laser Technology"},
    {
        "id": "T14327",
        "label": "Advanced Energy Technologies and Civil Engineering Innovations",
    },
    {"id": "T14311", "label": "Electrical and Electromagnetic Research"},
    {
        "id": "T10607",
        "label": "Magnetic and transport properties of perovskites and related materials",
    },
    {"id": "T14504", "label": "Diverse Academic Research Analysis"},
    {"id": "T13757", "label": "Graphic Design and Typography"},
    {"id": "T10299", "label": "Photonic and Optical Devices"},
    {"id": "T10666", "label": "Photonic Crystals and Applications"},
    {"id": "T11575", "label": "Nonlinear Photonic Systems"},
    {"id": "T10846", "label": "Photonic Crystal and Fiber Optics"},
    {"id": "T10767", "label": "Advanced Photonic Communication Systems"},
    {"id": "T10988", "label": "Advanced Fiber Laser Technologies"},
    {"id": "T11050", "label": "Photorefractive and Nonlinear Optics"},
    {"id": "T10657", "label": "Topological Materials and Phenomena"},
    {"id": "T10245", "label": "Metamaterials and Metasurfaces Applications"},
    {"id": "T10205", "label": "Advanced Fiber Optic Sensors"},
    {"id": "T10478", "label": "Diamond and Carbon-based Materials Research"},
    {"id": "T11315", "label": "Phase-change materials and chalcogenides"},
    {"id": "T11414", "label": "Quantum optics and atomic interactions"},
    {"id": "T11262", "label": "Quantum Mechanics and Non-Hermitian Physics"},
    {"id": "T12510", "label": "Magneto-Optical Properties and Applications"},
    {"id": "T11788", "label": "Nonlinear Optical Materials Studies"},
    {"id": "T11723", "label": "Optical Coatings and Gratings"},
    {"id": "T12442", "label": "Thermal Radiation and Cooling Technologies"},
    {"id": "T10732", "label": "Laser Material Processing Techniques"},
    {"id": "T11797", "label": "graph theory and CDMA systems"},
    {"id": "T11887", "label": "Quasicrystal Structures and Properties"},
    {"id": "T12466", "label": "Near-Field Optical Microscopy"},
    {"id": "T11367", "label": "Particle accelerators and beam dynamics"},
    {"id": "T12699", "label": "Electromagnetic Launch and Propulsion Technology"},
    {"id": "T10642", "label": "Plasma Applications and Diagnostics"},
    {"id": "T10384", "label": "Laser-Plasma Interactions and Diagnostics"},
    {"id": "T10346", "label": "Magnetic confinement fusion research"},
    {
        "id": "T12122",
        "label": "Physical Unclonable Functions (PUFs) and Hardware Security",
    },
    {"id": "T12808", "label": "Ferroelectric and Negative Capacitance Devices"},
    {"id": "T10107", "label": "Ferroelectric and Piezoelectric Materials"},
    {"id": "T10886", "label": "Multiferroics and related materials"},
    {"id": "T11878", "label": "Solid-state spectroscopy and crystallography"},
    {"id": "T11758", "label": "Organic and Molecular Conductors Research"},
    {"id": "T11608", "label": "Dielectric materials and actuators"},
    {"id": "T12588", "label": "Electronic and Structural Properties of Oxides"},
    {"id": "T12557", "label": "Inorganic Chemistry and Materials"},
    {"id": "T12155", "label": "Microwave Dielectric Ceramics Synthesis"},
    {"id": "T12875", "label": "Thermal Expansion and Ionic Conductivity"},
    {"id": "T13249", "label": "Dielectric properties of ceramics"},
    {"id": "T10083", "label": "Graphene research and applications"},
    {"id": "T11200", "label": "Electrodeposition and Electroless Coatings"},
    {"id": "T12340", "label": "Anodic Oxide Films and Nanostructures"},
    {"id": "T12106", "label": "Surface Treatment and Residual Stress"},
    {"id": "T13470", "label": "Surface Treatment and Coatings"},
    {"id": "T12161", "label": "Plant Surface Properties and Treatments"},
    {"id": "T10016", "label": "Adsorption and biosorption for pollutant removal"},
    {"id": "T10513", "label": "Natural Fiber Reinforced Composites"},
    {"id": "T11401", "label": "Minerals Flotation and Separation Techniques"},
    {"id": "T12078", "label": "Environmental remediation with nanomaterials"},
    {"id": "T14479", "label": "Freezing and Crystallization Processes"},
    {"id": "T12064", "label": "Intraperitoneal and Appendiceal Malignancies"},
    {"id": "T10938", "label": "Phase Change Materials Research"},
    {"id": "T14382", "label": "Electrophoretic Deposition in Materials Science"},
    {"id": "T10281", "label": "Advanced Battery Materials and Technologies"},
    {"id": "T10783", "label": "Additive Manufacturing and 3D Printing Technologies"},
    {"id": "T10965", "label": "Geological formations and processes"},
    {"id": "T11651", "label": "Inhalation and Respiratory Drug Delivery"},
    {"id": "T11279", "label": "Lanthanide and Transition Metal Complexes"},
    {"id": "T12091", "label": "Peatlands and Wetlands Ecology"},
    {"id": "T10626", "label": "High-Temperature Coating Behaviors"},
    {"id": "T12350", "label": "Particle Dynamics in Fluid Flows"},
    {"id": "T11630", "label": "Petroleum Processing and Analysis"},
    {"id": "T10488", "label": "Nanocomposite Films for Food Packaging"},
    {"id": "T10460", "label": "Electronic Packaging and Soldering Technologies"},
    {"id": "T14055", "label": "Consumer Packaging Perceptions and Trends"},
    {"id": "T10333", "label": "Meat and Animal Product Quality"},
    {"id": "T10473", "label": "Postharvest Quality and Shelf Life Management"},
    {"id": "T13748", "label": "Advanced Statistical Modeling Techniques"},
    {"id": "T12971", "label": "Material Properties and Processing"},
    {"id": "T12583", "label": "Food Waste Reduction and Sustainability"},
    {"id": "T11527", "label": "3D IC and TSV technologies"},
    {"id": "T13067", "label": "Geological Modeling and Analysis"},
    {"id": "T12698", "label": "3D Modeling in Geospatial Applications"},
    {"id": "T10191", "label": "Robotics and Sensor-Based Localization"},
    {"id": "T10586", "label": "Robotic Path Planning Algorithms"},
    {"id": "T10571", "label": "Robotic Mechanisms and Dynamics"},
    {"id": "T10653", "label": "Robot Manipulation and Learning"},
    {"id": "T10462", "label": "Reinforcement Learning in Robotics"},
    {"id": "T11486", "label": "Micro and Nano Robotics"},
    {"id": "T10879", "label": "Robotic Locomotion and Control"},
    {"id": "T10868", "label": "Soft Robotics and Applications"},
    {"id": "T11023", "label": "Prosthetics and Rehabilitation Robotics"},
    {"id": "T12784", "label": "Modular Robots and Swarm Intelligence"},
    {"id": "T10709", "label": "Social Robot Interaction and HRI"},
    {"id": "T13382", "label": "Robotics and Automated Systems"},
    {"id": "T11615", "label": "Control and Dynamics of Mobile Robots"},
    {"id": "T14335", "label": "Educational Robotics and Engineering"},
    {"id": "T10040", "label": "Adaptive Control of Nonlinear Systems"},
    {"id": "T13715", "label": "Power Line Inspection Robots"},
    {"id": "T10510", "label": "Stroke Rehabilitation and Recovery"},
    {"id": "T10249", "label": "Distributed Control Multi-Agent Systems"},
    {"id": "T13287", "label": "Robotic Process Automation Applications"},
    {"id": "T12128", "label": "AI in Service Interactions"},
    {"id": "T10668", "label": "Endometrial and Cervical Cancer Treatments"},
    {"id": "T10776", "label": "Spinal Fractures and Fixation Techniques"},
    {"id": "T10616", "label": "Smart Agriculture and AI"},
    {"id": "T11174", "label": "Pediatric Urology and Nephrology Studies"},
    {"id": "T12288", "label": "Optimization and Search Problems"},
    {"id": "T11737", "label": "Advanced Materials and Mechanics"},
    {"id": "T10906", "label": "AI-based Problem Solving and Planning"},
    {"id": "T11814", "label": "Advanced Manufacturing and Logistics Optimization"},
    {"id": "T10916", "label": "Surgical Simulation and Training"},
    {"id": "T10533", "label": "Teaching and Learning Programming"},
    {"id": "T11170", "label": "Biomimetic flight and propulsion mechanisms"},
    {"id": "T11749", "label": "Iterative Learning Control Systems"},
    {"id": "T11728", "label": "Thyroid and Parathyroid Surgery"},
    {"id": "T11687", "label": "Teleoperation and Haptic Systems"},
    {"id": "T11701", "label": "Space Satellite Systems and Control"},
    {"id": "T14163", "label": "Astronomical Observations and Instrumentation"},
    {"id": "T12321", "label": "Insect Pheromone Research and Control"},
    {"id": "T12053", "label": "Minimally Invasive Surgical Techniques"},
    {"id": "T13717", "label": "Advanced Algorithms and Applications"},
    {"id": "T12782", "label": "Assembly Line Balancing Optimization"},
    {"id": "T12634", "label": "Ureteral procedures and complications"},
    {"id": "T13312", "label": "Mechanical and Thermal Properties Analysis"},
    {"id": "T12794", "label": "Adaptive Dynamic Programming Control"},
    {"id": "T12899", "label": "Engineering and Technology Innovations"},
    {"id": "T13364", "label": "Digitalization, Law, and Regulation"},
    {"id": "T13904", "label": "Artificial Intelligence Applications"},
    {"id": "T14381", "label": "Psychiatry, Mental Health, Neuroscience"},
    {"id": "T13827", "label": "Mechatronics Education and Applications"},
    {"id": "T13964", "label": "Educational Technology and Optimization"},
    {"id": "T13612", "label": "Advanced Scientific and Engineering Studies"},
    {"id": "T14359", "label": "Wetland Management and Conservation"},
    {"id": "T11192", "label": "Underwater Vehicles and Communication Systems"},
    {"id": "T13713", "label": "Diverse Perspectives in Modern Studies"},
    {"id": "T13344", "label": "Industrial Automation and Control Systems"},
    {"id": "T11741", "label": "Flexible and Reconfigurable Manufacturing Systems"},
    {"id": "T11081", "label": "Advanced Control Systems Design"},
    {"id": "T14470", "label": "Advanced Data Processing Techniques"},
    {"id": "T10525", "label": "Human-Automation Interaction and Safety"},
    {"id": "T12190", "label": "Innovations in Concrete and Construction Materials"},
    {"id": "T12222", "label": "IoT-based Smart Home Systems"},
    {"id": "T14512", "label": "Technology and Human Factors in Education and Health"},
    {"id": "T12451", "label": "Smart Grid and Power Systems"},
    {"id": "T13681", "label": "Engineering and Information Technology"},
    {"id": "T10763", "label": "Digital Transformation in Industry"},
    {"id": "T13027", "label": "Applied Advanced Technologies"},
    {"id": "T14260", "label": "Impact of AI and Big Data on Business and Society"},
    {"id": "T10682", "label": "Quantum Computing Algorithms and Architecture"},
    {"id": "T10612", "label": "Magnetism in coordination complexes"},
    {"id": "T13126", "label": "Scientific Research and Discoveries"},
    {"id": "T13182", "label": "Quantum-Dot Cellular Automata"},
    {"id": "T10310", "label": "Corrosion Behavior and Inhibition"},
    # ── Broad CS / AI topics added 2026-06-01 ──────────────────────────────
    # Core AI/ML
    {"id": "T10089", "label": "Machine Learning"},
    {"id": "T10025", "label": "Deep Learning"},
    {"id": "T10017", "label": "Computer Vision"},
    {"id": "T10302", "label": "Natural Language Processing"},
    {"id": "T11823", "label": "Large Language Models"},
    {"id": "T10019", "label": "Generative Models and Generative AI"},
    {"id": "T10048", "label": "Reinforcement Learning"},
    {"id": "T11099", "label": "Explainable AI and Interpretable Machine Learning"},
    # Data
    {"id": "T10031", "label": "Data Science and Analytics"},
    {"id": "T10338", "label": "Data Mining"},
    {"id": "T10166", "label": "Knowledge Graphs and Semantic Web"},
    {"id": "T10267", "label": "Information Retrieval"},
    # Systems / Infrastructure
    {"id": "T11446", "label": "Cybersecurity and Network Security"},
    {"id": "T10186", "label": "Cloud Computing"},
    {"id": "T10065", "label": "Distributed Systems"},
    {"id": "T10128", "label": "Software Engineering"},
    {"id": "T10232", "label": "Internet of Things"},
    {"id": "T10058", "label": "Edge Computing and Federated Learning"},
    # Human / Health
    {"id": "T10312", "label": "Human Computer Interaction"},
    {"id": "T10146", "label": "Healthcare AI and Clinical Machine Learning"},
    {"id": "T10376", "label": "Biomedical Informatics"},
    # Autonomous systems (robotics already covered; this adds broader autonomy)
    {"id": "T10154", "label": "Autonomous Vehicles and Autonomous Systems"},
]

# ============================================================
# Pagination & Limits
# ============================================================


MAX_WORKS_PAGES = 10  # Unused for Stage 1 full cursor backfill
WORKS_PER_PAGE = 100  # Stage 1 full backfill default
MAX_COAUTHOR_WORKS_PAGES = (
    4  # Pages of recent works to fetch per author for co-author analysis
)
MAX_COAUTHORS_TO_CHECK = 50  # Max co-authors to profile per researcher


# ============================================================
# Rate Limiting (seconds between requests)
# ============================================================


OPENALEX_SLEEP = 0.11  # ~9 req/s with polite pool
S2_SLEEP = 1.1  # ~1 req/s without API key


# ============================================================
# Staleness Window (days)
# ============================================================
# Cached profiles older than this are re-fetched on the next run.


STALENESS_DAYS = 30


# ============================================================
# Mentee Classification Thresholds
# ============================================================


MENTEE_MAX_WORKS = 20  # works_count <= this => likely student/postdoc


# ============================================================
# Data Paths
# ============================================================


DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
INTERMEDIATE_DIR = os.path.join(DATA_DIR, "intermediate")


PAPERS_DIR = os.path.join(RAW_DIR, "papers")
FIELD_AUTHOR_MAP_FILE = os.path.join(INTERMEDIATE_DIR, "field_author_map.json")


def papers_file_for(concept_label):
    """Return the papers.jsonl path for a given concept label."""
    slug = concept_label.lower().replace(" ", "_")
    return os.path.join(PAPERS_DIR, f"papers_{slug}.jsonl")


PROFILES_DIR = os.path.join(RAW_DIR, "profiles")
COAUTHORS_DIR = os.path.join(RAW_DIR, "coauthors")
INSTITUTIONS_DIR = os.path.join(RAW_DIR, "institutions")


KNOWLEDGE_BASE_FILE = os.path.join(DATA_DIR, "knowledge_base.json")
SUMMARY_EXCEL_FILE = os.path.join(DATA_DIR, "knowledge_base_summary.xlsx")
SUMMARY_SCHEMA_FILE = os.path.join(DATA_DIR, "knowledge_base_summary_schema.json")


def ensure_dirs():
    """Create all output directories if they don't exist."""
    for d in [
        DATA_DIR,
        RAW_DIR,
        INTERMEDIATE_DIR,
        PAPERS_DIR,
        PROFILES_DIR,
        COAUTHORS_DIR,
        INSTITUTIONS_DIR,
    ]:
        os.makedirs(d, exist_ok=True)


# ============================================================
# Embedding / Vector DB / LLM Configuration
# ============================================================

# OpenAI (for embeddings) or other provider API key. If empty, embedding
# functions will raise until configured.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
# Embedding model to use (OpenAI example). Change to your model.
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-3-small")

# Pinecone configuration (optional). If not using Pinecone, leave unset.
PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY", "")
PINECONE_INDEX = os.environ.get("PINECONE_INDEX", "researcher-kb-index")
# ^ Actual deployed index name is "researcher-kb-index" (serverless, AWS us-east-1, dim=768).

# Batch sizes for embedding/upsert
EMBED_BATCH_SIZE = int(os.environ.get("EMBED_BATCH_SIZE", "64"))
PINECONE_UPSERT_BATCH = int(os.environ.get("PINECONE_UPSERT_BATCH", "100"))


# ============================================================
# Ranking / Search Configuration
# ============================================================

TOP_K_PINECONE = int(os.environ.get("TOP_K_PINECONE", "500"))
MIN_UNIQUE_RESEARCHERS = int(os.environ.get("MIN_UNIQUE_RESEARCHERS", "25"))
MAX_TOP_K_PINECONE = int(os.environ.get("MAX_TOP_K_PINECONE", "2000"))
TARGET_PAPERS_PER_RESEARCHER = float(
    os.environ.get("TARGET_PAPERS_PER_RESEARCHER", "2.0")
)
Q_MAX_PAPERS_PER_RESEARCHER = int(os.environ.get("Q_MAX_PAPERS_PER_RESEARCHER", "200"))
Q_WEIGHT = float(os.environ.get("Q_WEIGHT", "0.5"))
R_WEIGHT = float(os.environ.get("R_WEIGHT", "0.5"))
PARETO_EPSILON = float(os.environ.get("PARETO_EPSILON", "0.05"))
PARETO_REQUIRE_K = int(os.environ.get("PARETO_REQUIRE_K", "1"))

# Number of top paper similarity scores to average for Q
Q_TOP_PAPERS = int(os.environ.get("Q_TOP_PAPERS", "20"))
