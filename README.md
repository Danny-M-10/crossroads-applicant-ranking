# Billy Heromans AI Applicant Ranking Tool

AI-powered candidate screening tool that reads resumes from a folder, scores candidates against weighted criteria using Claude AI, and produces ranked shortlists with professional reports.

## Quick Start

### Prerequisites

- Python 3.11+
- An Anthropic API key

**WeasyPrint system dependencies** (for PDF report generation):

macOS:
```bash
brew install pango gdk-pixbuf libffi
```

Ubuntu/Debian:
```bash
apt-get install -y libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0
```

### Setup

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and set your ANTHROPIC_API_KEY and RESUME_FOLDER_PATH
```

### Run

```bash
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000 in your browser.

## Usage

1. **Job Roles** come pre-configured for Billy Heromans (Route Driver, Warehouse Staff, Floral Designer, Inside Sales). Edit criteria weights as needed.

2. **Start a Ranking**: Click "Start New Ranking", select a job role, enter the path to a folder containing resume files (PDF/DOCX), and click "Start Ranking".

3. **Watch Progress**: The tool parses all resumes and scores each candidate against your weighted criteria using Claude AI. A live progress bar tracks the process.

4. **View Results**: Candidates are ranked by weighted total score. Each candidate shows per-criterion scores, justifications, a profile summary, and any red flags.

5. **Export Reports**: Download a professional PDF or HTML report of the top 10 candidates.

## Configuration

| Environment Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | (required) | Your Anthropic API key |
| `RESUME_FOLDER_PATH` | `./resumes` | Default folder path shown in the UI |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/ranker.db` | SQLite database URL |
| `CLAUDE_MODEL` | `claude-sonnet-4-20250514` | Claude model to use for scoring |
| `MAX_CONCURRENT_SCORES` | `5` | Max parallel Claude API calls |

## Architecture

- **FastAPI** backend with async SQLAlchemy + SQLite
- **Jinja2 + Tailwind CSS + HTMX** frontend (no JS build step)
- **pdfplumber** / **python-docx** for resume text extraction
- **Anthropic Claude API** for AI-powered scoring
- **WeasyPrint** for PDF report generation
