import os
import json
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import google.generativeai as genai

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mock Database (In production, we'd use a real DB like PostgreSQL)
EXERCISE_STORAGE = []

api_key = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-1.5-pro')

@app.get("/")
async def root():
    return {"status": "Role 2 Backend Active", "saved_count": len(EXERCISE_STORAGE)}

@app.post("/generate-name")
async def generate_name():
    prompt = "Generate 5 cool, professional USMC military exercise names focused on medical operations. Return only the names, comma separated."
    response = model.generate_content(prompt)
    names = response.text.split(",")
    return {"name": names[0].strip()}

@app.post("/save-exercise")
async def save_exercise(data: dict):
    # This saves the full detail to our "storage"
    EXERCISE_STORAGE.append(data)
    return {"message": "Exercise Saved Successfully", "id": len(EXERCISE_STORAGE)}

@app.get("/history")
async def get_history():
    return {"exercises": EXERCISE_STORAGE}

@app.post("/generate-warno")
async def generate_warno(data: dict):
    prompt = f"Write a USMC Medical WARNO for {data.get('exerciseName')}. METs: {data.get('mets')}."
    response = model.generate_content(prompt)
    
    # Save the document automatically with the exercise details
    data["generated_warno"] = response.text
    EXERCISE_STORAGE.append(data)
    
    return {"document": response.text}