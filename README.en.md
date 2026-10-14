<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/readme/hero-dark.svg">
    <img src="docs/assets/readme/hero-light.svg" alt="AegisLab 实验哨兵 — AI × Spatial Modeling × Scenario Innovation" width="100%">
  </picture>
</p>

<h3 align="center">Scenario-aware AI pre-review for university laboratories</h3>
<p align="center">AI understands the plan. Space connects equipment, evidence and decisions.</p>

<p align="center">
  <a href="#overview"><img alt="AI + Scenario Innovation" src="https://img.shields.io/badge/AI-Scenario_Innovation-2563EB?style=flat-square&labelColor=334155"></a>
  <a href="#spatial"><img alt="3D Spatial Modeling" src="https://img.shields.io/badge/3D-Spatial_Modeling-0284C7?style=flat-square&labelColor=334155&logo=threedotjs&logoColor=white"></a>
  <a href="#architecture"><img alt="React" src="https://img.shields.io/badge/React-20232A?style=flat-square&logo=react&logoColor=61DAFB"></a>
  <a href="#architecture"><img alt="Three.js" src="https://img.shields.io/badge/Three.js-20232A?style=flat-square&logo=threedotjs&logoColor=white"></a>
  <a href="#architecture"><img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white"></a>
  <a href="https://github.com/fanyangzi/AegisLab/actions/workflows/desktop-web.yml"><img alt="Web workspace verification" src="https://github.com/fanyangzi/AegisLab/actions/workflows/desktop-web.yml/badge.svg?branch=main"></a>
</p>

<p align="center"><a href="README.md">简体中文</a> · <strong>English</strong></p>
<p align="center">
  <a href="#overview">Overview</a> ·
  <a href="#highlights">Highlights</a> ·
  <a href="#spatial">AI + Spatial Modeling</a> ·
  <a href="#workflow">Workflow</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#architecture">Architecture</a>
</p>

<p align="center">
  <a href="docs/assets/readme/workspace.png"><img src="docs/assets/readme/workspace.png" alt="Complete AegisLab workspace with laboratory, equipment, navigation, object details and resource timeline" width="100%"></a>
  <br><sub>Spatial workspace · Complete product interface · Example workspace</sub>
</p>

<a id="overview"></a>
## Overview

**AegisLab (实验哨兵, Lab Sentinel)** brings AI-assisted understanding, 3D spatial modeling, relationship graphs and collaborative workflows into one browser workspace for university laboratory planning and safety pre-review.

An experiment plan is more than a document: it refers to equipment, time windows, required controls and supporting records. AegisLab connects these into an interactive, traceable working context so researchers, instructors and laboratory staff can move from **reading a plan** to **understanding conditions, comparing changes and completing a review**.

> **AI + Scenario Innovation: turn experiments described in documents into interactive, checkable laboratory scenarios.**

Current examples focus on university chemistry, sample preparation and analytical testing. The website serves experiment authors, instructors, equipment administrators and authorized reviewers.

<a id="highlights"></a>
## Highlights

| Capability | How AegisLab implements it | What it enables |
| :--- | :--- | :--- |
| **AI plan understanding** | Organizes steps, equipment and control cues from an SOP into reviewable candidates with source locations. | Brings unstructured plans into the review workflow. |
| **Interactive spatial modeling** | Room dimensions and equipment types, positions and orientations drive a Three.js scene with selection, focus and details. | Makes the business objects involved in an experiment accessible in their spatial context. |
| **Relationships and sources** | Connects plans, steps, resources, conditions, records and decisions through neighborhood, type and path queries. | Traces a finding to the relevant objects, dependencies and evidence. |
| **What-if comparison** | Edits resources, times and supported fields in isolated candidates; shows check differences before submitting a new revision. | Helps users understand a change while keeping candidates separate from the official plan. |
| **Evidence applicability** | Checks equipment identity, specifications, validity intervals, verification status and conflicting records together. | Determines whether a record supports this experiment's particular conditions. |
| **Collaborative pre-review** | Links findings to evidence requests, assignment, return, handoff and decision records, with server-side permission and condition checks. | Turns analysis into accountable, traceable follow-up work. |

<a id="spatial"></a>
## AI + Spatial Modeling

**AI supplies semantic understanding, spatial modeling supplies object context, and rules and people complete the review.**

AegisLab constructs a 3D laboratory from room and resource configuration, then links plan references, check results and business actions to the corresponding equipment. The scene is configuration-driven; AI-assisted interpretation and spatial objects connect through shared business identities.

| Three views of one workspace | The question each view answers |
| :--- | :--- |
| **Space** | Where does the experiment happen? Which equipment does it involve? What plans reference the selected object? |
| **Graph** | What does the plan depend on? Which conditions and records explain a finding? Where is its source? |
| **Timeline** | When is the equipment needed? Does use overlap maintenance or other plans? Does evidence cover that interval? |

The views share plan, equipment and workspace data. Users can move from equipment to its plan, follow a relationship to evidence and switch to time to understand allocations. Object and source actions in AI analysis also return to the relevant working context.

**Space is the interaction surface. The graph explains dependencies. Time supplies the conditions.** Together, they support understanding, pre-review and change handling for a specific experiment.

<a id="workflow"></a>
## From Experiment Plans to Collaborative Decisions

<p align="center"><img src="docs/assets/readme/workflow-en.svg" alt="Understand the plan → Connect spatial objects → Check conditions and evidence → Compare changes → Collaborate and review" width="100%"></p>

1. **Import and understand:** upload TXT, Markdown, DOCX or a text-based PDF; preserve the source and confirm steps and object matches.
2. **Connect and review:** check equipment records, use intervals and supporting documents; request AI-assisted explanations and next-step suggestions.
3. **Compare and coordinate:** create a candidate, inspect its impact and assign evidence, coordination or review tasks.
4. **Confirm and record:** authorized people make decisions; the system retains their basis and history, and rechecks related results when conditions change.

For example, a plan needs a shared fume hood. A user can select it in the laboratory, inspect its plans and inspection records, then compare a different time or resource. **The plan, space, evidence and actions stay within the same experiment context.**

<a id="quick-start"></a>
## Quick Start

### 1. Install

Use **Node.js 22.12+ (22.x)** and **Python 3.12**. Commands below target macOS / Linux:

```bash
git clone https://github.com/fanyangzi/AegisLab.git
cd AegisLab

npm ci
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements-dev.txt
test -f .env || cp .env.example .env
```

On Windows, activate the virtual environment with `.venv\Scripts\Activate.ps1`. Preserve an existing `.env` and use the [configuration example](.env.example) to add the settings you need.

### 2. Start the Website

**Terminal 1: API**

```bash
source .venv/bin/activate
uvicorn backend.main:app --env-file .env --host 127.0.0.1 --port 8000 --reload
```

**Terminal 2: frontend**

```bash
npm run dev
```

Open **http://127.0.0.1:5173/** in your browser. For development, leave `VITE_API_BASE_URL` empty so Vite proxies `/api` requests.

Create your own laboratory and equipment, or explicitly import the example workspace. Open a plan to explore the connected spatial, relationship, time and AI-assisted review views.

### 3. Connect a Model

Configure the following in the server-side `.env`, then restart the API:

```dotenv
LABSAFETY_LLM_ENABLED=1
LABSAFETY_LLM_BASE_URL=
LABSAFETY_LLM_MODEL=
LABSAFETY_LLM_API_KEY=
```

Set `BASE_URL` to the base address of a compatible model API, `MODEL` to an identifier offered by that service and `API_KEY` to your credentials. The adapter tries Responses first, with a Chat Completions fallback for services that do not support that endpoint.

Open a plan's AI-assisted pre-review to run analysis. **Models propose interpretations and explanations, rules check conditions, and authorized people make the final review decision.** Keep credentials on the server, outside `VITE_*` variables and Git.

<details>
<summary><strong>Serve the website and API from one origin</strong></summary>

```bash
npm run build
AEGIS_SERVE_WEB=1 uvicorn backend.main:app --env-file .env --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000/**. FastAPI serves both the built website and API. Stop another development service using the same port first. Configure HTTPS and access control for a public deployment; use `AEGIS_WORKSPACE_TOKEN` to configure a workspace access token and connect through the website's settings.

</details>

<a id="architecture"></a>
## Architecture

| Layer | Technology and responsibility | Entry point |
| :--- | :--- | :--- |
| **Web workspace** | React, TypeScript and Vite; pages, selection, forms and cross-view context. | [`src/web/`](src/web/) |
| **Space and interaction** | Three.js; parametric equipment, scene modeling, cameras, picking and labels. | [`Scene.tsx`](src/web/Scene.tsx) |
| **Semantic understanding** | Model adapters, structured SOP candidates, source anchoring and explanations. | [`llm.py`](backend/app/llm.py) · [`parser.py`](backend/app/parser.py) |
| **Business logic and checks** | FastAPI; resource conditions, graph queries, branches, records, tasks and decisions. | [`spatial.py`](backend/app/spatial.py) |
| **Data and background work** | SQLite, revisions and idempotency, durable jobs and a separate Worker. | [`worker.py`](backend/worker.py) |

<details>
<summary><strong>Development checks</strong></summary>

```bash
npm run test:parity
npm run build
python -m unittest discover -s tests -p 'test_*.py' -v
python tests/smoke.py
```

Covers frontend/backend domain parity, APIs, document processing, collaboration states, authorization, concurrency and persistence.

</details>

## Contributing

Share feedback, use cases and reproducible issues through [Issues](https://github.com/fanyangzi/AegisLab/issues), or contribute through [Pull Requests](https://github.com/fanyangzi/AegisLab/pulls). See the [equipment survey](docs/equipment-taxonomy-research.md) and [source registry](data/knowledge_sources.json) for equipment categories and knowledge references.

<p align="center"><strong>实验哨兵 · AegisLab</strong><br><sub>知微守安队 · AI + Scenario Innovation</sub></p>
