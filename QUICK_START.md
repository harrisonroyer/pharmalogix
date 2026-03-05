# PharmaLogix - Quick Start Guide

## Files Created

```
/sessions/determined-keen-wright/pharmalogix/
├── backend/
│   ├── main.py                 (543 lines, 24KB) - Complete FastAPI app
│   ├── requirements.txt         (228 bytes) - All Python dependencies
│   ├── Dockerfile              (162 bytes) - Container configuration
│   ├── pharmalogix.db          (created at runtime) - SQLite database
│   ├── uploads/                (created at runtime) - File storage
│   └── static/
│       └── index.html          (1,399 lines, 52KB) - React SPA
├── docker-compose.yml          (336 bytes) - Orchestration
├── railway.toml                (230 bytes) - Railway.app config
├── .env.example                (191 bytes) - Environment template
├── README.md                   (comprehensive docs)
└── QUICK_START.md              (this file)
```

## What Was Built

### Backend (main.py)
- FastAPI server with CORS enabled
- SQLite multi-tenant database
- JWT authentication with 24-hour tokens
- OpenAI GPT-4o integration
- File upload processing (CSV, Excel)
- Email webhook integration (n8n)
- RESTful API (13 endpoints)

### Frontend (index.html)
- Single-page React 18 app (no build process)
- 4 main views: Chat, Data, Settings, API Docs
- Beautiful dark navy theme (#0a1628, #1e3a5f, #2563eb)
- Responsive design (desktop, tablet)
- Drag-and-drop file upload
- Real-time chat with message history
- API key management with reveal/copy
- Usage statistics dashboard

### Database (SQLite)
- companies (tenant accounts with API keys)
- data_files (uploaded files with metadata)
- chat_history (conversation history)
- knowledge_docs (custom documents)

## Quick Start Options

### Option 1: Local Python (Recommended for Development)

```bash
cd /sessions/determined-keen-wright/pharmalogix/backend

# Install dependencies
pip install -r requirements.txt

# Set environment
export OPENAI_API_KEY="sk-..."
export SECRET_KEY="my-secret-key-change-this"

# Run
python main.py
```

Open http://localhost:8000

### Option 2: Docker Compose

```bash
cd /sessions/determined-keen-wright/pharmalogix

# Create .env file
cp .env.example .env
# Edit .env with your API keys

# Run
docker-compose up --build
```

Open http://localhost:8000

### Option 3: Railway.app (Production)

1. Push to GitHub
2. Connect repo to Railway
3. Add environment variables in Railway dashboard
4. Deploy automatically

## Key Features

**Chat Interface**
- Analyzes uploaded logistics data
- Pharmaceutical-focused system prompt
- Tracks conversation history per tenant
- Renders markdown-like formatting

**File Management**
- Upload CSV or Excel files
- Auto-processes data (counts rows, detects dates, statistics)
- Shows file metadata and summary
- Stores files with company isolation

**Multi-Tenancy**
- Separate account for each pharmaceutical company
- JWT tokens expire after 24 hours
- API keys for programmatic access
- Complete data isolation by company_id

**Email Integration (Optional)**
- Send reports via n8n webhooks
- Configured in Settings
- Used by copilot or API users

## API Examples

### Login
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@pharma.com",
    "password": "password123"
  }'
```

Response:
```json
{
  "token": "eyJhbGc...",
  "company_name": "Acme Pharma",
  "api_key": "plx_abc123...",
  "plan": "starter"
}
```

### Chat
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Authorization: Bearer eyJhbGc..." \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What are our cold chain compliance metrics?"
  }'
```

### Upload File
```bash
curl -X POST http://localhost:8000/api/files/upload \
  -H "Authorization: Bearer eyJhbGc..." \
  -F "file=@logistics_data.csv"
```

## Environment Variables

| Variable | Required | Default |
|----------|----------|---------|
| OPENAI_API_KEY | Yes | (none) |
| SECRET_KEY | No | pharmalogix-secret-key-change-in-production |
| N8N_WEBHOOK_URL | No | (empty) |
| PORT | No | 8000 |

## Database Schema

### companies
```sql
CREATE TABLE companies (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  api_key TEXT UNIQUE,
  plan TEXT DEFAULT 'starter',
  created_at TEXT,
  n8n_webhook TEXT
)
```

### data_files
```sql
CREATE TABLE data_files (
  id TEXT PRIMARY KEY,
  company_id TEXT NOT NULL,
  filename TEXT NOT NULL,
  original_name TEXT NOT NULL,
  file_type TEXT,
  row_count INTEGER,
  columns TEXT,
  summary TEXT,
  uploaded_at TEXT,
  FOREIGN KEY (company_id) REFERENCES companies(id)
)
```

## System Prompt Highlights

The PharmaLogix copilot is specialized for:
- 3PL performance analysis (OTIF, damage rates)
- Cold chain excursion management
- Inventory and audit tracking
- Launch readiness assessment
- Compliance and CAPA recommendations
- KPI summarization and trend analysis
- Vendor/3PL SLA compliance
- Recall management support

All uploaded data is automatically included in the AI context.

## Testing the App

1. **Register**: Create account with company name, email, password
2. **Upload Data**: Go to Data tab, upload CSV or Excel
3. **Chat**: Ask questions about your data
4. **Settings**: Configure email webhook, see API key, check stats
5. **API Docs**: See code examples for integrations

## Troubleshooting

**"OpenAI API key not configured"**
- Set OPENAI_API_KEY environment variable
- Example: `export OPENAI_API_KEY="sk-proj-..."`

**"Database is locked"**
- Close other connections to pharmalogix.db
- For production, migrate to PostgreSQL

**"File upload fails"**
- Check file size (tested up to 10MB)
- Ensure file is CSV or Excel format
- Look at server logs for details

**"No messages sent"**
- Check JWT token is valid (expires after 24 hours)
- Verify Authorization header format: `Bearer TOKEN`
- Check company_id matches between token and request

## Architecture Notes

- **Stateless API**: No memory between requests except database
- **Single HTML File**: No build process, React from CDN
- **SQLite**: Suitable for < 10k active companies; use PostgreSQL for larger scale
- **JWT Tokens**: 24-hour expiration, no refresh tokens needed for SPA
- **File Storage**: Server-side at backend/uploads/{company_id}/
- **Async**: FastAPI handles concurrent requests efficiently

## Production Deployment

Before deploying to production:

1. Change SECRET_KEY to a random string (use openssl: `openssl rand -hex 32`)
2. Set OPENAI_API_KEY from your OpenAI account
3. Configure HTTPS/TLS (Railway handles this)
4. Add N8N_WEBHOOK_URL if using email features
5. Consider migrating from SQLite to PostgreSQL
6. Set up monitoring and logging
7. Add rate limiting for API endpoints
8. Implement request logging

## Support & Customization

To customize:

1. **System Prompt**: Edit PHARMALOGIX_SYSTEM_PROMPT in main.py
2. **UI Styling**: Edit CSS in index.html (dark navy theme)
3. **Database Schema**: Modify init_db() function
4. **API Routes**: Add new @app.post/@app.get decorators
5. **Frontend Views**: Add new React components in index.html

---

**Total Size**: ~80KB (24KB backend + 52KB frontend + deps)
**Python Version**: 3.11+
**No build process required**: Pure Python + HTML/React CDN
**Ready for production**: Docker, Railway.app, or traditional hosting

Enjoy your PharmaLogix SaaS application!
