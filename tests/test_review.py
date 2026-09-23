"""Review workflow against SQLite: comments, controller edits (re-red-teamed),
approval gates, library export, and packets printing the sign-off."""
import io
import json
import pathlib
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import main, redteam

FIX = json.loads((pathlib.Path(__file__).parent / "fixtures" / "erss_ship_sim_dcs.json").read_text())


@pytest.fixture()
def client(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'r.db'}")
    main.Base.metadata.create_all(engine)
    SL = sessionmaker(bind=engine)
    monkeypatch.setattr(main, "SessionLocal", SL)
    case = dict(FIX["case"])
    case["controller"] = redteam.red_team(FIX["controller"], case)
    cfg = dict(exercise_name="Op Review", duration=1, supported_unit="MEU", environment="Maritime",
               threat_level="Peer/Near-Peer", region="Indo-Pacific", selected_mets=[], selected_footprint=["FRSS"],
               specialists={}, days=[{"day_number": 1, "tactical_setting": "Amphibious Assault",
                                      "total_patients": 1, "total_waves": 1}])
    db = SL()
    ex = main.Exercise(name="Op Review", config=cfg, cases=[case],
                       msel_data=[{"day": 1, "time": "0930", "event": "Routine", "arr_raw": 570}],
                       warno_text="w", annex_q_text="a", medroe_text="m", road_to_war_text="r", fragos=[])
    db.add(ex)
    db.commit()
    eid = ex.id
    db.close()
    return TestClient(main.app), eid


def test_review_flow(client):
    c, eid = client
    assert c.get("/reviews/status").json()["enabled"] is True
    ov = c.get(f"/exercises/{eid}/review").json()
    assert ov["cases"][0]["status"] == "auto_checked"
    assert ov["cases"][0]["red_team"]["high"] == 2

    r = c.post(f"/exercises/{eid}/review/0/comments",
               json={"author": "Maj Trauma", "target": "legs[R2-ERC2].tree.n7", "body": "Scapula side wrong", "severity": "high"})
    cid = r.json()["id"]
    assert c.get(f"/exercises/{eid}/review").json()["cases"][0]["status"] == "in_review"

    # Blocked: open high comment
    r = c.post(f"/exercises/{eid}/review/0/decision", json={"reviewer": "Maj Trauma", "status": "approved"})
    assert r.status_code == 409
    c.patch(f"/exercises/{eid}/review/0/comments/{cid}", json={"resolved": True})
    # Blocked: open high red-team findings
    r = c.post(f"/exercises/{eid}/review/0/decision", json={"reviewer": "Maj Trauma", "status": "approved"})
    assert r.status_code == 409 and "red-team" in r.json()["detail"]

    # Expert edit fixes laterality; rules re-run
    ctrl = c.get(f"/exercises/{eid}/review/0").json()["case"]["controller"]
    for leg in ctrl["legs"]:
        for n in leg["tree"]["nodes"]:
            n["label"] = n["label"].replace("L Scapula", "R Scapula")
    r = c.put(f"/exercises/{eid}/review/0/controller", json={"author": "Maj Trauma", "controller": ctrl, "summary": "Fixed scapula side"})
    assert r.status_code == 200
    assert r.json()["controller"]["red_team"]["counts"]["high"] == 0
    assert r.json()["review"]["status"] == "in_review"

    r = c.post(f"/exercises/{eid}/review/0/decision", json={"reviewer": "Maj Trauma", "status": "approved", "note": "Good to run"})
    assert r.status_code == 200 and r.json()["status"] == "approved"

    lib = c.get("/library").json()
    assert lib["cases"][0]["reviewer"] == "Maj Trauma"
    exported = c.get(f"/library/{eid}/0").json()
    assert exported["cases"][0]["case"]["controller"]["review"]["status"] == "approved"

    # Packet prints the sign-off
    z = zipfile.ZipFile(io.BytesIO(c.get(f"/exercises/{eid}/download").content))
    from docx import Document
    doc = Document(io.BytesIO(z.read("Op Review_Controller_Packet.docx")))
    cells = [cell.text for t in doc.tables for row in t.rows for cell in row.cells]
    assert "Maj Trauma" in cells and "Approved" in cells


def test_review_disabled_without_db(monkeypatch):
    monkeypatch.setattr(main, "SessionLocal", None)
    c = TestClient(main.app)
    assert c.get("/reviews/status").json()["enabled"] is False
    assert c.get("/exercises/1/review").status_code == 503
    assert c.get("/library").json() == {"enabled": False, "cases": []}
