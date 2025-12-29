import os
import time
import json
import requests
import google.generativeai as genai
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
MOCK_MODE = False 

# PASTE YOUR KEYS HERE
GOOGLE_SEARCH_KEY = "AIzaSyDAO6SDoB9wLRgXx8LhtDx_ijZQ0vyAmm0"
SEARCH_ENGINE_ID = "327b63d78557d4105"
GEMINI_API_KEY = "AIzaSyDKl-_nC9uAEbyQAoFWocAWmNNyT4mKEYw"

# ==========================================
# 🧠 UNIVERSAL AUTO-LOADER
# ==========================================
MODEL_NAME = None

if not MOCK_MODE:
    genai.configure(api_key=GEMINI_API_KEY)
    
    print("\n🤖 SYSTEM STARTUP: Scanning for ANY working model...")
    try:
        available_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name)
        
        if available_models:
            # Prefer Flash models for speed
            chosen_model = available_models[0]
            for m in available_models:
                if "flash" in m:
                    chosen_model = m
                    break
            
            MODEL_NAME = chosen_model
            print(f"✅ SUCCESS: Connected to '{MODEL_NAME}'")
            model = genai.GenerativeModel(MODEL_NAME)
        else:
            print("❌ FAILURE: No models available.")
            MOCK_MODE = True

    except Exception as e:
        print(f"❌ CONNECTION ERROR: {e}")
        MOCK_MODE = True

def generate_safe(prompt):
    if MOCK_MODE: return None
    try:
        return model.generate_content(prompt)
    except Exception as e:
        print(f"AI Generation Error: {e}")
        return None

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ProjectRequest(BaseModel):
    abstract: str

# ==========================================
# 🧠 CORE FUNCTIONS
# ==========================================

def clean_json_response(text):
    text = text.replace("```json", "").replace("```", "").strip()
    return text

def search_google_accurate(query):
    """
    Fetches real-world data for the AI to cross-check against.
    """
    url = "https://www.googleapis.com/customsearch/v1"
    domains = ["site:github.com", "site:ieeexplore.ieee.org","site:patents.google.com", "site:researchgate.net", "site:arxiv.org"]
    site_filter = " OR ".join(domains)
    refined_query = f"{query} (project OR implementation) ({site_filter})"
    
    params = {'key': GOOGLE_SEARCH_KEY, 'cx': SEARCH_ENGINE_ID, 'q': refined_query, 'num': 8}
    try:
        resp = requests.get(url, params=params)
        return resp.json()
    except Exception as e:
        print(f"Search failed: {e}")
        return {}

def analyze_with_ai_cross_check(abstract, search_results):
    """
    The Core Engine: Uses AI to calculate EVERYTHING based on evidence.
    """
    if MOCK_MODE: 
        return {
            "similarity_score": 85, "novelty_score": 15, "feasibility_score": 90,
            "pivot_suggestion": "Mock Data Pivot", "feasibility_reason": "Mock Data", "verdict": "Common"
        }
    
    # 1. Prepare Evidence for the AI
    evidence_list = []
    if 'items' in search_results:
        for item in search_results['items']:
            evidence_list.append(f"- {item.get('title')}: {item.get('snippet')}")
    
    evidence_text = "\n".join(evidence_list[:6])

    # 2. The Master Prompt
    prompt = f"""
    Act as a Senior Chief Technology Officer (CTO).
    
    USER PROJECT IDEA: "{abstract}"
    
    EVIDENCE FROM WEB SEARCH (SIMILAR PROJECTS):
    {evidence_text}
    
    TASK:
    1. Cross-check the User's Idea against the Evidence.
    2. Analyze if the core functionality already exists.
    3. Calculate 3 scores (0-100) based strictly on the Evidence.
    
    SCORING RULES:
    - Similarity: How much does it overlap with the Evidence? (0 = Unique, 100 = Exact Clone)
    - Novelty: (100 - Similarity).
    - Feasibility: Can a final-year student build this in 3 months?
    
    RETURN EXACT JSON ONLY:
    {{
        "similarity_score": (int),
        "novelty_score": (int),
        "feasibility_score": (int),
        "verdict": "Unique" or "Common" or "Very Common",
        "pivot_suggestion": "One sentence suggestion to make it innovative.",
        "feasibility_reason": "One sentence explanation citing the evidence."
    }}
    """
    
    response = generate_safe(prompt)
    
    if response:
        try:
            text = clean_json_response(response.text)
            return json.loads(text)
        except:
            return None
    return None

# ==========================================
# 🚀 ENDPOINT
# ==========================================

@app.post("/validate")
async def validate_project(request: ProjectRequest):
    try:
        print(f"🔍 Analyzing: {request.abstract[:50]}...") 

        # 1. Search Real Evidence
        search_data = search_google_accurate(request.abstract)
        
        # 2. Extract Sources for Frontend
        sources = []
        if 'items' in search_data:
            for item in search_data['items']:
                sources.append({"title": item.get('title'), "link": item.get('link')})

        # 3. AI Cross-Check & Scoring
        ai_result = analyze_with_ai_cross_check(request.abstract, search_data)
        
        # Fallback if AI fails
        if not ai_result:
            ai_result = {
                "similarity_score": 0, "novelty_score": 0, "feasibility_score": 0,
                "verdict": "Error", "pivot_suggestion": "AI Failed", "feasibility_reason": "Check logs"
            }

        return {
            "metrics": {
                "similarity": ai_result.get("similarity_score", 0),
                "novelty": ai_result.get("novelty_score", 0),
                "feasibility": ai_result.get("feasibility_score", 0)
            },
            "analysis": {
                "pivot": ai_result.get("pivot_suggestion", "N/A"),
                "feasibility_reason": ai_result.get("feasibility_reason", "N/A"),
                "verdict": ai_result.get("verdict", "Unknown")
            },
            "sources": sources[:5]
        }

    except Exception as e:
        print(f"🔥 Error: {e}")
        raise HTTPException(status_code=500, detail="Server Error")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)