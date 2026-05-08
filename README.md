# AnalizePub



Free EPUB accessibility audit tool. Upload an EPUB (EPUB 2 or EPUB 3) and get a detailed accessibility report — without modifying the original file.

AnalizePub is the free companion to [AccesPub](https://accespub.app). AccesPub *fixes* EPUBs automatically; AnalizePub *only* analyses and reports. Both share the same analysis engine.

- **Production URL:** https://analizepub.app
- **Owner:** Alberto Barajas (info@abserveis.net)
- **License:** MIT (engine reused from AccesPub)

---

## What it does

- Detects every accessibility issue in an EPUB (EPUB 2 and EPUB 3).
- Runs EPUBCheck and surfaces its errors and warnings.
- Generates a downloadable HTML and PDF report.
- Shows compliance against WCAG 2.1 AA and the European Accessibility Act (EAA).
- Three at-a-glance status indicators: EAA, WCAG, EPUBCheck.

## What it does NOT do

- It does **not** modify the uploaded EPUB.
- It does **not** convert EPUB 2 to EPUB 3.
- It does **not** apply any fixes (use AccesPub for that).
- No registration, no licences, no credits.

---

## Stack

- Python 3.11
- `http.server` standard library (`ThreadingHTTPServer`) — no Flask
- `lxml` for XML/EPUB parsing
- `epubcheck` Python wrapper (requires Java — `default-jre-headless`)
- `weasyprint` for PDF report rendering
- Lucide icons (CDN)
- UI in ES / EN / CA

## Repository layout

```
AnalizePub/
├── README.md
├── CLAUDE.md                     ← project context for the AI coding assistant
├── Dockerfile                    ← Python 3.11 + Java + WeasyPrint deps
├── fly.toml                      ← Fly.io app config (region: ams)
├── requirements.txt
├── .env.example
├── .gitignore
├── .github/workflows/deploy.yml  ← CI/CD: push to main → Fly.io
│
├── dashboard/
│   ├── app.py                    ← main HTTP server (~1000 lines)
│   ├── i18n.py                   ← ES / EN / CA translations
│   └── static/
│       └── style.css
│
└── epub_a11y/                    ← read-only analysis engine (from AccesPub)
    ├── __init__.py
    ├── analyzer.py
    ├── models.py
    ├── constants.py
    └── fixes/
        ├── contrast.py
        └── metadata.py
```

---

## Local development

```bash
# 1. Clone & install
git clone https://github.com/abserveis/AnalizePub.git
cd AnalizePub
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. (Optional) install Java for EPUBCheck
#   macOS:  brew install openjdk
#   Debian: sudo apt install default-jre-headless

# 3. Run
cp .env.example .env
python -m dashboard.app
# → http://localhost:8080
```

## Deployment

```bash
fly deploy --remote-only --app analizepub
```

CI/CD: every push to `main` deploys automatically via GitHub Actions.

---

## License

MIT — see [LICENSE](LICENSE).

The analysis engine in `epub_a11y/` is shared with AccesPub.
