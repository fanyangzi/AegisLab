# AegisLab chemical experiment safety backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload
```

The API is offline-first. `GET /health` checks SQLite and reports the model
adapter. Set `LABSAFETY_DB_PATH` to relocate the database. LLM settings are
`LABSAFETY_LLM_BASE_URL`, `LABSAFETY_LLM_MODEL`, `LABSAFETY_LLM_API_KEY`, and
`LABSAFETY_LLM_ENABLED`; without a key the deterministic offline summary
remains active.

Useful flow: `POST /parse/sop` or `POST /reviews/from-sop`,
`POST /reviews/{id}/submit`, `POST /reviews/{id}/evaluate`, approval gates,
`POST /reviews/{id}/override`, incident drills, `GET /skills`, and
`GET /reviews/{id}/evidence-package`.

An experiment review accepts `sop`, ordered `steps` (hazards, controls and PPE),
`substances` (hazard classes, storage and SDS reference), emergency controls,
findings and evidence. The deterministic organic-solvent rule pack checks PPE,
ventilation, incompatibility, equipment boundaries, waste streams, SDS/storage,
emergency response, evidence and approval gates. The safe Skill Harness accepts
JSON values only and never executes uploaded SOP content.
