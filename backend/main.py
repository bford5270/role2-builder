@app.post("/generate-name")
async def generate_name(data: dict):
    aor = data.get("aor", "General")
    unit = data.get("unitType", "Medical")
    # Prompt now understands the difference between Division and CLB
    prompt = f"Generate one professional USMC military exercise name for a {unit} unit operating in a {aor} environment. Focus on medical surgical resonance. Return only the name."
    response = model.generate_content(prompt)
    return {"name": response.text.strip()}

@app.post("/generate-warno")
async def generate_warno(data: dict):
    # This captures the specific Role 2 footprint and specialties for the AI
    footprint = ", ".join(data.get('selectedSpaces', []))
    mets = ", ".join(data.get('selectedMETs', []))
    
    prompt = f"""
    Write a formal USMC Medical WARNO. 
    Exercise Name: {data.get('exerciseName')}
    AOR: {data.get('aor')}
    Duration: {data.get('duration')} days
    Functional Footprint: {footprint}
    Focus METs: {mets}
    
    Ensure the WARNO references specific Role 2 entities like the STP and FRSS 
    where appropriate for triage and damage control surgery.
    """
    
    response = model.generate_content(prompt)
    
    # Save to PostgreSQL
    db = SessionLocal()
    new_ex = Exercise(name=data.get('exerciseName'), details=data, warno=response.text)
    db.add(new_ex)
    db.commit()
    db.close()
    
    return {"document": response.text}
