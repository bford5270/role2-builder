import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import google.generativeai as genai

app = FastAPI()

# Security: Allows your Vercel site to talk to this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Gemini using an Environment Variable (we set this in Railway later)
api_key = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-1.5-pro')

@app.get("/")
async def root():
    return {"status": "Role 2 Backend Active"}

@app.post("/generate-warno")
async def generate_warno(data: dict):
    # This takes the data from your website and asks Gemini to write the WARNO
    prompt = f"Write a USMC Medical WARNO for an exercise called {data.get('exerciseName')}. Duration: {data.get('duration')} days. Environment: {data.get('aor')}. Focus on METs: {data.get('mets')}."
    
    response = model.generate_content(prompt)
    return {"document": response.text}