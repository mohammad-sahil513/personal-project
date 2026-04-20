# AI SDLC — Frontend

Enterprise-grade document generation UI. Built with React + TypeScript + Tailwind CSS.
EY-inspired design: black, white, yellow `#FFD400`.

## Stack

- React 18 + Vite + TypeScript
- Tailwind CSS (custom EY theme)
- Zustand (state management)
- Axios (API calls — proxied to `localhost:8000`)
- react-markdown + remark-gfm (DOCX-like viewer)
- lucide-react (icons)

## Setup

```bash
npm install
npm run dev
```

App runs at **http://localhost:3000**  
Backend must be running at **http://localhost:8001**

## API Contract Expected

```
POST   /jobs                                    — Create job
POST   /jobs/{id}/upload                        — Upload BRD file
POST   /jobs/{id}/start                         — Start pipeline
GET    /jobs/{id}/progress                      — Poll progress
GET    /jobs/{id}/documents                     — Get document structure
GET    /jobs/{id}/documents/{type}/sections/{sid} — Get section content
GET    /jobs/{id}/download/all                  — Download ZIP
GET    /jobs/{id}/download/{type}               — Download individual DOCX

GET    /templates                               — List templates
POST   /templates/upload                        — Upload custom template
```

## 3 Pages

| Page | Route | Purpose |
|------|-------|---------|
| Upload | `/` | Upload BRD, select docs, pick template |
| Progress | `/progress` | Live progress bar with polling |
| Output | `/output` | DOCX-like section viewer + download |

## DOCX Viewer

The viewer renders Markdown as a white page on a gray canvas — mimicking Word.
- Page breaks: insert `<!-- PAGE_BREAK -->` in your Markdown
- Images: use full URLs in Markdown `![alt](https://your-storage/image.png)`
- Styles: `.docx-prose` class in `index.css` — fully customisable

## Notes

- Vite proxies `/api/*` → `localhost:8000` (but all API calls use full URL directly)
- CORS must be enabled on your FastAPI backend: `allow_origins=["http://localhost:5173"]`
