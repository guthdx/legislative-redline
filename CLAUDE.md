# CLAUDE.md - Legislative Redline Tool

## Overview

A web application that compares proposed statutory amendments against current federal law (USC and CFR), displaying visual redline comparisons with strikethrough (red) for deletions and highlights (green) for insertions.

## Quick Start

```bash
# Start development environment
docker compose up -d

# Backend: http://redline-api.localhost (port 8004)
# Frontend: http://redline.localhost (port 5176)
# Database: localhost:5438
```

## Architecture

### Tech Stack
- **Backend**: FastAPI (Python 3.13)
- **Frontend**: React + Vite + Tailwind CSS
- **Database**: PostgreSQL 16
- **Proxy**: Traefik (shared with other Iyeska projects)

### Ports
| Service | Port | Traefik Route |
|---------|------|---------------|
| PostgreSQL | 5438 | N/A (internal) |
| Backend | 8004 | http://redline-api.localhost |
| Frontend | 5176 | http://redline.localhost |

### Data Sources
| Source | Purpose | Auth |
|--------|---------|------|
| **govinfo.gov** | USC (United States Code) | Free API key |
| **eCFR.gov** | CFR (Code of Federal Regulations) | None required |

## Project Structure

```
legislative_redline/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entry point
│   │   ├── core/config.py       # Pydantic settings
│   │   ├── api/v1/              # API routes
│   │   ├── models/              # SQLAlchemy models
│   │   ├── schemas/             # Pydantic schemas
│   │   ├── services/            # Business logic
│   │   │   ├── document_parser.py    # PDF/DOCX parsing
│   │   │   ├── citation_detector.py  # Regex detection
│   │   │   ├── statute_fetcher.py    # API integration
│   │   │   ├── amendment_parser.py   # Pattern matching
│   │   │   └── diff_generator.py     # Redline output
│   │   └── db/                  # Database session
│   ├── alembic/                 # Migrations
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/          # Reusable UI
│   │   ├── pages/               # Route pages
│   │   └── services/api.js      # API client
│   ├── Dockerfile
│   └── package.json
├── docs/                      # Sample legislative documents
│   ├── PAT26007.docx          # Farm bill amendment specs
│   └── *.pdf, *.html          # Additional test documents
├── docker-compose.yml
└── .env.example
```

## Core Workflow

1. **Upload**: User uploads PDF/DOCX with proposed amendments
2. **Parse**: Extract text with PyMuPDF or python-docx
3. **Detect**: Find USC/CFR citations using regex patterns
4. **Fetch**: Retrieve current law from govinfo.gov/eCFR.gov
5. **Compare**: Apply amendments and generate diff with diff-match-patch
6. **Display**: Render redline with strikethrough (red) and highlights (green)

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/health` | GET | Health check |
| `/api/v1/documents/upload` | POST | Upload PDF/DOCX |
| `/api/v1/documents/{id}/parse` | POST | Parse & detect citations |
| `/api/v1/documents/{id}/citations` | GET | List detected citations |
| `/api/v1/citations/{id}/fetch-statute` | POST | Fetch current law |
| `/api/v1/documents/{id}/compare` | POST | Generate redline |
| `/api/v1/documents/{id}/result` | GET | Get comparison results |

## Citation Patterns

### USC (United States Code)
- `26 U.S.C. § 501(c)(3)`
- `26 USC 501`
- `Title 26, Section 501`
- `section 501 of title 26`

### CFR (Code of Federal Regulations)
- `42 C.F.R. § 482.12`
- `42 CFR 482.12`

### Public Law
- `Pub. L. 117-169`
- `Public Law 117-169`

## Amendment Patterns

The amendment parser (`services/amendment_parser.py`) detects the following patterns:

### Core Patterns (High Frequency)

| Type | Pattern | Example |
|------|---------|---------|
| `strike_insert` | striking X and inserting Y | "by striking 'December 31, 2023' and inserting 'December 31, 2029'" |
| `insert_after` | inserting after X the following | "by inserting after 'eligible entity' the following:" |
| `read_as_follows` | amended to read as follows | "Section 501(a) is amended to read as follows:" |
| `add_at_end` | adding at the end | "by adding at the end the following new paragraph:" |
| `strike` | striking X (deletion only) | "by striking 'and' at the end" |

### Extended Patterns

| Type | Pattern | Example |
|------|---------|---------|
| `further_amended` | is further amended | "Section 1204 is further amended by adding..." |
| `each_place_appears` | X each place it appears | "by striking 'FY2023' each place it appears" |
| `redesignate` | redesignating X as Y | "by redesignating subsection (c) as subsection (d)" |
| `insert_before` | inserting before X | "by inserting before paragraph (1) the following:" |
| `add_at_beginning` | adding at the beginning | "by inserting at the beginning the following:" |

### Structural Targets

The parser handles amendments targeting specific structural elements:
- Subsections: `(a)`, `(b)`, etc.
- Paragraphs: `(1)`, `(2)`, etc.
- Subparagraphs: `(A)`, `(B)`, etc.
- Clauses: `(i)`, `(ii)`, etc.

### Quote Handling

The parser normalizes smart quotes before processing:
- `"` `"` → `"`  (smart double quotes)
- `'` `'` → `'`  (smart single quotes)
- `′` `″` → `'` `"`  (prime characters)

### Phase 2: Structural Operations (Jan 2025)

| Type | Pattern | Example |
|------|---------|---------|
| `redesignate` (range) | paragraphs (X) through (Y) as | "by redesignating paragraphs (2) through (6) as paragraphs (3) through (7)" |
| `designate` | designating X as Y | "by designating the matter preceding paragraph (1) as subsection (a)" |
| `strike_redesignate` | strike X and redesignate | "by striking paragraph (2) and redesignating paragraphs (3) through (5)" |

### Phase 3: Bug Fixes (Jan 2025)

Fixed three critical bugs affecting amendment parsing:

1. **Pattern capture after newlines** - `STRIKE_INSERT_PATTERNS` now captures replacement text that appears after `\n\n` using `re.DOTALL`
2. **Structural element type** - Parser now correctly identifies "paragraph" vs "subparagraph" instead of hardcoding
3. **Context extraction truncation** - `SECTION_BOUNDARY_PATTERN` in `citation_detector.py` no longer incorrectly matches amendment instructions like "(A) by striking..." as section boundaries

### Coverage Analysis (Jan 2025)

Based on analysis of 2.3M+ characters of legislative text:
- **~99.7% pattern coverage** after Phase 1 + 2 + 3
- 598 amendment operations analyzed
- Phase 1 added: further_amended, quote normalization
- Phase 2 added: redesignate ranges, designate patterns
- Phase 3 fixed: multiline inserts, structural type capture, context truncation

## Development

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Start dev server
uvicorn app.main:app --reload --port 8004
```

### Frontend

```bash
cd frontend
npm install
npm run dev  # Starts on port 5176
```

### Database

```bash
# Connect to PostgreSQL
docker compose exec db psql -U postgres -d redline_db

# Reset database
docker compose down -v
docker compose up -d
```

## Environment Variables

```bash
# Database
POSTGRES_USER=postgres
POSTGRES_PASSWORD=localdev
POSTGRES_DB=redline_db
POSTGRES_HOST=db
POSTGRES_PORT=5432

# External APIs
GOVINFO_API_KEY=your_key  # Get free key at api.data.gov

# App Settings
DOCUMENT_RETENTION_HOURS=24
STATUTE_CACHE_DAYS=7
```

## Key Dependencies

### Backend
- `fastapi` - Web framework
- `pymupdf` - PDF parsing (fast, structure-preserving)
- `python-docx` - DOCX parsing
- `httpx` - Async HTTP client
- `diff-match-patch` - Text diffing
- `sqlalchemy` + `asyncpg` - Database

### Frontend
- `react` + `react-router-dom` - UI framework
- `@tanstack/react-query` - Server state
- `axios` - HTTP client
- `react-dropzone` - File upload
- `tailwindcss` - Styling

## Testing

```bash
# Backend tests
cd backend
pytest

# Frontend tests
cd frontend
npm test
```

## Troubleshooting

### GovInfo API returns 429
Rate limit exceeded. Wait 1 hour or check `X-RateLimit-Remaining` header.

### Citation not detected
Check regex patterns in `services/citation_detector.py`. Add new pattern if needed.

### PDF parsing fails
Some PDFs are image-based. Enable OCR with `pymupdf` + `pytesseract`.

### Statute not found
Citation may reference a repealed section or use non-standard format. Check logs.

### Amendment shows "unknown" type with no changes
This was fixed in Phase 3. Common causes were:
1. **Context truncation** - The `SECTION_BOUNDARY_PATTERN` was incorrectly matching amendment instructions like "(A) by striking..." as section boundaries, truncating context to ~118 chars
2. **Multiline insert text** - Patterns weren't capturing replacement text after `\n\n`
3. **Structural type hardcoding** - Code was using "subparagraph" even when "paragraph" was matched

If you see this issue, ensure you have the latest code from commits `e530b5a`, `36daf2a`, `8c630a7`.

### Definitional references showing as amendments
Citations that are definitional (e.g., "has the meaning given in section X") should show as "unknown" with no changes. The system correctly identifies these and displays: "This citation is a definitional reference."
