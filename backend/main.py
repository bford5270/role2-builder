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

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

@app.post("/generate-name")
async def generate_name(data: dict):
    aor = data.get("aor", "General")
    unit = data.get("unitType", "Medical")
    # Random seed forces a new name reiteration every time the button is clicked
    prompt = f"Generate one unique USMC exercise name for a {unit} unit in {aor}. Use two aggressive words. Avoid 'Crimson', 'Scalpel', 'Steel'. Seed: {random.random()}"
    response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
    return {"name": response.text.strip()}

@app.post("/generate-msel")
async def generate_msel(data: dict):
    # Base structure for the Excel export
    df = pd.DataFrame([{"Time": "0800", "Inject": "EXSTART", "Description": "HSS capabilities established.", "MET": "HSS-MBN-6001"}])
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='MSEL')
    return Response(output.getvalue(), headers={'Content-Disposition': 'attachment; filename="MSEL.xlsx"'}, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.post("/generate-warno")
async def generate_warno(data: dict):
    prompt = f"Draft a USMC Medical WARNO. Exercise: {data.get('exerciseName')}. Duration: {data.get('duration')} days."
    response = client.models.generate_content(model="gemini-1.5-flash", contents=prompt)
    db = SessionLocal()
    db.add(Exercise(name=data.get('exerciseName'), details=data, warno=response.text))
    db.commit()
    db.close()
    return {"document": response.text}