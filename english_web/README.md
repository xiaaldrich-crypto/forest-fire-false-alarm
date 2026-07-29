# ForestGuard — English Web UI

Standalone **English** front-end for overseas use. The Chinese UI is unchanged.

## Location

```text
english_web/
├── README.md
├── templates/index.html   # English page
└── static/
    ├── style.css          # Same look & layout (Latin fonts)
    └── app.js             # English copy + label localization
```

## How to open

Start the app as usual, then open the English page:

```bash
cd ~/Desktop/forest-fire-false-alarm
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

| UI | URL |
|----|-----|
| Chinese (original) | http://127.0.0.1:8000/ |
| **English** | **http://127.0.0.1:8000/en** |

Static assets: `/static-en/…` (not under `/en/…`, so the page route never blocks them).

## Translation notes

| Chinese (system) | English (UI) |
|------------------|--------------|
| 疑似真实火情 | Suspected Real Fire |
| 疑似误报 | Suspected False Alarm |
| 建议人工复核 | Recommend Human Review |
| 强光误报 | Strong-light / glare false alarm |
| 祭祀用火误报 | Ritual / sacrificial fire false alarm |
| 农业用火误报 | Agricultural burning false alarm |
| 工厂排气误报 | Industrial exhaust false alarm |
| 云雾误报 | Cloud / fog false alarm |

Verdicts, false-alarm types, and common fusion phrases from the API are localized in the browser so the page stays fully English for overseas reviewers. Layout, colors, and interaction flow match the Chinese product UI.
