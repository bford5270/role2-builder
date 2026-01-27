import os
import random
import pandas as pd
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import google.generativeai as genai
from io import BytesIO

app = FastAPI()

# --- DATABASE SETUP ---
DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Exercise(Base):
    __tablename__ = "exercises"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    details = Column(JSON)
    warno = Column(String)

Base.metadata.create_all(bind=engine)

# --- SECURITY & AI ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_key = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-1.5-pro')

# --- ENDPOINTS ---

@app.post("/generate-name")
async def generate_name(data: dict):
    aor = data.get("aor", "General")
    unit = data.get("unitType", "Division")
    prompt = f"Generate one unique USMC exercise name for a {unit} unit in a {aor} environment. Style: Aggressive/Medical. Avoid 'Crimson', 'Scalpel', 'Steel'. Seed: {random.random()}"
    response = model.generate_content(prompt)
    return {"name": response.text.strip()}

@app.post("/generate-msel")
async def generate_msel(data: dict):
    # This structure is designed to be populated by the tactical waves next
    df = pd.DataFrame([
        {"Time": "0800", "Inject": "Exercise Start", "Description": "All Role 2 sections (STP/FRSS/COC) online."},
        {"Time": "1000", "Inject": "Casualty Wave 1", "Description": "Point of Injury arrivals; Triage initiated."},
        {"Time": "1400", "Inject": "MASCAL Declared", "Description": "MCT 4.5.6 procedures activated."}
    ])
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='MSEL')
    headers = {'Content-Disposition': 'attachment; filename="MSEL.xlsx"'}
    return Response(output.getvalue(), headers=headers, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.post("/generate-warno")
async def generate_warno(data: dict):
    prompt = f"Write a formal USMC Medical WARNO for {data.get('exerciseName')}. Focus METs: {data.get('selectedMETs')}. Environmental: {data.get('aor')}."
    response = model.generate_content(prompt)
    
    db = SessionLocal()
    new_ex = Exercise(name=data.get('exerciseName'), details=data, warno=response.text)
    db.add(new_ex)
    db.commit()
    db.close()
    
    return {"document": response.text}