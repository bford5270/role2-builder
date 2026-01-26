import os
import pandas as pd
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_url, create_engine, Column, Integer, String, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import google.generativeai as genai
from io import BytesIO

app = FastAPI()

# Database Setup
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

# Standard Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

api_key = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-1.5-pro')

@app.post("/generate-name")
async def generate_name():
    prompt = "Generate 5 professional USMC medical exercise names. Return only the names, comma separated."
    response = model.generate_content(prompt)
    return {"name": response.text.split(",")[0].strip()}

@app.post("/generate-msel")
async def generate_msel(data: dict):
    # This creates the Excel spreadsheet in memory
    df = pd.DataFrame([
        {"Time": "0800", "Event": "Initial Casualties", "Location": "Role 2", "Injected By": "Control", "Description": "3x GSW to Chest"},
        {"Time": "1000", "Event": "MASCAL Declared", "Location": "Role 2", "Injected By": "Evaluator", "Description": "Wave of 10 casualties arrival"},
        {"Time": "1400", "Event": "Evac Denied", "Location": "AOR", "Injected By": "Intel", "Description": "Weather/AA threat prevents launch"}
    ])
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='MSEL')
    
    headers = {
        'Content-Disposition': 'attachment; filename="MSEL.xlsx"'
    }
    return Response(output.getvalue(), headers=headers, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.post("/generate-warno")
async def generate_warno(data: dict):
    prompt = f"Write a USMC Medical WARNO for {data.get('exerciseName')}. METs: {data.get('mets')}."
    response = model.generate_content(prompt)
    
    # Save to Database
    db = SessionLocal()
    new_ex = Exercise(name=data.get('exerciseName'), details=data, warno=response.text)
    db.add(new_ex)
    db.commit()
    db.close()
    
    return {"document": response.text}