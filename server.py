"""ThaiNDC AI Learning Assistant Server with Auth, Dashboard, DOCX Download & Public Sharing."""
import os, sqlite3, json, uuid, tempfile, time, re, urllib.parse, codecs
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pptx import Presentation
from pypdf import PdfReader
from google import genai
from google.genai import types

from auth import (
    hash_password, verify_password, init_auth_tables,
    create_session, get_user_by_token, delete_session
)
from docx_generator import (
    build_executive_brief_docx,
    build_transcript_docx,
    build_transcript_text
)

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
DATA.mkdir(exist_ok=True)
DB = DATA / 'lectures.sqlite3'

app = FastAPI(title='ThaiNDC AI Learning Assistant')
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')

def conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute('''
        CREATE TABLE IF NOT EXISTS lectures (
            id TEXT PRIMARY KEY,
            date TEXT NOT NULL,
            title TEXT NOT NULL,
            lecturer TEXT,
            notes TEXT,
            source_text TEXT,
            transcript TEXT,
            brief TEXT,
            created_at TEXT NOT NULL
        )
    ''')
    init_auth_tables(c)
    return c

# Initialize database tables immediately
with conn() as _c:
    pass

def ai():
    key = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
    if not key:
        raise HTTPException(400, 'กรุณาตั้งค่า GEMINI_API_KEY ที่ฝั่งเซิร์ฟเวอร์')
    return genai.Client(api_key=key)

AUDIO_MIME = {
    '.mp3': 'audio/mpeg',
    '.mpeg': 'audio/mpeg',
    '.mpga': 'audio/mpeg',
    '.mp4': 'audio/mp4',
    '.m4a': 'audio/mp4',
    '.wav': 'audio/wav',
    '.webm': 'audio/webm'
}

def transcribe(path: str, suffix: str) -> str:
    c = ai()
    up = c.files.upload(file=path, config={'mime_type': AUDIO_MIME[suffix]})
    try:
        while up.state and up.state.name == 'PROCESSING':
            time.sleep(1)
            up = c.files.get(name=up.name)
        models = [
            os.getenv('TRANSCRIBE_MODEL', 'gemini-2.5-flash'),
            'gemini-flash-lite-latest',
            'gemini-3.5-flash-lite',
            'gemini-flash-latest'
        ]
        prompt = 'ถอดเสียงไฟล์นี้เป็นข้อความตามที่พูดจริงในภาษาเดิม ห้ามสรุป ห้ามแต่งเติม ถ้าฟังไม่ชัดให้ใส่ [ไม่ชัด] ตอบเฉพาะข้อความถอดเสียง'
        errors = []
        for m in models:
            for attempt in range(2):
                try:
                    out = c.models.generate_content(model=m, contents=[up, prompt])
                    return out.text or ''
                except Exception as e:
                    errors.append(f"{m}: {e}")
                    time.sleep(2)
        raise HTTPException(503, f"AI โมเดลไม่พร้อมใช้งานชั่วคราว ({'; '.join(errors[-2:])}) กรุณาลองใหม่อีกครั้ง")
    finally:
        try:
            c.files.delete(name=up.name)
        except Exception:
            pass

def extract(name: str, raw: bytes) -> str:
    suffix = Path(name).suffix.lower()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(raw)
        p = f.name
    try:
        if suffix == '.pptx':
            pres = Presentation(p)
            return '\n\n'.join(
                f'[สไลด์ {i}] ' + ' | '.join(sh.text for sh in slide.shapes if sh.has_text_frame and sh.text.strip())
                for i, slide in enumerate(pres.slides, 1)
            )
        if suffix == '.pdf':
            reader = PdfReader(p)
            return '\n\n'.join(f'[หน้า {i}] ' + (page.extract_text() or '') for i, page in enumerate(reader.pages, 1))
        if suffix == '.txt':
            return raw.decode('utf-8-sig', errors='replace')
        raise HTTPException(400, 'รองรับไฟล์สไลด์ .pptx, .pdf, .txt')
    finally:
        os.remove(p)

def format_brief_html(title: str, date: str, lecturer: str, md_text: str) -> str:
    if not md_text:
        return ''
    style_block = '''<style>
div, p, td, li { font-family: 'TH SarabunPSK', 'TH Sarabun New', sans-serif; font-size: 16pt; }
h1 { font-family: 'TH SarabunPSK', 'TH Sarabun New', sans-serif; font-size: 18pt; font-weight: bold; margin-top: 12pt; margin-bottom: 4pt; color: #0f2942; }
table { border-collapse: collapse; width: 100%; margin-bottom: 14pt; border: 1px solid #cbd5e1; }
table td { padding: 3pt 6pt; border: 1px solid #cbd5e1; vertical-align: middle; }
table td p { margin: 0pt !important; line-height: 1.15; font-family: 'TH SarabunPSK', 'TH Sarabun New', sans-serif; font-size: 16pt; }
</style>'''
    html = [style_block, '''<div style="font-family: 'TH SarabunPSK', 'TH Sarabun New', sans-serif; font-size: 16pt; line-height: 1.25; color: #17263c;">''']
    html.append('''<p style="text-align: center; font-size: 18pt; font-weight: bold; margin-top: 0; margin-bottom: 12pt; color: #0f2942;">Executive Brief</p>''')
    html.append(f'''<table border="1" style="border-collapse: collapse; width: 100%; font-size: 16pt; margin-bottom: 14pt; border: 1px solid #cbd5e1;">
  <tr>
    <td style="width: 25%; padding: 3pt 6pt; border: 1px solid #cbd5e1; vertical-align: middle;"><p style="margin: 0pt; line-height: 1.15; font-weight: bold; font-family: 'TH SarabunPSK', 'TH Sarabun New', sans-serif; font-size: 16pt; color: #0f2942;">หัวข้อ</p></td>
    <td style="padding: 3pt 6pt; border: 1px solid #cbd5e1; vertical-align: middle;"><p style="margin: 0pt; line-height: 1.15; font-family: 'TH SarabunPSK', 'TH Sarabun New', sans-serif; font-size: 16pt;">{title or '-'}</p></td>
  </tr>
  <tr>
    <td style="padding: 3pt 6pt; border: 1px solid #cbd5e1; vertical-align: middle;"><p style="margin: 0pt; line-height: 1.15; font-weight: bold; font-family: 'TH SarabunPSK', 'TH Sarabun New', sans-serif; font-size: 16pt; color: #0f2942;">วันที่</p></td>
    <td style="padding: 3pt 6pt; border: 1px solid #cbd5e1; vertical-align: middle;"><p style="margin: 0pt; line-height: 1.15; font-family: 'TH SarabunPSK', 'TH Sarabun New', sans-serif; font-size: 16pt;">{date or '-'}</p></td>
  </tr>
  <tr>
    <td style="padding: 3pt 6pt; border: 1px solid #cbd5e1; vertical-align: middle;"><p style="margin: 0pt; line-height: 1.15; font-weight: bold; font-family: 'TH SarabunPSK', 'TH Sarabun New', sans-serif; font-size: 16pt; color: #0f2942;">อาจารย์/วิทยากร</p></td>
    <td style="padding: 3pt 6pt; border: 1px solid #cbd5e1; vertical-align: middle;"><p style="margin: 0pt; line-height: 1.15; font-family: 'TH SarabunPSK', 'TH Sarabun New', sans-serif; font-size: 16pt;">{lecturer or '-'}</p></td>
  </tr>
</table>''')
    in_list = False
    past_header = False
    section_keywords = ['executive summary', 'key takeaways', 'strategic insights', 'implications for leaders', 'evidence & source references', 'reflection questions', 'ข้อจำกัดของข้อมูล']
    for raw in md_text.strip().split('\n'):
        line = raw.strip()
        if not line:
            if in_list:
                html.append('</ul>')
                in_list = False
            continue
        clean_lower = line.lower()
        if not past_header:
            if any(kw in clean_lower for kw in ['รายงานสรุป', 'executive brief', 'หัวข้อ:', 'วันที่:', 'วิทยากร:', 'หัวข้อ :', 'วันที่ :', 'วิทยากร :']) \
               or (line.startswith('*') and any(kw in clean_lower for kw in ['หัวข้อ', 'วันที่', 'วิทยากร'])) \
               or (line.startswith('-') and any(kw in clean_lower for kw in ['หัวข้อ', 'วันที่', 'วิทยากร'])):
                continue
            if 'executive summary' in clean_lower or line.startswith('#'):
                past_header = True
        line_clean = re.sub(r'^\[.*?\]\s*', '', line)
        line_formatted = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', line_clean)
        if re.match(r'^#{1,6}\s+', line):
            if in_list:
                html.append('</ul>')
                in_list = False
            h_text = re.sub(r'^#{1,6}\s+', '', line_formatted).strip()
            html.append(f'''<h1 style="font-family: 'TH SarabunPSK', 'TH Sarabun New', sans-serif; font-size: 18pt; font-weight: bold; margin-top: 12pt; margin-bottom: 4pt; color: #0f2942;">{h_text}</h1>''')
            continue
        bullet_match = re.match(r'^(\*|\-|\•|\d+\.)\s*(.*)$', line_clean)
        if bullet_match:
            if not in_list:
                html.append('''<ul style="margin-top: 0; margin-bottom: 6pt; padding-left: 20pt;">''')
                in_list = True
            item_raw = bullet_match.group(2)
            item_formatted = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', item_raw)
            html.append(f'''<li style="font-family: 'TH SarabunPSK', 'TH Sarabun New', sans-serif; font-size: 16pt; margin-bottom: 4pt; text-align: justify; text-justify: inter-cluster;">{item_formatted}</li>''')
            continue
        clean_title_check = re.sub(r'^[#\*\s]+', '', line_clean).lower()
        if any(kw in clean_title_check for kw in section_keywords) and len(line_clean) < 70:
            if in_list:
                html.append('</ul>')
                in_list = False
            clean_title = re.sub(r'^[\*\s]+|[\*\s]+$', '', line_formatted)
            html.append(f'''<h1 style="font-family: 'TH SarabunPSK', 'TH Sarabun New', sans-serif; font-size: 18pt; font-weight: bold; margin-top: 12pt; margin-bottom: 4pt; color: #0f2942;">{clean_title}</h1>''')
            continue
        if in_list:
            html.append('</ul>')
            in_list = False
        html.append(f'''<p style="font-family: 'TH SarabunPSK', 'TH Sarabun New', sans-serif; font-size: 16pt; margin-top: 0; margin-bottom: 6pt; text-align: justify; text-justify: inter-cluster;">{line_formatted}</p>''')
    if in_list:
        html.append('</ul>')
    html.append('</div>')
    return '\n'.join(html)

# ================= AUTH UTILITIES =================

def get_token_from_request(request: Request) -> Optional[str]:
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        return auth_header[7:].strip()
    return request.headers.get('X-Auth-Token') or request.cookies.get('session_token') or request.query_params.get('token')

def get_current_user(request: Request) -> dict:
    token = get_token_from_request(request)
    if not token:
        raise HTTPException(401, 'กรุณาเข้าสู่ระบบก่อนทำรายการ')
    with conn() as c:
        user = get_user_by_token(c, token)
    if not user:
        raise HTTPException(401, 'เซสชันหมดอายุ กรุณาเข้าสู่ระบบใหม่')
    return user

def get_optional_user(request: Request) -> Optional[dict]:
    token = get_token_from_request(request)
    if not token:
        return None
    with conn() as c:
        return get_user_by_token(c, token)

# ================= AUTH ENDPOINTS =================

class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: Optional[str] = None

class LoginRequest(BaseModel):
    username: str
    password: str

@app.post('/api/auth/register')
def register(body: RegisterRequest, response: Response):
    u = body.username.strip()
    p = body.password.strip()
    d = (body.display_name or u).strip()
    if len(u) < 3:
        raise HTTPException(400, 'ชื่อผู้ใช้งานต้องมีความยาวอย่างน้อย 3 ตัวอักษร')
    if len(p) < 4:
        raise HTTPException(400, 'รหัสผ่านต้องมีความยาวอย่างน้อย 4 ตัวอักษร')

    user_id = str(uuid.uuid4())
    pwd_hash, salt = hash_password(p)
    now = datetime.now(timezone.utc).isoformat()

    with conn() as c:
        existing = c.execute('SELECT id FROM users WHERE username = ? COLLATE NOCASE', (u,)).fetchone()
        if existing:
            raise HTTPException(400, 'ชื่อผู้ใช้งานนี้ถูกใช้งานแล้ว กรุณาเลือกชื่ออื่น')
        c.execute('INSERT INTO users (id, username, password_hash, salt, display_name, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                  (user_id, u, pwd_hash, salt, d, now))
        # Migrate any orphan legacy lectures (user_id IS NULL) to first user
        c.execute('UPDATE lectures SET user_id = ? WHERE user_id IS NULL', (user_id,))
        token = create_session(c, user_id)

    response.set_cookie('session_token', token, max_age=30*86400, httponly=False, samesite='lax')
    return {'token': token, 'user': {'id': user_id, 'username': u, 'display_name': d}}

@app.post('/api/auth/login')
def login(body: LoginRequest, response: Response):
    u = body.username.strip()
    p = body.password.strip()
    with conn() as c:
        row = c.execute('SELECT * FROM users WHERE username = ? COLLATE NOCASE', (u,)).fetchone()
        if not row:
            raise HTTPException(401, 'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง')
        user = dict(row)
        if not verify_password(p, user['password_hash'], user['salt']):
            raise HTTPException(401, 'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง')
        token = create_session(c, user['id'])

    response.set_cookie('session_token', token, max_age=30*86400, httponly=False, samesite='lax')
    return {
        'token': token,
        'user': {
            'id': user['id'],
            'username': user['username'],
            'display_name': user['display_name'] or user['username']
        }
    }

@app.get('/api/auth/me')
def me(request: Request):
    user = get_current_user(request)
    return {'user': user}

@app.post('/api/auth/logout')
def logout(request: Request, response: Response):
    token = get_token_from_request(request)
    if token:
        with conn() as c:
            delete_session(c, token)
    response.delete_cookie('session_token')
    return {'status': 'ok'}

# ================= LECTURES ENDPOINTS =================

@app.get('/api/lectures')
def list_lectures(request: Request):
    user = get_current_user(request)
    with conn() as c:
        rows = c.execute('''
            SELECT id, date, title, lecturer, created_at, share_token,
                   CASE WHEN brief IS NULL THEN 0 ELSE 1 END AS has_brief,
                   CASE WHEN (transcript IS NOT NULL AND transcript != '') THEN 1 ELSE 0 END AS has_transcript
            FROM lectures
            WHERE user_id = ?
            ORDER BY date DESC, created_at DESC
        ''', (user['id'],)).fetchall()
        return [dict(r) for r in rows]

@app.get('/api/lectures/{id}')
def get_lecture(id: str, request: Request):
    user = get_current_user(request)
    with conn() as c:
        row = c.execute('SELECT * FROM lectures WHERE id = ? AND user_id = ?', (id, user['id'])).fetchone()
    if not row:
        raise HTTPException(404, 'ไม่พบรายการหรือไม่มีสิทธิ์เข้าถึง')
    d = dict(row)
    if not d.get('share_token'):
        new_share = str(uuid.uuid4())
        with conn() as c:
            c.execute('UPDATE lectures SET share_token = ? WHERE id = ?', (new_share, id))
        d['share_token'] = new_share
    d['brief_html'] = format_brief_html(d.get('title') or '', d.get('date') or '', d.get('lecturer') or '', d.get('brief') or '')
    return d

@app.delete('/api/lectures/{id}')
def delete_lecture(id: str, request: Request):
    user = get_current_user(request)
    with conn() as c:
        row = c.execute('SELECT id FROM lectures WHERE id = ? AND user_id = ?', (id, user['id'])).fetchone()
        if not row:
            raise HTTPException(404, 'ไม่พบรายการที่ต้องการลบ')
        c.execute('DELETE FROM lectures WHERE id = ?', (id,))
    return {'status': 'deleted', 'id': id}

@app.post('/api/lectures')
async def create_lecture(
    request: Request,
    date: str = Form(...),
    title: str = Form(...),
    lecturer: str = Form(''),
    notes: str = Form(''),
    slides: list[UploadFile] | None = File(None),
    audio: list[UploadFile] | None = File(None)
):
    user = get_current_user(request)
    if not title.strip() or not date.strip():
        raise HTTPException(400, 'โปรดระบุวันที่และหัวข้อ')

    parts = []
    for slide in [f for f in slides or [] if f.filename]:
        raw = await slide.read()
        if len(raw) > 20 * 1024 * 1024:
            raise HTTPException(413, f'ไฟล์สไลด์ {slide.filename} มีขนาดเกิน 20MB')
        parts.append(f'=== เอกสาร {slide.filename} ===\n' + extract(slide.filename or '', raw))

    transcript_parts = []
    for idx, sound in enumerate([f for f in audio or [] if f.filename], 1):
        raw = await sound.read()
        if len(raw) > 25 * 1024 * 1024:
            raise HTTPException(413, f'ไฟล์เสียง {sound.filename} มีขนาดเกิน 25MB')
        suffix = Path(sound.filename or '').suffix.lower()
        if suffix not in AUDIO_MIME:
            raise HTTPException(400, f'ไฟล์เสียง {sound.filename} ไม่รองรับ')
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(raw)
            p = f.name
        try:
            transcript_parts.append(f'[เสียงชุด {idx}: {sound.filename}]\n{transcribe(p, suffix)}')
        finally:
            os.remove(p)

    lid = str(uuid.uuid4())
    share_token = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with conn() as c:
        c.execute('''
            INSERT INTO lectures (id, date, title, lecturer, notes, source_text, transcript, brief, created_at, user_id, share_token)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (lid, date, title, lecturer, notes, '\n'.join(parts), '\n\n'.join(transcript_parts), None, now, user['id'], share_token))

    return {'id': lid, 'status': 'saved', 'slide_count': len(parts), 'audio_count': len(transcript_parts), 'share_token': share_token}

@app.post('/api/lectures/{id}/summarize')
def summarize(id: str, request: Request):
    user = get_current_user(request)
    with conn() as c:
        row = c.execute('SELECT * FROM lectures WHERE id = ? AND user_id = ?', (id, user['id'])).fetchone()
    if not row:
        raise HTTPException(404, 'ไม่พบรายการหรือไม่มีสิทธิ์เข้าถึง')
    row = dict(row)

    source = f"วันที่: {row['date']}\nหัวข้อ: {row['title']}\nวิทยากร: {row['lecturer']}\nบันทึกผู้เรียน: {row['notes']}\n\nสไลด์:\n{row['source_text']}\n\nถอดเสียง:\n{row['transcript']}"
    if not any((row['notes'], row['source_text'], row['transcript'])):
        raise HTTPException(400, 'ยังไม่มีเนื้อหาสำหรับสรุป (กรุณาแนบไฟล์สไลด์, เสียงบรรยาย หรือบันทึกย่อ)')
    if len(source) > 100000:
        raise HTTPException(413, 'เนื้อหายาวเกินขีดจำกัดต้นแบบ กรุณาแบ่งการบรรยายเป็นหลายรายการ')

    models = [
        os.getenv('BRIEF_MODEL', 'gemini-2.5-flash'),
        'gemini-flash-lite-latest',
        'gemini-3.5-flash-lite',
        'gemini-flash-latest'
    ]
    client = ai()
    out = None
    errors = []
    sys_instruction = '''คุณเป็นเลขานุการวิชาการสำหรับผู้บริหารระดับสูงของหลักสูตร วปอ. (ThaiNDC). เขียนภาษาไทยกึ่งทางการ กระชับ ตรงประเด็น ห้ามแต่งข้อเท็จจริง/คำพูด/เวลาจากเสียงที่ไม่มี timecode ให้แยก "ข้อเท็จจริงจากแหล่งข้อมูล" และ "การวิเคราะห์ต่อยอดของ AI" อย่างชัดเจน ใช้แหล่งอ้างอิง [สไลด์ N]/[หน้า N]/[เสียงชุด N] เฉพาะเมื่อมีหลักฐาน อย่าอ้างแหล่งเท็จ หากมีความขัดแย้งให้ระบุว่าไม่สอดคล้องกัน ไม่ถ่ายทอดข้อมูลอ่อนไหวที่ไม่จำเป็น จัดรูปแบบ Markdown มี: Executive Summary, Key Takeaways 5-7 ข้อ, Strategic Insights, Implications for Leaders, Evidence & Source References, Reflection Questions 3-5 ข้อ, ข้อจำกัดของข้อมูล. ข้อสำคัญ: ห้ามพิมพ์ชื่อเรื่อง วันที่ หรือชื่อวิทยากรซ้ำที่ส่วนต้น (เนื่องจากระบบมีตารางหัวกระดาษให้อยู่แล้ว) ให้เริ่มต้นเนื้อหาด้วยหัวข้อ Executive Summary ทันที.'''

    for m in models:
        for attempt in range(2):
            try:
                out = client.models.generate_content(
                    model=m,
                    config=types.GenerateContentConfig(system_instruction=sys_instruction),
                    contents=source
                )
                if out and out.text:
                    break
            except Exception as e:
                errors.append(f"{m}: {e}")
                time.sleep(2)
        if out and out.text:
            break

    if not out or not out.text:
        raise HTTPException(503, f"AI โมเดลไม่พร้อมใช้งานชั่วคราว ({'; '.join(errors[-2:])})")

    brief = out.text
    with conn() as c:
        c.execute('UPDATE lectures SET brief = ? WHERE id = ?', (brief, id))
    brief_html = format_brief_html(row.get('title') or '', row.get('date') or '', row.get('lecturer') or '', brief)
    return {'id': id, 'brief': brief, 'brief_html': brief_html}

@app.get('/api/lectures/{id}/download-docx')
def download_docx(id: str, request: Request):
    user = get_current_user(request)
    with conn() as c:
        row = c.execute('SELECT * FROM lectures WHERE id = ? AND user_id = ?', (id, user['id'])).fetchone()
    if not row:
        raise HTTPException(404, 'ไม่พบรายการ')
    d = dict(row)
    if not d.get('brief'):
        raise HTTPException(400, 'ยังไม่มีบทสรุป Executive Brief สำหรับดาวน์โหลด')

    buf = build_executive_brief_docx(
        d.get('title') or '',
        d.get('date') or '',
        d.get('lecturer') or '',
        d.get('brief') or ''
    )
    safe_title = re.sub(r'[\\/*?:"<>|]', '_', d.get('title') or 'Brief')[:30]
    filename = f"Executive_Brief_{d.get('date') or ''}_{safe_title}.docx"
    encoded_filename = urllib.parse.quote(filename)

    return Response(
        content=buf.getvalue(),
        media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        headers={
            'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_filename}",
            'Access-Control-Expose-Headers': 'Content-Disposition'
        }
    )

@app.get('/api/lectures/{id}/download-transcript')
def download_transcript(id: str, request: Request, format: str = 'txt'):
    user = get_current_user(request)
    with conn() as c:
        row = c.execute('SELECT * FROM lectures WHERE id = ? AND user_id = ?', (id, user['id'])).fetchone()
    if not row:
        raise HTTPException(404, 'ไม่พบรายการ')
    d = dict(row)
    transcript = d.get('transcript') or ''
    notes = d.get('notes') or ''
    source_text = d.get('source_text') or ''
    if not (transcript or notes or source_text):
        raise HTTPException(400, 'ยังไม่มีเนื้อหาคำบรรยายหรือบันทึกถอดเสียงสำหรับดาวน์โหลด')

    safe_title = re.sub(r'[\\/*?:"<>|]', '_', d.get('title') or 'Transcript')[:30]
    date_str = d.get('date') or ''

    if format == 'docx':
        buf = build_transcript_docx(
            d.get('title') or '',
            date_str,
            d.get('lecturer') or '',
            transcript,
            notes,
            source_text
        )
        filename = f"Transcript_{date_str}_{safe_title}.docx"
        encoded_filename = urllib.parse.quote(filename)
        return Response(
            content=buf.getvalue(),
            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            headers={
                'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_filename}",
                'Access-Control-Expose-Headers': 'Content-Disposition'
            }
        )
    else:
        txt = build_transcript_text(
            d.get('title') or '',
            date_str,
            d.get('lecturer') or '',
            transcript,
            notes,
            source_text
        )
        filename = f"Transcript_{date_str}_{safe_title}.txt"
        encoded_filename = urllib.parse.quote(filename)
        return Response(
            content=codecs.BOM_UTF8 + txt.encode('utf-8'),
            media_type='text/plain; charset=utf-8',
            headers={
                'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_filename}",
                'Access-Control-Expose-Headers': 'Content-Disposition'
            }
        )

# ================= PUBLIC SHARE ENDPOINTS =================

@app.get('/api/share/{token}')
def get_shared_lecture(token: str):
    with conn() as c:
        row = c.execute('''
            SELECT id, date, title, lecturer, brief, transcript, notes, source_text, created_at,
                   CASE WHEN (transcript IS NOT NULL AND transcript != '') THEN 1 ELSE 0 END AS has_transcript
            FROM lectures
            WHERE share_token = ?
        ''', (token,)).fetchone()
    if not row:
        raise HTTPException(404, 'ไม่พบบันทึกบทเรียนนี้ หรือลิงก์หมดอายุ')
    d = dict(row)
    d['brief_html'] = format_brief_html(d.get('title') or '', d.get('date') or '', d.get('lecturer') or '', d.get('brief') or '')
    return d

@app.get('/api/share/{token}/download-docx')
def download_shared_docx(token: str):
    with conn() as c:
        row = c.execute('SELECT * FROM lectures WHERE share_token = ?', (token,)).fetchone()
    if not row:
        raise HTTPException(404, 'ไม่พบบันทึกบทเรียนนี้')
    d = dict(row)
    if not d.get('brief'):
        raise HTTPException(400, 'ยังไม่มีบทสรุป Executive Brief สำหรับดาวน์โหลด')

    buf = build_executive_brief_docx(
        d.get('title') or '',
        d.get('date') or '',
        d.get('lecturer') or '',
        d.get('brief') or ''
    )
    safe_title = re.sub(r'[\\/*?:"<>|]', '_', d.get('title') or 'Brief')[:30]
    filename = f"Executive_Brief_{d.get('date') or ''}_{safe_title}.docx"
    encoded_filename = urllib.parse.quote(filename)

    return Response(
        content=buf.getvalue(),
        media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        headers={
            'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_filename}",
            'Access-Control-Expose-Headers': 'Content-Disposition'
        }
    )

@app.get('/api/share/{token}/download-transcript')
def download_shared_transcript(token: str, format: str = 'txt'):
    with conn() as c:
        row = c.execute('SELECT * FROM lectures WHERE share_token = ?', (token,)).fetchone()
    if not row:
        raise HTTPException(404, 'ไม่พบบันทึกบทเรียนนี้')
    d = dict(row)
    transcript = d.get('transcript') or ''
    notes = d.get('notes') or ''
    source_text = d.get('source_text') or ''
    if not (transcript or notes or source_text):
        raise HTTPException(400, 'ยังไม่มีเนื้อหาคำบรรยายหรือบันทึกถอดเสียงสำหรับดาวน์โหลด')

    safe_title = re.sub(r'[\\/*?:"<>|]', '_', d.get('title') or 'Transcript')[:30]
    date_str = d.get('date') or ''

    if format == 'docx':
        buf = build_transcript_docx(
            d.get('title') or '',
            date_str,
            d.get('lecturer') or '',
            transcript,
            notes,
            source_text
        )
        filename = f"Transcript_{date_str}_{safe_title}.docx"
        encoded_filename = urllib.parse.quote(filename)
        return Response(
            content=buf.getvalue(),
            media_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            headers={
                'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_filename}",
                'Access-Control-Expose-Headers': 'Content-Disposition'
            }
        )
    else:
        txt = build_transcript_text(
            d.get('title') or '',
            date_str,
            d.get('lecturer') or '',
            transcript,
            notes,
            source_text
        )
        filename = f"Transcript_{date_str}_{safe_title}.txt"
        encoded_filename = urllib.parse.quote(filename)
        return Response(
            content=codecs.BOM_UTF8 + txt.encode('utf-8'),
            media_type='text/plain; charset=utf-8',
            headers={
                'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_filename}",
                'Access-Control-Expose-Headers': 'Content-Disposition'
            }
        )

@app.get('/share/{token}')
def share_page(token: str):
    return FileResponse(ROOT / 'static' / 'share.html')

@app.get('/')
def index():
    return FileResponse(ROOT / 'static' / 'index.html')
