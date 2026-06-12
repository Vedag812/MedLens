# MedLens -- AI-Powered Medication Safety Platform

A real-time medication identification and drug interaction analysis platform that combines **Computer Vision**, **NLP-based Named Entity Recognition**, and **Graph Analytics** to help patients and healthcare workers make safer medication decisions.

> Built for medication safety in India, where polypharmacy and OTC drug access make accidental drug interactions a serious public health concern.

## Key Features

### Computer Vision Pipeline
- **Multi-strategy OCR preprocessing** using OpenCV (CLAHE, adaptive thresholding, bilateral denoising, auto-rotation)
- **EasyOCR** with English + Hindi language support for Indian medicine strips
- **Auto-Scan mode** with continuous frame capture and real-time text detection feedback
- **Mobile camera integration** over HTTPS for on-the-go scanning

### ML/NLP Pipeline
- **Named Entity Recognition** for drug name extraction from noisy OCR output
- **OCR error correction** using domain-specific lookup dictionaries (common misreads like `0` to `O`, `1` to `l`)
- **Multi-signal scoring** combining fuzzy string matching (RapidFuzz), positional signals, dosage proximity weighting, and n-gram TF-IDF
- **Confidence-ranked results** with explainable match breakdowns

### Knowledge Graph Analytics
- **Drug interaction network** built with NetworkX (65 drugs, 55+ verified interactions)
- **Centrality analysis**: degree, betweenness, eigenvector, and closeness centrality
- **Community detection** via greedy modularity optimization
- **Danger ranking** identifying the highest-risk drugs in the database
- **Per-user vault subgraph analysis** showing personalized interaction density

### Personalized Risk Scoring
- **Feature-engineered risk model** incorporating:
  - Base interaction severity (weighted by CRITICAL/SERIOUS/MODERATE/MINOR)
  - Polypharmacy multiplier (non-linear scaling for 3+ concurrent medications)
  - Age-group adjustment (child, adult, elderly)
  - Pre-existing condition modifiers (liver disease, kidney disease, heart disease, diabetes, pregnancy)
  - Interaction density factor
- **Explainable output** with factor-by-factor breakdown

## Architecture

```
                    +-------------------+
                    |   Mobile / Web    |
                    |   Browser (HTTPS) |
                    +--------+----------+
                             |
                    +--------v----------+
                    |    FastAPI Server  |
                    |    (Uvicorn)       |
                    +--------+----------+
                             |
            +----------------+----------------+
            |                |                |
   +--------v------+  +-----v-------+  +-----v--------+
   | Image Pipeline |  | NER Pipeline|  | Graph Engine |
   | (OpenCV +      |  | (RapidFuzz +|  | (NetworkX)   |
   |  EasyOCR)      |  |  TF-IDF)   |  |              |
   +--------+------+  +-----+-------+  +-----+--------+
            |                |                |
            +----------------+----------------+
                             |
                    +--------v----------+
                    |   Drug Database   |
                    |   (65 drugs,      |
                    |    55 interactions)|
                    +-------------------+
```

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **API Server** | FastAPI + Uvicorn | Async REST API with auto-docs |
| **OCR Engine** | EasyOCR (PyTorch) | Multilingual text extraction (EN + HI) |
| **Image Processing** | OpenCV, Pillow | 4-strategy preprocessing pipeline |
| **NLP/Matching** | RapidFuzz, scikit-learn | Fuzzy matching + TF-IDF scoring |
| **Graph Analytics** | NetworkX | Centrality, community detection, subgraph analysis |
| **Frontend** | Vanilla HTML/CSS/JS | PWA-ready dark UI with Canvas graph visualization |
| **Drug Data** | Curated JSON | 65 Indian medicines with brand names, interactions, dosage |

## Quick Start

```bash
# Clone the repository
git clone https://github.com/Vedag812/MedLens.git
cd MedLens

# Install dependencies
pip install -r requirements.txt

# Run the server
uvicorn backend.main:app --reload --port 8000

# Open in browser
# http://localhost:8000
```

### Mobile Testing (Phone Camera)

```bash
# Generate SSL certificate (required for camera access on mobile)
python generate_cert.py

# Start with HTTPS (accessible from phone on same WiFi)
uvicorn backend.main:app --host 0.0.0.0 --port 8000 \
  --ssl-keyfile certs/key.pem --ssl-certfile certs/cert.pem

# Open on phone: https://<your-local-ip>:8000
# Accept the self-signed certificate warning
```

## Project Structure

```
MedLens/
├── backend/
│   ├── main.py                 # FastAPI app, API endpoints, OCR integration
│   ├── drug_database.py        # Drug data loader, interaction queries
│   ├── drug_matcher.py         # RapidFuzz fuzzy matching engine
│   ├── ml_pipeline.py          # NER extraction, risk scoring model
│   ├── knowledge_graph.py      # NetworkX graph analytics
│   └── image_preprocessing.py  # OpenCV multi-strategy preprocessing
├── frontend/
│   ├── index.html              # Single-page app (4 tabs)
│   ├── styles.css              # Dark medical-grade UI
│   └── app.js                  # Camera, auto-scan, graph viz, vault
├── data/
│   └── drugs.json              # 65 drugs, 55 interactions, brand names
├── tests/
│   └── test_drug_matcher.py    # Unit tests for matching engine
├── generate_cert.py            # SSL cert generator for mobile testing
└── requirements.txt
```

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Service health check |
| `/api/drugs` | GET | List all 65 drugs with metadata |
| `/api/drug/{key}` | GET | Full drug info (dosage, sides, warnings) |
| `/api/scan/image` | POST | Upload image for OCR + NER drug extraction |
| `/api/scan/text` | POST | Text search with fuzzy + NER matching |
| `/api/interactions/check` | POST | Check one drug against vault |
| `/api/interactions/matrix` | POST | All pairwise interactions in vault |
| `/api/risk/score` | POST | Personalized risk score with explainable factors |
| `/api/analytics/graph` | GET | Full knowledge graph (nodes, edges, stats) |
| `/api/analytics/vault-graph` | POST | Vault-specific subgraph analysis |
| `/api/analytics/stats` | GET | Network metrics and danger ranking |

## Drug Database Coverage

The database includes **65 commonly used Indian medicines** across categories:

- **Analgesics**: Paracetamol, Ibuprofen, Diclofenac, Aceclofenac, Etoricoxib, Tramadol
- **Antibiotics**: Amoxicillin, Azithromycin, Ciprofloxacin, Cefixime, Doxycycline, Levofloxacin, Metronidazole, Norfloxacin
- **Antidiabetics**: Metformin, Glimepiride, Sitagliptin, Pioglitazone, Dapagliflozin, Insulin Glargine
- **Cardiac**: Amlodipine, Atorvastatin, Losartan, Telmisartan, Metoprolol, Carvedilol, Warfarin, Clopidogrel
- **Psychiatric**: Fluoxetine, Sertraline, Escitalopram, Amitriptyline, Alprazolam, Clonazepam
- **GI**: Omeprazole, Pantoprazole, Rabeprazole, Domperidone, Ondansetron
- **Respiratory**: Salbutamol, Montelukast, Deriphylline
- **And more**: Levothyroxine, Prednisolone, Gabapentin, Phenytoin, Sodium Valproate, supplements

## Contributors

- [Vedant Agarwal](https://github.com/Vedag812)
- [Tanishka Poddar](https://github.com/Tan1725)

## License

MIT
