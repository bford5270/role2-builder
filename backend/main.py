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

# --- DATABASE ENGINE ---
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

# --- GENAI CLIENT ---
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

@app.post("/generate-name")
async def generate_name(data: dict):
    aor = data.get("aor", "General")
    unit = data.get("unitType", "Division")
    prompt = f"Provide one unique USMC exercise name for a {unit} unit in {aor}. Style: Two words. No 'Crimson', 'Scalpel', 'Steel'. Random: {random.random()}"
    response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
    return {"name": response.text.strip()}

@app.post("/generate-msel")
async def generate_msel(data: dict):
    # This structure will be populated by tactical configuration in the next step
    df = pd.DataFrame([
        {"Time": "0800", "Inject": "EXSTART", "Description": "All Role 2 sections (STP/FRSS) active."},
        {"Time": "1000", "Inject": "Wave 1", "Description": "Triage and disposition initiated."},
        {"Time": "1400", "Inject": "MASCAL", "Description": "HSS-SVCS-3701 activated."}
    ])
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='MSEL')
    headers = {'Content-Disposition': 'attachment; filename="MSEL.xlsx"'}
    return Response(output.getvalue(), headers=headers, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.post("/generate-warno")
async def generate_warno(data: dict):
    prompt = f"Draft a USMC Medical WARNO. Exercise: {data.get('exerciseName')}. METs: {data.get('selectedMETs')}."
    response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
    db = SessionLocal()
    new_ex = Exercise(name=data.get('exerciseName'), details=data, warno=response.text)
    db.add(new_ex)
    db.commit()
    db.close()
    return {"document": response.text}