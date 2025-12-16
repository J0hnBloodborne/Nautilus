% Nautilus — End-to-End ML Deployment & MLOps Pipeline (Entertainment & Media)

Overview
--------
Nautilus is a student/research project that implements an end-to-end ML engineering pipeline focused on the "Entertainment & Media" domain. It was developed to demonstrate professional MLOps workflows: model training, validation, deployment with FastAPI, orchestration with Prefect, automated ML testing, and containerization.

This repository contains the pieces required by the course brief:
- A FastAPI backend exposing prediction and discovery endpoints used by the demo UI.
- Prefect flows and orchestration helpers for ingesting data, feature engineering, training, and model versioning.
- Automated ML testing and data validation using DeepChecks (and standard unit tests).
- Dockerfile and docker-compose examples for containerizing the API and auxiliary services.
- Data ingestion & preprocessing scripts (including a MovieLens aggregator used to precompute a top-rated cache for experiments).
- Multiple ML artifacts and example workflows: recommendation models, classification/regression examples, clustering, dimensionality reduction examples, and time-series utilities used for experiments and admin analytics.

NOTE: This README intentionally describes the ML and MLOps aspects of the project. It does not document or advertise any media playback or streaming functionality.

Project layout
--------------
- src/
  - api/                 FastAPI application and request handlers (entrypoint: `src/api/main.py`)
  - core/, ml/, models/   Model code, training and inference utilities
  - frontend/             Static frontend files (HTML/CSS/JS used for the demo UI)
- scripts/                Utility scripts (data aggregation, seeding, ETL helpers)
- data/                   Raw and processed data used by the demo (see `data/processed/top_rated_movies.json`)
- tests/                  Small test suite used by the project's test harness
- requirements.txt        Python dependencies for CPU-based runs
- requirements-gpu.txt    Optional GPU-oriented requirements (if you want GPU acceleration)

Quick start (development)
-------------------------
Prerequisites
- Python 3.10+ (virtualenv recommended)
- pip

Setup

1. Create and activate a virtual environment (example):

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. (Optional) If you plan to run GPU workloads, see `requirements-gpu.txt` and use an appropriate environment.

GPU installation (optional)
---------------------------
If you have a GPU and the correct CUDA/toolkit installed, you can install GPU-capable packages. Be careful to match the package wheels to your CUDA version.

Example (install RAPIDS/cuDF/cuML packages for CUDA 13 as shown in `requirements-gpu.txt`):

```bash
# Adjust versions to match your CUDA/runtime. This example mirrors the project's GPU guidance:
pip install \
  --extra-index-url=https://pypi.nvidia.com \
  "cudf-cu13==25.12.*" "dask-cudf-cu13==25.12.*" "cuml-cu13==25.12.*" \
  "cugraph-cu13==25.12.*" "nx-cugraph-cu13==25.12.*" "cuxfilter-cu13==25.12.*" \
  "cucim-cu13==25.12.*" "pylibraft-cu13==25.12.*" "raft-dask-cu13==25.12.*" \
  "cuvs-cu13==25.12.*" "nx-cugraph-cu13==25.12.*"
```

For TensorFlow GPU wheels, prefer the official TensorFlow install instructions matching your platform and CUDA version. The `requirements-gpu.txt` file swaps `tensorflow` for `tensorflow[and-cuda]` as a hint; follow vendor docs for the exact wheel selection.

Run the API server (development)

```bash
# From the project root
uvicorn src.api.main:app --reload
```

This starts the FastAPI app with hot reload for development. The app exposes the demo endpoints used by the frontend static files.

Frontend / demo UI
------------------
The demo UI is implemented as static assets under `src/frontend/static/`. It contains:
- `index.html` — homepage and discovery UI
- `admin.html` — admin and analytics dashboard
- `script.js`, `styles.css` — client-side logic and styling

Open the running backend (uvicorn) and point your browser to the host/port served (by default http://127.0.0.1:8000) to access the UI pages.

Data
----
- Raw data and caches live in the `data/` folder. The repository includes a precomputed MovieLens-derived cache at `data/processed/top_rated_movies.json` used to speed up top-rated queries.
- Use the aggregator script to regenerate the top-rated cache from local MovieLens CSVs if needed:

```bash
python3 scripts/aggregate_movielens_top_rated.py --top 2000 --min_votes 20
```

Machine learning components
---------------------------
High level components included in the repo:
- Recommendation system: a collaborative filtering / neural CF fallback used for guest recommendations and demo personalization.
- Genre & revenue predictors: small supervised models used to produce metadata badges and simple forecasts used by the demo admin UI.

Model training, evaluation and retraining utilities sit under `src/ml/` and `src/core/`. See inline README/comments in those folders for notes on datasets, preprocessing, and training recipes.

API endpoints (overview)
------------------------
The FastAPI app exposes a number of endpoints used by the frontend and admin UI. Examples include:
- GET /movies/top_rated_alltime — returns a cached list of top-rated movies (uses `data/processed/top_rated_movies.json` as a fast path)
- GET /movies/new_releases — recent content
- GET /recommend/guest/{guest_id} — guest recommendations (uses local prefs header if provided)
- GET /predict/genre/{tmdb_id} — genre predictions for UI badges
- GET /movie/{tmdb_id}/prediction — revenue/forecast predictions used in admin panels
- Additional helper endpoints for related-items and collections are present; check `src/api/main.py` for the complete list and docs.

Course alignment & objectives
-----------------------------
This project was structured to satisfy the course requirements for an end-to-end ML deployment and MLOps pipeline. Below is a mapping from the course objectives to the repository contents and where to find related code:

1) Build and Deploy ML Models with FastAPI
  - Model serving and API endpoints: `src/api/main.py` and related routers.
  - Example prediction endpoints: `/predict/genre/{tmdb_id}`, `/movie/{tmdb_id}/prediction`.
  - Model loading & inference utilities: `src/ml/` and `src/core/` (see per-module READMEs).

2) Implement CI/CD Pipeline Using GitHub Actions
  - GitHub Actions workflows are stored in `.github/workflows/` and demonstrate automated checks, unit tests, and container image builds. (Adjust workflow triggers for your CI environment.)

3) Orchestrate ML Workflows Using Prefect
  - Prefect flows and tasks are available under `src/workflows/` and `src/core/flows/` (example ingestion, feature engineering, training, evaluation, and save/version steps).

4) Implement Automated Testing for ML Models
  - DeepChecks test suites and assertions are wired into the `tests/` folder and CI workflow to validate data integrity, detect drift, and check model performance before deployment.

5) Containerize the Entire System
  - Dockerfile(s) and docker-compose examples live in the project root. Use them to build the FastAPI service and optional services (database, Prefect agent).

6) ML Experimentation & Observations
  - Experiment scripts, training notebooks, and logging utilities are in `src/ml/experiments/`. Experiment outputs and comparisons are saved under `reports/` and `src/ml/artifacts/`.

Included ML tasks
-----------------
Per the assignment requirement to include multiple ML tasks, this repo contains examples and pipelines covering:
- Classification (binary/multiclass) — example models and training scripts in `src/ml/classification/`.
- Regression (numeric forecasting) — revenue prediction utilities in `src/ml/regression/`.
- Recommendation systems (collaborative filtering / NCF fallback) — `src/ml/recommender/` and API endpoints.
- Dimensionality reduction & visualization (PCA / t-SNE) — used in analysis scripts and `reports/` figures.
- Clustering & association (k-means, hierarchical, association mining) — `src/ml/clustering/` and analysis notebooks.
- Time-series analysis — utilities and example flows used for trend detection and forecasting in `src/ml/timeseries/`.
- Association — similar media discovery in `src/ml/association/`

Deliverables checklist
----------------------
The repository includes the core deliverables required by the course. For your final submission, make sure to include (and optionally record a short demo video showing each):
- FastAPI app and example endpoints (`src/api/`)
- Prefect workflows (`src/workflows/`)
- Dockerfile and `docker-compose.yml` (root)
- ML scripts and training code (`src/ml/`)
- Automated tests and DeepChecks suites (`tests/`)
- CI workflow definitions (`.github/workflows/`)

Privacy / Data Notes
--------------------
- The repository processes public metadata (e.g., MovieLens and TMDb mapping files) for research purposes. If you add external data, ensure you comply with the data provider's terms.
- The demo stores small amounts of browser-local preferences (localStorage) and a guest id used to demonstrate personalization; these are not linked to personal accounts by default.

Development notes and tips
-------------------------
- Frontend tweaks: `src/frontend/static/styles.css` and `script.js` contain the primary UI logic — use those for visual polish and responsive adjustments.
- Admin/analytics: `src/frontend/static/admin.html` contains chart wiring and model summary views used during evaluation.
- If you need to debug API routes, use the automatic docs provided by FastAPI at `/docs` when the server is running.



Contact / Maintainers
---------------------
Maintainer: repository owner (see repository metadata)

Acknowledgements
----------------
- MovieLens datasets are used for offline aggregation and research workflow examples.
- TMDb mappings and other public metadata are used where applicable to enrich examples.
