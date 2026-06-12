"""
MedLens FastAPI Application
Main API server with drug scanning, interaction checking, knowledge graph analytics,
personalized risk scoring, and ML-based entity extraction.
"""

import io
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.drug_database import (
    get_drug_info, get_all_drug_keys, get_all_brand_names,
    find_interactions, get_interaction_matrix
)
from backend.drug_matcher import match_drug_name
from backend.ml_pipeline import DrugEntityExtractor, InteractionRiskScorer
from backend.knowledge_graph import (
    get_graph_statistics, build_interaction_graph,
    get_vault_subgraph_analysis, get_full_graph_data
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("medlens")

# Lazy-loaded OCR engine
_ocr_engine = None

def get_ocr():
    global _ocr_engine
    if _ocr_engine is None:
        try:
            import easyocr
            # Support English + Hindi for Indian medicine strips
            _ocr_engine = easyocr.Reader(["en", "hi"], gpu=False, verbose=False)
            logger.info("EasyOCR loaded (English + Hindi)")
        except Exception as e:
            logger.warning(f"EasyOCR failed to load: {e}")
            _ocr_engine = "fallback"
    return _ocr_engine

# Lazy-loaded ML components
_entity_extractor = None
_risk_scorer = None

def get_entity_extractor():
    global _entity_extractor
    if _entity_extractor is None:
        _entity_extractor = DrugEntityExtractor(
            drug_names=get_all_drug_keys(),
            brand_names=get_all_brand_names()
        )
    return _entity_extractor

def get_risk_scorer():
    global _risk_scorer
    if _risk_scorer is None:
        _risk_scorer = InteractionRiskScorer()
    return _risk_scorer


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("MedLens starting up...")
    keys = get_all_drug_keys()
    logger.info(f"Loaded {len(keys)} drugs")
    G = build_interaction_graph()
    logger.info(f"Knowledge graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    yield
    logger.info("MedLens shutting down...")

app = FastAPI(
    title="MedLens API",
    description="Medicine identification, interaction checking, and knowledge graph analytics",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic Models

class TextScanRequest(BaseModel):
    text: str

class InteractionRequest(BaseModel):
    drug_key: str
    vault_keys: list[str]

class MatrixRequest(BaseModel):
    vault_keys: list[str]

class RiskScoreRequest(BaseModel):
    vault_keys: list[str]
    age_group: str = "adult"
    conditions: list[str] = ["none"]


# ============ Core Endpoints ============

@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "drugs_loaded": len(get_all_drug_keys())}

@app.get("/api/drugs")
async def list_drugs():
    keys = get_all_drug_keys()
    drugs = []
    for key in keys:
        info = get_drug_info(key)
        if info:
            drugs.append({
                "drug_key": key,
                "generic_name": info["generic_name"],
                "brand_names": info["brand_names"],
                "category": info["category"],
            })
    return {"count": len(drugs), "drugs": drugs}

@app.get("/api/drug/{drug_key}")
async def get_drug(drug_key: str):
    info = get_drug_info(drug_key.lower())
    if not info:
        raise HTTPException(status_code=404, detail=f"Drug '{drug_key}' not found")
    return {"drug_key": drug_key.lower(), "drug_info": info}


# ============ Scanning Endpoints ============

def _run_ocr_on_image(img_array):
    """Run EasyOCR with multiple preprocessing strategies."""
    import numpy as np
    from backend.image_preprocessing import preprocess_for_ocr, auto_rotate

    ocr = get_ocr()
    if ocr == "fallback":
        return ""

    img_array = auto_rotate(img_array)
    preprocessed = preprocess_for_ocr(img_array)
    all_images = [img_array] + preprocessed

    best_text = ""
    best_count = 0

    for i, img in enumerate(all_images):
        try:
            results = ocr.readtext(
                img, detail=1, paragraph=False,
                min_size=10, text_threshold=0.4,
                low_text=0.3, link_threshold=0.3, width_ths=0.7,
            )
            if not results:
                continue

            lines = [text.strip() for (_, text, conf) in results if conf > 0.25 and len(text.strip()) >= 2]
            combined = " ".join(lines)

            if len(combined.split()) > best_count:
                best_count = len(combined.split())
                best_text = combined
        except Exception as e:
            logger.warning(f"OCR strategy {i} failed: {e}")

    return best_text


@app.post("/api/scan/image")
async def scan_image(file: UploadFile = File(...)):
    """Upload medicine image for OCR + ML entity extraction + drug matching."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    contents = await file.read()
    ocr = get_ocr()
    if ocr == "fallback":
        raise HTTPException(status_code=503, detail="OCR engine not available. Use text search.")

    try:
        import numpy as np
        from PIL import Image

        image = Image.open(io.BytesIO(contents)).convert("RGB")
        img_array = np.array(image)
        extracted_text = _run_ocr_on_image(img_array)
    except Exception as e:
        logger.error(f"OCR error: {e}")
        raise HTTPException(status_code=500, detail=f"Image processing failed: {str(e)}")

    if not extracted_text.strip():
        return {"success": False, "extracted_text": "", "matches": [], "ml_entities": [],
                "message": "No text detected. Try getting closer or type the name manually."}

    # Standard fuzzy matching
    matches = match_drug_name(extracted_text)

    # ML NER pipeline extraction
    extractor = get_entity_extractor()
    ml_entities = extractor.extract_entities(extracted_text)

    # Merge ML entities into matches if they found something new
    matched_keys = {m["drug_key"] for m in matches}
    for entity in ml_entities:
        if entity["drug_key"] not in matched_keys and entity["final_score"] >= 60:
            info = get_drug_info(entity["drug_key"])
            if info:
                matches.append({
                    "drug_key": entity["drug_key"],
                    "matched_term": entity["matched_term"],
                    "query_chunk": entity["chunk"],
                    "confidence": entity["final_score"],
                    "drug_info": info,
                    "source": "ml_ner",
                })
                matched_keys.add(entity["drug_key"])

    return {
        "success": len(matches) > 0,
        "extracted_text": extracted_text,
        "matches": matches,
        "ml_entities": [{"drug_key": e["drug_key"], "chunk": e["chunk"],
                          "score": e["final_score"]} for e in ml_entities[:5]],
        "message": f"Found {len(matches)} drug(s)" if matches else "No drugs identified. Try typing the name.",
    }


@app.post("/api/scan/text")
async def scan_text(request: TextScanRequest):
    """Text-based drug search with both fuzzy matching and ML NER."""
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    matches = match_drug_name(request.text)

    extractor = get_entity_extractor()
    ml_entities = extractor.extract_entities(request.text)

    matched_keys = {m["drug_key"] for m in matches}
    for entity in ml_entities:
        if entity["drug_key"] not in matched_keys and entity["final_score"] >= 60:
            info = get_drug_info(entity["drug_key"])
            if info:
                matches.append({
                    "drug_key": entity["drug_key"],
                    "matched_term": entity["matched_term"],
                    "query_chunk": entity["chunk"],
                    "confidence": entity["final_score"],
                    "drug_info": info,
                    "source": "ml_ner",
                })

    return {
        "success": len(matches) > 0,
        "extracted_text": request.text,
        "matches": matches,
        "message": f"Found {len(matches)} drug(s)" if matches else "No matching drugs found.",
    }


# ============ Interaction Endpoints ============

@app.post("/api/interactions/check")
async def check_interactions(request: InteractionRequest):
    drug_key = request.drug_key.lower()
    vault_keys = [k.lower() for k in request.vault_keys]
    info = get_drug_info(drug_key)
    if not info:
        raise HTTPException(status_code=404, detail=f"Drug '{drug_key}' not found")

    interactions = find_interactions(drug_key, vault_keys)
    has_critical = any(i["severity"] == "CRITICAL" for i in interactions)
    has_serious = any(i["severity"] == "SERIOUS" for i in interactions)

    return {
        "drug_key": drug_key,
        "drug_name": info["generic_name"],
        "vault_size": len(vault_keys),
        "interactions_found": len(interactions),
        "has_critical": has_critical,
        "has_serious": has_serious,
        "alert_level": "CRITICAL" if has_critical else "SERIOUS" if has_serious else "SAFE",
        "interactions": interactions,
    }

@app.post("/api/interactions/matrix")
async def interaction_matrix(request: MatrixRequest):
    vault_keys = [k.lower() for k in request.vault_keys]
    matrix = get_interaction_matrix(vault_keys)
    return {"vault_size": len(vault_keys), "interactions_found": len(matrix), "interactions": matrix}


# ============ ML/DS Analytics Endpoints ============

@app.post("/api/risk/score")
async def risk_score(request: RiskScoreRequest):
    """
    Personalized risk scoring using ML-inspired feature engineering.
    Takes patient profile (age, conditions) and medication list to
    calculate a weighted risk score with explainable factor breakdown.
    """
    vault_keys = [k.lower() for k in request.vault_keys]
    matrix = get_interaction_matrix(vault_keys)
    scorer = get_risk_scorer()

    result = scorer.calculate_risk_score(
        interactions=matrix,
        vault_size=len(vault_keys),
        age_group=request.age_group,
        conditions=request.conditions,
    )
    return result


@app.get("/api/analytics/graph")
async def full_graph():
    """Return the full drug interaction knowledge graph for visualization."""
    return get_full_graph_data()


@app.post("/api/analytics/vault-graph")
async def vault_graph(request: MatrixRequest):
    """Analyze the subgraph formed by the user's vault medications."""
    vault_keys = [k.lower() for k in request.vault_keys]
    return get_vault_subgraph_analysis(vault_keys)


@app.get("/api/analytics/stats")
async def graph_stats():
    """
    Return graph-level statistics: centrality measures, community detection,
    danger ranking, severity distribution, and network density.
    """
    G = build_interaction_graph()
    return get_graph_statistics(G)


# ============ Serve Frontend ============

_frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")

if os.path.isdir(_frontend_dir):
    app.mount("/static", StaticFiles(directory=_frontend_dir), name="static")

    @app.get("/")
    async def serve_frontend():
        return FileResponse(os.path.join(_frontend_dir, "index.html"))
