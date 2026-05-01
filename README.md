# Budget Excel analytics

Streamlit app that ingests Union Budget **SBE** Excel exports, parses line items, and charts totals by period, demand (ministry), and sheet subsection.

## Run locally

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Open <http://localhost:8501>. Sample `sbe*.xlsx` files in this repo load when **Load all `.xlsx` from this folder** is on.

## Deploy — Streamlit Community Cloud (quickest)

1. Push this repository to GitHub (for example [dhruvpd77/budget](https://github.com/dhruvpd77/budget)).
2. Sign in at [Streamlit Community Cloud](https://share.streamlit.io/).
3. **New app** → pick the repo and branch → **Main file path:** `app.py`.
4. **Deploy.**  
   - Python deps come from `requirements.txt`.  
   - Server options live in [`.streamlit/config.toml`](.streamlit/config.toml).  
   - Optional secrets: copy [`.streamlit/secrets.toml.example`](.streamlit/secrets.toml.example) to **Secrets** in the Cloud UI (this app does not require keys today).

## Deploy — Docker

```bash
docker compose up --build
```

Then open <http://localhost:8501>.

For a single image:

```bash
docker build -t budget-app .
docker run --rm -p 8501:8501 budget-app
```

Hosts that inject a dynamic port (Render, Railway, Fly) should set `PORT`; the image CMD already uses `${PORT:-8501}`.

## Deploy — Render

- **Option A:** In the Render dashboard, create a **Web Service** from this repo, use **Docker** and point to the [`Dockerfile`](Dockerfile), or use the blueprint file [`render.yaml`](render.yaml).
- **Option B:** **Native Python** — build command: `pip install -r requirements.txt`; start command:  
  `streamlit run app.py --server.address=0.0.0.0 --server.port=$PORT`

Health check path (if asked): `/_stcore/health`

## Project layout

| Path | Purpose |
|------|--------|
| `app.py` | Streamlit UI |
| `budget_parser.py` | SBE Excel → tidy rows |
| `requirements.txt` | Dependencies |
| `.streamlit/config.toml` | Streamlit server & theme |
| `Dockerfile` / `docker-compose.yml` | Container run |
