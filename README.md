# 💊 MedLens — Medicine Interaction Checker

An intelligent medicine identification and drug interaction checking platform powered by OCR, ML-based Named Entity Recognition, and Knowledge Graph analytics.

## Features

- **Image-based Drug Scanning** — Upload medicine packaging images and extract drug names using EasyOCR with multi-strategy preprocessing (adaptive thresholding, auto-rotation, contrast enhancement)
- **Text-based Drug Search** — Type medicine names for instant fuzzy matching across 100+ drugs
- **Drug Interaction Detection** — Check for critical, serious, and moderate interactions between medications
- **Knowledge Graph Analytics** — Visualize drug interaction networks with centrality analysis, community detection, and danger ranking
- **Personalized Risk Scoring** — ML-inspired risk engine factoring patient age, conditions, and poly-pharmacy count
- **Interactive Interaction Matrix** — See all pairwise interactions across your medication vault

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Python, FastAPI, Uvicorn |
| **OCR** | EasyOCR with custom preprocessing pipeline |
| **ML/NLP** | Scikit-learn, fuzzy matching, NER extraction |
| **Graph Analytics** | NetworkX (centrality, community detection) |
| **Frontend** | HTML, CSS, JavaScript |
| **Data** | JSON drug database (100+ drugs, interactions, categories) |

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
uvicorn backend.main:app --reload --port 8000

# Open browser
# http://localhost:8000
```

## Project Structure

```
MedLens/
├── backend/
│   ├── main.py              # FastAPI application & endpoints
│   ├── drug_database.py     # Drug data loading & interaction queries
│   ├── drug_matcher.py      # Fuzzy matching engine
│   ├── ml_pipeline.py       # ML entity extraction & risk scoring
│   ├── knowledge_graph.py   # NetworkX graph analytics
│   └── image_preprocessing.py  # OCR preprocessing strategies
├── frontend/
│   ├── index.html           # Main UI
│   ├── styles.css           # Styling
│   └── app.js               # Frontend logic
├── data/
│   └── drugs.json           # Drug database
├── tests/
│   └── test_drug_matcher.py # Unit tests
└── requirements.txt
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/drugs` | GET | List all drugs |
| `/api/drug/{key}` | GET | Get drug details |
| `/api/scan/image` | POST | OCR scan medicine image |
| `/api/scan/text` | POST | Text-based drug search |
| `/api/interactions/check` | POST | Check drug interactions |
| `/api/interactions/matrix` | POST | Full interaction matrix |
| `/api/risk/score` | POST | Personalized risk score |
| `/api/analytics/graph` | GET | Full knowledge graph |
| `/api/analytics/stats` | GET | Graph statistics |

## Contributors

- [Vedant Agarwal](https://github.com/Vedag812)
- [Tanishka Poddar](https://github.com/Tan1725)

## License

MIT
