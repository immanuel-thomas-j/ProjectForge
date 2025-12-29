import os
import json
import requests
import google.generativeai as genai
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# ==========================================
# ⚙️ CONFIGURATION (MUST BE AT THE TOP)
# ==========================================

# 1. Load environment variables
load_dotenv()

# 2. Define variables FIRST (Fixes NameError)
GOOGLE_SEARCH_KEY = os.getenv("GOOGLE_SEARCH_KEY")
SEARCH_ENGINE_ID = os.getenv("SEARCH_ENGINE_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 3. Initialize Mock Mode
MOCK_MODE = False 

# 4. Check if keys exist
if not GEMINI_API_KEY:
    print("⚠️ WARNING: GEMINI_API_KEY not found in .env file. Switching to MOCK_MODE.")
    MOCK_MODE = True

# ==========================================
# 🧠 SMART MODEL LOADER
# ==========================================
MODEL_NAME = "gemini-1.5-flash" 

if not MOCK_MODE:
    try:
        # Now GEMINI_API_KEY is defined, so this works:
        genai.configure(api_key=GEMINI_API_KEY)
        
        # Check available models
        try:
            available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
            if any("gemini-2.5-flash" in m for m in available_models):
                MODEL_NAME = "gemini-2.5-flash"
            elif any("gemini-2.0-flash" in m for m in available_models):
                MODEL_NAME = "gemini-2.0-flash-exp"
        except:
            pass # Fallback to default if listing fails
        
        print(f"✅ AI CONNECTED: {MODEL_NAME}")
        model = genai.GenerativeModel(MODEL_NAME)
    except Exception as e:
        print(f"⚠️ AI Connection Failed: {e}")
        MOCK_MODE = True

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Request Models ---
class RequestModel(BaseModel):
    abstract: str
    duration: str = "3 Months"
    tech_stack: str = "" 

class StackRequestModel(BaseModel):
    abstract: str
    difficulty: str
    duration: str
    requirements: str = ""

# ==========================================
# 🧠 HELPER FUNCTIONS
# ==========================================

def clean_json(text):
    text = text.replace("```json", "").replace("```", "").strip()
    return text

def google_search(query, num_results=3):
    if MOCK_MODE or not GOOGLE_SEARCH_KEY: return []
    url = "https://www.googleapis.com/customsearch/v1"
    try:
        resp = requests.get(url, params={
            'key': GOOGLE_SEARCH_KEY, 
            'cx': SEARCH_ENGINE_ID, 
            'q': query, 
            'num': num_results
        })
        return resp.json().get('items', [])
    except Exception as e:
        print(f"Google Search Error: {e}")
        return []

def search_youtube(query):
    if MOCK_MODE or not GOOGLE_SEARCH_KEY: return []
    url = "https://www.googleapis.com/youtube/v3/search"
    try:
        params = {
            'part': 'snippet',
            'q': f"{query} crash course tutorial",
            'key': GOOGLE_SEARCH_KEY,
            'maxResults': 2,
            'type': 'video'
        }
        resp = requests.get(url, params=params)
        data = resp.json()
        videos = []
        for item in data.get('items', []):
            videos.append({
                "title": item['snippet']['title'],
                "thumbnail": item['snippet']['thumbnails']['medium']['url'],
                "link": f"https://www.youtube.com/watch?v={item['id']['videoId']}",
                "channel": item['snippet']['channelTitle']
            })
        return videos
    except Exception as e:
        print(f"YouTube Error: {e}")
        return []

def generate_safe(prompt):
    if MOCK_MODE: return None
    try:
        return model.generate_content(prompt)
    except Exception as e:
        print(f"AI Generation Error: {e}")
        return None

# ==========================================
# 🚀 ENDPOINT 1: NOVELTY VALIDATOR
# ==========================================
@app.post("/validate")
async def api_validate(req: RequestModel):
    tech_search = google_search(f"site:github.com OR site:arxiv.org {req.abstract} project implementation", num_results=5)
    evidence_text = "\n".join([f"- {i['title']}: {i['snippet']}" for i in tech_search])
    
    prompt = f"""
    Act as a Senior CTO. Analyze this project idea: "{req.abstract}"
    
    EVIDENCE FROM WEB:
    {evidence_text}
    
    TASK:
    1. Score Complexity (0-100) based on technical difficulty.
    2. Score Novelty (0-100) based on how unique it is compared to the evidence.
    3. Determine Feasibility (0-100) for a small team.
    4. Suggest 3 Unique Variants (Pivots) that make the idea stand out more.
    
    STRICT JSON OUTPUT FORMAT:
    {{
        "original": {{
            "novelty_score": (int),
            "complexity_score": (int),
            "feasibility_score": (int),
            "verdict": "Unique/Common",
            "reason": "A 2-sentence explanation of the analysis."
        }},
        "variants": [
            {{ "title": "Variant Name", "desc": "Short description of the pivot.", "novelty": 90, "complexity": 80 }}
        ]
    }}
    """
    
    res = generate_safe(prompt)
    data = {
        "original": {"novelty_score": 0, "complexity_score": 0, "feasibility_score": 0, "verdict": "Error", "reason": "AI Failed"},
        "variants": []
    }
    if res:
        try:
            data = json.loads(clean_json(res.text))
        except Exception as e:
            pass
    
    valid_evidence = [{"title": i['title'], "link": i['link']} for i in tech_search if 'title' in i and 'link' in i]
    data['evidence'] = valid_evidence[:4]
    
    return data

# ==========================================
# 📅 ENDPOINT 2: PLANNER + YOUTUBE
# ==========================================
@app.post("/roadmap")
async def api_roadmap(req: RequestModel):
    try:
        stack_instruction = f"Strictly use this Tech Stack: {req.tech_stack}" if req.tech_stack else "Suggest the best modern Tech Stack."

        prompt = f"""
        Act as a Technical PM. Create a roadmap for: "{req.abstract}"
        Timeline: {req.duration}.
        {stack_instruction}
        
        RETURN JSON ONLY:
        {{
            "stack": ["Tool 1", "Tool 2", "Tool 3"], 
            "roadmap": [
                {{"week": "Week 1", "phase": "Setup", "tasks": ["Task 1", "Task 2"]}},
                {{"week": "Week 2", "phase": "Backend", "tasks": ["Task 3", "Task 4"]}}
            ]
        }}
        """
        res = generate_safe(prompt)
        
        if not res:
            raise HTTPException(status_code=500, detail="AI Failed")
            
        data = json.loads(clean_json(res.text))
        
        videos = []
        if data.get("stack"):
            for tech in data['stack'][:2]: 
                videos.extend(search_youtube(tech))
                
        data['tutorials'] = videos[:3]
        return data

    except Exception as e:
        raise HTTPException(status_code=500, detail="Server Error")

# ==========================================
# 🛠️ ENDPOINT 3: TECH STACK SUGGESTER (FAST)
# ==========================================
@app.post("/suggest")
async def api_suggest(req: StackRequestModel):
    try:
        prompt = f"""
        Act as a Tech Architect.
        Project: "{req.abstract}"
        Constraints: {req.difficulty}, {req.duration}, {req.requirements}
        
        Generate 3 distinct Tech Stacks.
        KEEP IT CONCISE.
        - "reason": Max 15 words.
        - "pros": 2 bullet points (max 3 words each).
        
        RETURN JSON ONLY:
        {{
            "suggestions": [
                {{
                    "name": "The Rapid Stack",
                    "technologies": ["React", "Firebase", "Tailwind"],
                    "reason": "Instant backend setup perfect for tight deadlines.",
                    "pros": ["Fast Setup", "Real-time DB"],
                    "cons": ["Vendor Lock-in"]
                }}
            ]
        }}
        """
        res = generate_safe(prompt)
        
        data = {"suggestions": []}
        if res:
            try:
                data = json.loads(clean_json(res.text))
            except:
                pass
        
        return data

    except Exception as e:
        raise HTTPException(status_code=500, detail="Server Error")

# ==========================================
# 🎓 ENDPOINT 4: VIVA DEFENDER
# ==========================================
@app.post("/viva")
async def api_viva(req: RequestModel):
    try:
        prompt = f"""
        Act as a strict External Examiner.
        Project: "{req.abstract}"
        
        Generate 5 TOUGH technical questions.
        Constraints:
        1. Questions must be SHORT (Max 15 words).
        2. Answers must be CONCISE (Max 2 sentences).
        
        RETURN JSON ONLY:
        {{
            "questions": [
                {{ "q": "Why Firebase over MongoDB?", "a": "Built-in syncing." }}
            ]
        }}
        """
        res = generate_safe(prompt)
        if res:
            try:
                return json.loads(clean_json(res.text))
            except:
                pass
        
        raise HTTPException(status_code=500, detail="Viva Prep Failed")

    except Exception as e:
        raise HTTPException(status_code=500, detail="Server Error")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)