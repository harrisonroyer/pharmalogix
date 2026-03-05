# PharmaLogix - Pharmaceutical Logistics AI Copilot

A white-label SaaS web application providing AI-powered pharmaceutical supply chain and logistics intelligence. Built with FastAPI, React, SQLite, and OpenAI GPT-4o.

## Features

- **AI-Powered Chat Copilot**: Analyze logistics data with GPT-4o, ask KPI questions, identify compliance issues
- **Multi-Tenant Architecture**: Complete tenant isolation with JWT authentication
- **Data Upload**: Support for CSV and Excel files with automatic processing and context retention
- **Email Integration**: Send reports via n8n webhooks
- **API Key Authentication**: Programmatic access to the copilot
- **Admin Dashboard**: Company settings, usage stats, API key management
- **Beautiful UI**: Dark navy theme, responsive design, professional pharmaceutical branding

## Tech Stack

**Backend**:
- FastAPI 0.104.1
- SQLite (multi-tenant database)
- OpenAI API (GPT-4o)
- Python-Jose (JWT)
- Pandas (data processing)
- Uvicorn (ASGI server)

**Frontend**:
- React 18 (CDN)
- Single HTML file
- No build process required
- Responsive design

**Infrastructure**:
- Docker & Docker Compose
- Railway.app compatible
- Environment-based configuration

## Project Structure

```
pharmalogix/
├── backend/
│   ├── main.py                 # FastAPI application
│   ├── requirements.txt         # Python dependencies
│   ├── Dockerfile              # Container definition
│   ├── pharmalogix.db          # SQLite database (created at runtime)
│   ├── uploads/                # User file uploads (created at runtime)
│   └── static/
│       └── index.html          # React SPA
├── docker-compose.yml          # Docker Compose orchestration
├── railway.toml                # Railway.app deployment config
├── .env.example                # Environment variables template
└── README.md                   # This file
```

## Quick Start

### 1. Local Development

```bash
# Clone and navigate to directory
cd pharmalogix/backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export OPENAI_API_KEY="sk-..."
export SECRET_KEY="your-random-secret-key"

# Run server
python main.py
```

Visit `http://localhost:8000` in your browser.

### 2. Docker Compose

```bash
# From pharmalogix root directory
cp .env.example .env
# Edit .env with your API keys

docker-compose up --build
```

Access at `http://localhost:8000`

### 3. Railway.app Deployment

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and create project
railway login
railway init

# Deploy
railway up
```

Set environment variables in Railway dashboard:
- `OPENAI_API_KEY`
- `SECRET_KEY`
- `N8N_WEBHOOK_URL` (optional)

## API Endpoints

### Authentication

**POST /api/auth/register**
```json
{
  "company_name": "Acme Pharma",
  "email": "admin@acme.com",
  "password": "secure-password"
}
```
Response: `{ "token": "jwt...", "api_key": "plx_...", "company_name": "..." }`

**POST /api/auth/login**
```json
{
  "email": "admin@acme.com",
  "password": "secure-password"
}
```
Response: `{ "token": "jwt...", "company_name": "...", "api_key": "plx_...", "plan": "starter" }`

**GET /api/auth/me**
Headers: `Authorization: Bearer {token}`
Response: Company information and API key

### Chat

**POST /api/chat**
```json
{
  "message": "What are our OTIF metrics for Q1?"
}
```
Response: `{ "response": "Based on your uploaded data...", "usage": 2150 }`

**DELETE /api/chat/history**
Clear all conversation history for the company

### File Management

**POST /api/files/upload**
Multipart form with file field. Supported: CSV, XLSX, XLS

**GET /api/files**
List all uploaded files

**DELETE /api/files/{file_id}**
Delete a specific file

### Settings

**PUT /api/settings**
```json
{
  "company_name": "New Name",
  "n8n_webhook": "https://..."
}
```

**GET /api/stats**
Response: `{ "files": 5, "messages": 42, "data_rows": 15000 }`

## System Prompt

The copilot is configured with a comprehensive pharmaceutical logistics system prompt covering:

- 3PL performance analysis
- Cold chain excursion management
- Inventory and audit tracking
- Launch readiness assessment
- Compliance and CAPA recommendations
- KPI summarization and trend analysis
- Vendor/3PL SLA compliance monitoring
- Recall management support

Data uploaded by users is automatically included in the AI context for accurate, data-driven responses.

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | OpenAI API key (GPT-4o) |
| `SECRET_KEY` | Yes | JWT signing key (change in production!) |
| `N8N_WEBHOOK_URL` | No | n8n webhook for email integration |
| `PORT` | No | Server port (default: 8000) |

## Database

SQLite database with 4 tables:

- **companies**: Tenant companies with auth and API keys
- **data_files**: Uploaded files and metadata
- **chat_history**: Conversation history per company
- **knowledge_docs**: Custom knowledge documents

Auto-initialized on startup. Database file stored at `backend/pharmalogix.db`

## File Upload Processing

Automatically processes:
- **CSV**: Reads with pandas, detects numeric columns and date ranges
- **Excel**: Processes all sheets, aggregates statistics
- **Summary**: Generates preview with row counts, columns, and key statistics

Files stored in `backend/uploads/{company_id}/` with unique IDs.

## Email Integration (Optional)

To enable email reports:

1. Create n8n workflow with webhook trigger
2. Configure email node
3. Add webhook URL to settings
4. Send reports via API or frontend

## Development

### Code Structure

**main.py** organized in sections:
1. Imports & Configuration
2. Database Setup
3. Auth Helpers
4. Pydantic Models
5. System Prompt
6. Data Processing
7. FastAPI App Setup
8. Auth Routes
9. File Upload Routes
10. Chat Route (most important)
11. Email & Settings Routes
12. Static File Serving

### Modifying the System Prompt

Edit `PHARMALOGIX_SYSTEM_PROMPT` in `main.py` to customize AI behavior:

```python
PHARMALOGIX_SYSTEM_PROMPT = """Your custom instructions here..."""
```

### Adding New Routes

Use the FastAPI pattern:

```python
@app.post("/api/new-endpoint")
async def new_endpoint(company = Depends(get_current_company)):
    # company dict contains: id, name, email, api_key, plan, n8n_webhook
    return {"result": "success"}
```

## Security Considerations

- JWT tokens expire after 24 hours
- Passwords hashed with bcrypt
- SQLite enforces multi-tenancy via company_id
- No user data logged to stdout
- HTTPS recommended in production
- API keys should be regenerated periodically

## Performance

- Vector database queries: instant (no vector DB, uses embeddings context)
- File processing: < 1s for most files
- Chat responses: 2-5s (depends on OpenAI latency)
- Database: SQLite suitable for < 10k active companies
- Scaling: Can migrate to PostgreSQL for large deployments

## Troubleshooting

**No OpenAI responses**: Check `OPENAI_API_KEY` environment variable

**Database locked**: SQLite has write limitations. Migrate to PostgreSQL for production

**File upload fails**: Check file size and type. Max tested: 10MB Excel files

**Chat mentions no data**: Upload files to the Data section first

## License

Proprietary - PharmaLogix SaaS Platform

## Support

For issues and feature requests, contact the development team.

---

Built with attention to pharmaceutical compliance standards (GDP, FDA guidelines). Always review AI-generated compliance recommendations with your legal team.
