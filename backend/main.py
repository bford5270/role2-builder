import os
import random
import pandas as pd
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from google import genai 
from io import BytesIO

app = FastAPI()

# --- DATABASE ---
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MODERN GENAI CLIENT ---
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

@app.post("/generate-name")
async def generate_name(data: dict):
    aor = data.get("aor", "General")
    unit = data.get("unitType", "Division")
    prompt = f"Unique USMC exercise name. Unit: {unit}. Environment: {aor}. No 'Crimson', 'Scalpel', 'Steel'. Random: {random.random()}"
    response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
    return {"name": response.text.strip()}

@app.post("/generate-msel")
async def generate_msel(data: dict):
    # Logic to build rows based on your NAVMC 3500.84A METs [cite: 9, 15]
    msel_data = [
        {"Time": "0800", "Event": "EXSTART", "Inject": "All Role 2 sections (STP/FRSS/COC) online.", "MET/PECL": "HSS-MBN-6001 [cite: 127]"},
        {"Time": "0930", "Event": "Wave 1", "Inject": "3x Category Red (Urgent) casualties arrival at Triage/Alpha.", "MET/PECL": "HSS-SVCS-3501 [cite: 53]"},
        {"Time": "1100", "Event": "Surgical Inject", "Inject": "FRSS reports surgical saturation; triage shift required.", "MET/PECL": "HSS-FRSS-4001 [cite: 89]"},
        {"Time": "1300", "Event": "MASCAL", "Inject": "Simulated IED blast: 15 casualties inbound.", "MET/PECL": "HSS-SVCS-3701 [cite: 78]"}
    ]
    
    df = pd.DataFrame(msel_data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='MSEL')
    
    headers = {'Content-Disposition': 'attachment; filename="MSEL.xlsx"'}
    return Response(output.getvalue(), headers=headers, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.post("/generate-warno")
async def generate_warno(data: dict):
    prompt = f"Draft formal USMC Medical WARNO. Exercise: {data.get('exerciseName')}. METs: {data.get('selectedMETs')}."
    response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
    
    db = SessionLocal()
    new_ex = Exercise(name=data.get('exerciseName'), details=data, warno=response.text)
    db.add(new_ex)
    db.commit()
    db.close()
    return {"document": response.text}