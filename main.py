from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import uvicorn, os, json, uuid, sqlite3, hashlib, pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List
import openai, requests
from pydantic import BaseModel
from jose import JWTError, jwt
from passlib.context import CryptContext
from pathlib import Path
import io, shutil
from dotenv import load_dotenv

load_dotenv()

# ============================================================================
# CONFIGURATION
# ============================================================================
SECRET_KEY = os.getenv("SECRET_KEY", "pharmalogix-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 hours
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "")

BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
DB_PATH = BASE_DIR / "pharmalogix.db"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

# ============================================================================
# DATABASE SETUP
# ============================================================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS companies (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        api_key TEXT UNIQUE,
        plan TEXT DEFAULT 'starter',
        created_at TEXT,
        n8n_webhook TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS data_files (
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
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS chat_history (
        id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS knowledge_docs (
        id TEXT PRIMARY KEY,
        company_id TEXT NOT NULL,
        name TEXT NOT NULL,
        doc_type TEXT,
        content TEXT,
        uploaded_at TEXT
    )''')
    conn.commit()
    conn.close()

# ============================================================================
# AUTH HELPERS
# ============================================================================
def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def create_access_token(data: dict):
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({**data, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)

def get_current_company(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        company_id = payload.get("sub")
        if not company_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT * FROM companies WHERE id=?", (company_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            raise HTTPException(status_code=401, detail="Company not found")
        cols = ["id","name","email","password_hash","api_key","plan","created_at","n8n_webhook"]
        return dict(zip(cols, row))
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

def get_company_by_api_key(api_key: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM companies WHERE api_key=?", (api_key,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    cols = ["id","name","email","password_hash","api_key","plan","created_at","n8n_webhook"]
    return dict(zip(cols, row))

# ============================================================================
# PYDANTIC MODELS
# ============================================================================
class RegisterRequest(BaseModel):
    company_name: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None

class EmailRequest(BaseModel):
    to: str
    subject: str
    message: str

class UpdateSettingsRequest(BaseModel):
    n8n_webhook: Optional[str] = None
    company_name: Optional[str] = None

# ============================================================================
# PHARMALOGIX SYSTEM PROMPT
# ============================================================================
PHARMALOGIX_SYSTEM_PROMPT = """You are PharmaLogix Copilot, a professional-grade AI assistant supporting U.S. Logistics, Distribution, and Supply Chain Operations for pharmaceutical companies. 

Your role is to analyze, summarize, and interpret operational logistics data uploaded by the user, providing audit-ready, compliant, and actionable insights. You combine data reasoning, procedural knowledge, and contextual understanding.

CAPABILITIES:
- Analyze uploaded logistics data (3PL performance, cold chain, inventory, audits, launches, finance, risk)
- Generate KPI summaries, trend analysis, and executive reports
- Identify compliance issues and suggest CAPA actions
- Support cold chain excursion management
- Track vendor/3PL performance (OTIF, damage rates, SLA compliance)
- Support audit readiness and recall management
- Monitor launch readiness for new products
- Send email reports when requested

DATA BEHAVIOR:
- When data has been uploaded, use it to answer quantitative questions
- Always reference specific data points, dates, and metrics in your responses
- If asked for a report or dashboard, structure it clearly with sections and tables
- For compliance questions, follow pharmaceutical distribution standards (GDP, FDA guidelines)

OUTPUT STYLE:
- All reports: structured, labeled by timeframe and source, executive-level
- Use tables for comparative data, bullet points for recommendations
- Always include data sources and date ranges in reports
- Flag critical issues (temperature excursions, failed audits, high damage rates) prominently

LIMITATIONS:
- Only answer questions related to logistics, supply chain, and distribution operations
- If asked something unrelated, respond: "I'm focused on pharmaceutical logistics operations. How can I help with your supply chain?"
- If data for a requested timeframe is not available, clearly state what data IS available
"""

# ============================================================================
# DATA PROCESSING
# ============================================================================
def process_uploaded_file(filepath: str, original_name: str) -> dict:
    """Process Excel or CSV file and return summary"""
    try:
        if original_name.endswith('.csv'):
            df = pd.read_csv(filepath)
        elif original_name.endswith(('.xlsx', '.xls')):
            # Get all sheets
            xl = pd.ExcelFile(filepath)
            sheets = xl.sheet_names
            summaries = []
            all_cols = []
            total_rows = 0
            for sheet in sheets:
                df = pd.read_excel(filepath, sheet_name=sheet)
                total_rows += len(df)
                all_cols.extend([f"{sheet}.{c}" for c in df.columns.tolist()])
                # Sample summary
                num_cols = df.select_dtypes(include='number').columns.tolist()
                stats = {}
                for col in num_cols[:5]:
                    stats[col] = {"mean": round(df[col].mean(), 2), "min": round(df[col].min(), 2), "max": round(df[col].max(), 2)}
                summaries.append(f"Sheet '{sheet}': {len(df)} rows, {len(df.columns)} columns. Columns: {', '.join(df.columns.tolist()[:10])}")
            return {
                "row_count": total_rows,
                "columns": json.dumps(all_cols[:50]),
                "summary": "\n".join(summaries)
            }
        else:
            return {"row_count": 0, "columns": "[]", "summary": "Unsupported file type"}
        
        # CSV processing
        num_cols = df.select_dtypes(include='number').columns.tolist()
        stats = {}
        for col in num_cols[:8]:
            if df[col].notna().sum() > 0:
                stats[col] = {"mean": round(df[col].mean(), 2), "min": round(df[col].min(), 2), "max": round(df[col].max(), 2)}
        
        summary = f"Dataset: {len(df)} rows, {len(df.columns)} columns.\n"
        summary += f"Columns: {', '.join(df.columns.tolist())}\n"
        if stats:
            summary += "Key statistics:\n"
            for col, s in stats.items():
                summary += f"  {col}: avg={s['mean']}, min={s['min']}, max={s['max']}\n"
        
        # Date range detection
        for col in df.columns:
            if 'date' in col.lower() or 'time' in col.lower():
                try:
                    dates = pd.to_datetime(df[col], errors='coerce').dropna()
                    if len(dates) > 0:
                        summary += f"Date range ({col}): {dates.min().strftime('%Y-%m-%d')} to {dates.max().strftime('%Y-%m-%d')}\n"
                except:
                    pass
        
        return {
            "row_count": len(df),
            "columns": json.dumps(df.columns.tolist()),
            "summary": summary
        }
    except Exception as e:
        return {"row_count": 0, "columns": "[]", "summary": f"Error processing file: {str(e)}"}

def get_data_context(company_id: str) -> str:
    """Get all uploaded data context for a company"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT filename, original_name, summary, row_count, uploaded_at FROM data_files WHERE company_id=?", (company_id,))
    files = c.fetchall()
    
    c.execute("SELECT name, doc_type, content FROM knowledge_docs WHERE company_id=?", (company_id,))
    docs = c.fetchall()
    conn.close()
    
    if not files and not docs:
        return "No data has been uploaded yet. Ask the user to upload their logistics data files (Excel or CSV)."
    
    context = "=== UPLOADED DATA CONTEXT ===\n\n"
    
    if files:
        context += "DATA FILES:\n"
        for f in files:
            context += f"\n📊 File: {f[1]} (uploaded {f[4][:10]})\n"
            context += f"   Rows: {f[3]}\n"
            context += f"   Summary: {f[2]}\n"
    
    if docs:
        context += "\n\nKNOWLEDGE DOCUMENTS:\n"
        for d in docs:
            context += f"\n📄 {d[0]} ({d[1]})\n"
            if d[2]:
                context += f"   {d[2][:500]}...\n"
    
    return context

def get_recent_chat_history(company_id: str, limit: int = 10) -> list:
    """Get recent chat history for context"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT role, content FROM chat_history WHERE company_id=? ORDER BY created_at DESC LIMIT ?", (company_id, limit))
    rows = c.fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

# ============================================================================
# FASTAPI APP SETUP
# ============================================================================
app = FastAPI(title="PharmaLogix API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    init_db()

# ============================================================================
# AUTH ROUTES
# ============================================================================
@app.post("/api/auth/register")
async def register(req: RegisterRequest):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        company_id = str(uuid.uuid4())
        api_key = "plx_" + str(uuid.uuid4()).replace("-", "")
        c.execute("INSERT INTO companies VALUES (?,?,?,?,?,?,?,?)", (
            company_id, req.company_name, req.email,
            get_password_hash(req.password), api_key, "starter",
            datetime.utcnow().isoformat(), ""
        ))
        conn.commit()
        token = create_access_token({"sub": company_id})
        return {"token": token, "api_key": api_key, "company_name": req.company_name}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Email already registered")
    finally:
        conn.close()

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM companies WHERE email=?", (req.email,))
    row = c.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    cols = ["id","name","email","password_hash","api_key","plan","created_at","n8n_webhook"]
    company = dict(zip(cols, row))
    if not verify_password(req.password, company["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": company["id"]})
    return {"token": token, "company_name": company["name"], "api_key": company["api_key"], "plan": company["plan"]}

@app.get("/api/auth/me")
async def get_me(company = Depends(get_current_company)):
    return {"id": company["id"], "name": company["name"], "email": company["email"], 
            "api_key": company["api_key"], "plan": company["plan"], "n8n_webhook": company["n8n_webhook"]}

# ============================================================================
# FILE UPLOAD ROUTES
# ============================================================================
@app.post("/api/files/upload")
async def upload_file(file: UploadFile = File(...), company = Depends(get_current_company)):
    try:
        allowed = ['.csv', '.xlsx', '.xls']
        ext = Path(file.filename).suffix.lower()
        if ext not in allowed:
            raise HTTPException(status_code=400, detail=f"File type {ext} not supported. Use CSV or Excel.")

        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        company_dir = UPLOAD_DIR / company["id"]
        company_dir.mkdir(parents=True, exist_ok=True)

        file_id = str(uuid.uuid4())
        safe_filename = f"{file_id}{ext}"
        filepath = company_dir / safe_filename

        content = await file.read()
        with open(filepath, "wb") as f:
            f.write(content)

        file_info = process_uploaded_file(str(filepath), file.filename)

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO data_files VALUES (?,?,?,?,?,?,?,?,?)", (
            file_id, company["id"], safe_filename, file.filename, ext,
            file_info["row_count"], file_info["columns"], file_info["summary"],
            datetime.utcnow().isoformat()
        ))
        conn.commit()
        conn.close()

        return {
            "id": file_id,
            "filename": file.filename,
            "row_count": file_info["row_count"],
            "summary": file_info["summary"],
            "uploaded_at": datetime.utcnow().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload error: {str(e)}")

@app.get("/api/files")
async def list_files(company = Depends(get_current_company)):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, original_name, file_type, row_count, uploaded_at FROM data_files WHERE company_id=? ORDER BY uploaded_at DESC", (company["id"],))
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "type": r[2], "rows": r[3], "uploaded_at": r[4]} for r in rows]

@app.delete("/api/files/{file_id}")
async def delete_file(file_id: str, company = Depends(get_current_company)):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT filename FROM data_files WHERE id=? AND company_id=?", (file_id, company["id"]))
    row = c.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    
    filepath = UPLOAD_DIR / company["id"] / row[0]
    if filepath.exists():
        filepath.unlink()
    
    c.execute("DELETE FROM data_files WHERE id=?", (file_id,))
    conn.commit()
    conn.close()
    return {"message": "File deleted"}

# ============================================================================
# CHAT ROUTE (MOST IMPORTANT)
# ============================================================================
@app.post("/api/chat")
async def chat(req: ChatRequest, company = Depends(get_current_company)):
    api_key = os.environ.get("OPENAI_API_KEY") or OPENAI_API_KEY
    if not api_key:
        raise HTTPException(status_code=500, detail="OpenAI API key not configured.")

    try:
        client = openai.OpenAI(api_key=api_key)
        data_context = get_data_context(company["id"])
        history = get_recent_chat_history(company["id"])
        system_msg = PHARMALOGIX_SYSTEM_PROMPT + f"\n\n{data_context}\n\nCompany: {company['name']}"
        messages = [{"role": "system", "content": system_msg}]
        messages.extend(history[-8:])
        messages.append({"role": "user", "content": req.message})

        try:
            response = client.chat.completions.create(
                model="gpt-4o", messages=messages, max_tokens=2000, temperature=0.3
            )
        except Exception:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo", messages=messages, max_tokens=2000, temperature=0.3
            )

        assistant_message = response.choices[0].message.content

    except openai.AuthenticationError:
        raise HTTPException(status_code=401, detail="Invalid OpenAI API key. Check your OPENAI_API_KEY in Railway Variables.")
    except openai.RateLimitError:
        raise HTTPException(status_code=429, detail="OpenAI rate limit. Add billing at platform.openai.com.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")
    
    # Save to history
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO chat_history VALUES (?,?,?,?,?)", (
        str(uuid.uuid4()), company["id"], "user", req.message, datetime.utcnow().isoformat()
    ))
    c.execute("INSERT INTO chat_history VALUES (?,?,?,?,?)", (
        str(uuid.uuid4()), company["id"], "assistant", assistant_message, datetime.utcnow().isoformat()
    ))
    conn.commit()
    conn.close()
    
    return {"response": assistant_message, "usage": response.usage.total_tokens}

@app.delete("/api/chat/history")
async def clear_history(company = Depends(get_current_company)):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM chat_history WHERE company_id=?", (company["id"],))
    conn.commit()
    conn.close()
    return {"message": "Chat history cleared"}

# ============================================================================
# EMAIL AND SETTINGS ROUTES
# ============================================================================
@app.post("/api/email/send")
async def send_email(req: EmailRequest, company = Depends(get_current_company)):
    webhook_url = company.get("n8n_webhook") or N8N_WEBHOOK_URL
    if not webhook_url:
        raise HTTPException(status_code=400, detail="No email webhook configured. Add your n8n webhook URL in Settings.")
    
    try:
        resp = requests.post(webhook_url, json={"to": req.to, "subject": req.subject, "message": req.message}, timeout=10)
        if resp.status_code == 200:
            return {"message": "Email sent successfully"}
        else:
            raise HTTPException(status_code=500, detail=f"Webhook returned {resp.status_code}")
    except requests.Timeout:
        raise HTTPException(status_code=500, detail="Email webhook timed out")

@app.put("/api/settings")
async def update_settings(req: UpdateSettingsRequest, company = Depends(get_current_company)):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if req.n8n_webhook is not None:
        c.execute("UPDATE companies SET n8n_webhook=? WHERE id=?", (req.n8n_webhook, company["id"]))
    if req.company_name is not None:
        c.execute("UPDATE companies SET name=? WHERE id=?", (req.company_name, company["id"]))
    conn.commit()
    conn.close()
    return {"message": "Settings updated"}

@app.get("/api/stats")
async def get_stats(company = Depends(get_current_company)):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM data_files WHERE company_id=?", (company["id"],))
    file_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM chat_history WHERE company_id=? AND role='user'", (company["id"],))
    message_count = c.fetchone()[0]
    c.execute("SELECT SUM(row_count) FROM data_files WHERE company_id=?", (company["id"],))
    total_rows = c.fetchone()[0] or 0
    conn.close()
    return {"files": file_count, "messages": message_count, "data_rows": total_rows}

# ============================================================================
# HEALTH CHECK
# ============================================================================
@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "PharmaLogix"}

# ============================================================================
# STATIC FILE SERVING
# ============================================================================
@app.get("/", response_class=HTMLResponse)
async def serve_app():
    # Look for index.html in same directory as main.py, or in static/ subfolder
    for candidate in [BASE_DIR / "index.html", BASE_DIR / "static" / "index.html"]:
        if candidate.exists():
            return FileResponse(str(candidate))
    return HTMLResponse("<h1>PharmaLogix API</h1><p>Frontend not found. Check /docs for API.</p>")

@app.get("/{full_path:path}", response_class=HTMLResponse)
async def catch_all(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404)
    for candidate in [BASE_DIR / "index.html", BASE_DIR / "static" / "index.html"]:
        if candidate.exists():
            return FileResponse(str(candidate))
    raise HTTPException(status_code=404)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=False)
