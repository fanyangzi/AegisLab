# AegisLab

**AegisLab｜实验协议可信安全智能体** is an offline-first web console for
pre-reviewing organic-solvent experiments in a university chemistry lab.

It turns an SOP into structured steps and chemical entities, checks versioned
hard rules for PPE, ventilation, equipment boundaries, incompatibility and waste,
keeps high-risk work blocked until an authorized safety owner reviews it, runs
three bounded incident-rehearsal scenarios, and exports an auditable evidence
bundle. The LLM is optional: it explains and extracts; it never executes SOP
content and it cannot override deterministic rules.

The first demo cases are liquid-liquid extraction, solvent transfer/evaporation,
and chromatography with organic waste. Other experiment types are future work.
All demo cases and evaluation rows are marked `synthetic/demo`.

## Run the frontend

```bash
npm install
npm run dev
```

The UI works without an API and loads the generated evaluation snapshot from
`public/eval-summary.json`.

## Run the API

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env
uvicorn backend.main:app --reload
```

The API exposes `/health`, `/parse/sop`, `/reviews`, `/reviews/{id}/evaluate`,
`/reviews/{id}/evidence-package`, `/incidents`, `/skills`, and the safe
JSON-only Skill Harness. If no model key is configured, it remains in offline
mode. When configured, it uses `LABSAFETY_LLM_BASE_URL`,
`LABSAFETY_LLM_MODEL`, and `LABSAFETY_LLM_API_KEY`; the key is never stored in
the database, logs, evidence bundle, or source tree.

## Run the evaluation

```bash
python3 eval/run_eval.py
```

The output is a synthetic/demo baseline for the organic-solvent rule pack. It is
not a field trial, an institutional safety certification, or a claim about
accident reduction.

## Scope and safety boundary

AegisLab is a review and training aid. It does not certify a lab, replace an EHS
professional, or provide dangerous reaction parameters or executable emergency
instructions. Evidence sources are recorded with their URL, version/terms,
retrieval time and hash when used.
