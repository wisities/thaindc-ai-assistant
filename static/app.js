// ThaiNDC AI Learning Assistant Client Application

let currentUser = null;
let currentLecture = null;
let allLectures = [];
let authMode = 'login'; // 'login' or 'register'

const el = id => document.getElementById(id);

// Date default
if (el('date')) {
  el('date').value = new Date().toLocaleDateString('en-CA');
}

// Status Banner
function showBanner(message, type = 'info', autoHideMs = 4500) {
  const banner = el('statusBanner');
  banner.textContent = message;
  banner.className = type;
  if (autoHideMs > 0) {
    setTimeout(() => {
      if (banner.textContent === message) {
        banner.className = '';
        banner.style.display = 'none';
      }
    }, autoHideMs);
  }
}

// API Helper with Bearer token
async function api(url, opts = {}) {
  const token = localStorage.getItem('thaindc_token');
  const headers = opts.headers ? { ...opts.headers } : {};
  if (token) {
    headers['Authorization'] = 'Bearer ' + token;
  }
  const res = await fetch(url, { credentials: 'same-origin', ...opts, headers });
  
  if (res.status === 401) {
    // Session expired or unauthenticated
    localStorage.removeItem('thaindc_token');
    currentUser = null;
    updateUserBar();
    showAuthScreen();
    throw new Error('กรุณาเข้าสู่ระบบก่อนทำรายการ');
  }

  const text = await res.text();
  let json;
  try {
    json = JSON.parse(text);
  } catch (_) {
    if (!res.ok) throw new Error(`เซิร์ฟเวอร์ขัดข้อง (${res.status}): ${text || 'เกิดข้อผิดพลาด'}`);
    return text;
  }
  if (!res.ok) {
    throw new Error(json.detail || 'เกิดข้อผิดพลาดจากเซิร์ฟเวอร์');
  }
  return json;
}

// Auth State Check
async function initAuth() {
  const token = localStorage.getItem('thaindc_token');
  if (!token) {
    showAuthScreen();
    return;
  }
  try {
    const res = await api('/api/auth/me');
    currentUser = res.user;
    updateUserBar();
    showMainScreen();
    await loadDashboard();
  } catch (err) {
    showAuthScreen();
  }
}

function updateUserBar() {
  const userBar = el('userBar');
  if (currentUser) {
    userBar.innerHTML = `
      <div class="user-pill">
        👤 <span>${escapeHtml(currentUser.display_name || currentUser.username)}</span>
      </div>
      <button class="btn-secondary btn-sm" onclick="logout()">ออกจากระบบ</button>
    `;
  } else {
    userBar.innerHTML = `
      <button class="btn-primary btn-sm" onclick="showAuthScreen()">เข้าสู่ระบบ</button>
    `;
  }
}

function showAuthScreen() {
  el('authView').style.display = 'block';
  el('mainView').style.display = 'none';
  updateUserBar();
}

function showMainScreen() {
  el('authView').style.display = 'none';
  el('mainView').style.display = 'block';
  updateUserBar();
}

function switchAuthTab(mode) {
  authMode = mode;
  if (mode === 'login') {
    el('tabLogin').classList.add('active');
    el('tabRegister').classList.remove('active');
    el('displayNameField').style.display = 'none';
    el('authSubmitBtn').textContent = 'เข้าสู่ระบบ';
  } else {
    el('tabLogin').classList.remove('active');
    el('tabRegister').classList.add('active');
    el('displayNameField').style.display = 'block';
    el('authSubmitBtn').textContent = 'สร้างบัญชีผู้ใช้ใหม่';
  }
}

// Auth Form Handler
el('authForm').onsubmit = async (e) => {
  e.preventDefault();
  const username = el('authUsername').value.trim();
  const password = el('authPassword').value.trim();
  const displayName = el('authDisplayName') ? el('authDisplayName').value.trim() : '';

  const endpoint = authMode === 'register' ? '/api/auth/register' : '/api/auth/login';
  const payload = { username, password };
  if (authMode === 'register') payload.display_name = displayName;

  showBanner('กำลังตรวจสอบข้อมูล...', 'info', 0);
  try {
    const res = await api(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    localStorage.setItem('thaindc_token', res.token);
    currentUser = res.user;
    showBanner(`ยินดีต้อนรับ ${currentUser.display_name || currentUser.username}!`, 'success');
    showMainScreen();
    showView('dashboard');
    await loadDashboard();
  } catch (err) {
    showBanner('ผิดพลาด: ' + err.message, 'error', 6000);
  }
};

async function logout() {
  try {
    await api('/api/auth/logout', { method: 'POST' });
  } catch (_) {}
  localStorage.removeItem('thaindc_token');
  currentUser = null;
  showBanner('ออกจากระบบเรียบร้อยแล้ว', 'info');
  showAuthScreen();
}

// View Navigation
function showView(viewName, lectureId = null) {
  el('viewDashboard').style.display = 'none';
  el('viewRecord').style.display = 'none';
  el('viewDetail').style.display = 'none';

  el('navDashboard').classList.remove('active');
  el('navRecord').classList.remove('active');

  if (viewName === 'dashboard') {
    el('viewDashboard').style.display = 'block';
    el('navDashboard').classList.add('active');
    loadDashboard();
  } else if (viewName === 'record') {
    el('viewRecord').style.display = 'block';
    el('navRecord').classList.add('active');
  } else if (viewName === 'detail') {
    el('viewDetail').style.display = 'block';
    if (lectureId) loadLectureDetail(lectureId);
  }
}

// Dashboard Loader
async function loadDashboard() {
  try {
    allLectures = await api('/api/lectures');
    updateDashboardStats(allLectures);
    renderLectureList(allLectures);
  } catch (err) {
    showBanner('โหลดรายการไม่สำเร็จ: ' + err.message, 'error');
  }
}

function updateDashboardStats(list) {
  const total = list.length;
  const briefs = list.filter(item => item.has_brief).length;
  el('statTotal').textContent = total;
  el('statBriefs').textContent = briefs;
  el('statReady').textContent = briefs;
}

function renderLectureList(list) {
  const container = el('lectureList');
  if (!list || list.length === 0) {
    container.innerHTML = `
      <div style="text-align: center; padding: 36px 12px; color: var(--text-muted);">
        <p style="font-size: 15px; font-weight: 500;">ยังไม่มีบันทึกบทเรียนในบัญชีของคุณ</p>
        <p style="font-size: 12.5px; margin-top: 6px;">เริ่มต้นโดยการกดปุ่ม “➕ บันทึกบทเรียนใหม่” ด้านบน</p>
      </div>
    `;
    return;
  }

  container.innerHTML = list.map(item => `
    <div class="lecture-card">
      <div class="lecture-info">
        <div class="lecture-title">${escapeHtml(item.title)}</div>
        <div class="lecture-meta">
          <span>📅 ${escapeHtml(item.date)}</span>
          ${item.lecturer ? `<span>👤 ${escapeHtml(item.lecturer)}</span>` : ''}
          <span class="status-badge ${item.has_brief ? 'has-brief' : 'no-brief'}">
            ${item.has_brief ? '✓ มี Executive Brief แล้ว' : '⏳ รอสร้างบทสรุป'}
          </span>
        </div>
      </div>
      <div class="lecture-actions">
        <button class="btn-secondary btn-sm" onclick="showView('detail', '${item.id}')">
          👁️ ดูสรุป
        </button>
        ${item.has_brief ? `
          <button class="btn-primary btn-sm" onclick="downloadDocxDirect('${item.id}', '${escapeHtml(item.title)}')">
            📥 Word (.docx)
          </button>
        ` : ''}
        <button class="btn-secondary btn-sm" onclick="openShareModal('${item.share_token}')">
          🔗 แชร์ลิงก์
        </button>
        <button class="btn-danger btn-sm" onclick="deleteLecture('${item.id}', '${escapeHtml(item.title)}')">
          🗑️
        </button>
      </div>
    </div>
  `).join('');
}

// Live Search
if (el('searchLecture')) {
  el('searchLecture').oninput = (e) => {
    const q = e.target.value.toLowerCase().trim();
    if (!q) {
      renderLectureList(allLectures);
      return;
    }
    const filtered = allLectures.filter(item => 
      (item.title && item.title.toLowerCase().includes(q)) ||
      (item.lecturer && item.lecturer.toLowerCase().includes(q)) ||
      (item.date && item.date.toLowerCase().includes(q))
    );
    renderLectureList(filtered);
  };
}

// Record Form Handler
el('lectureForm').onsubmit = async (e) => {
  e.preventDefault();
  const btn = el('saveBtn');
  btn.disabled = true;
  showBanner('กำลังอัปโหลดเอกสารและถอดเสียงบรรยาย... อาจใช้เวลา 30–60 วินาทีตามความยาวเสียง', 'info', 0);

  try {
    const formData = new FormData(e.target);
    const data = await api('/api/lectures', {
      method: 'POST',
      body: formData
    });
    showBanner(`บันทึกเรียบร้อย: ${data.slide_count} เอกสาร / ${data.audio_count} ไฟล์เสียง`, 'success');
    e.target.reset();
    el('date').value = new Date().toLocaleDateString('en-CA');
    showView('detail', data.id);
  } catch (err) {
    showBanner('ผิดพลาดในการบันทึก: ' + err.message, 'error', 8000);
  } finally {
    btn.disabled = false;
  }
};

// Lecture Detail & Brief View
async function loadLectureDetail(id) {
  const paper = el('briefPaper');
  paper.innerHTML = '<p style="color:var(--text-muted); text-align:center; padding:40px 0;">กำลังโหลดเนื้อหาบทสรุป...</p>';
  try {
    const data = await api('/api/lectures/' + id);
    currentLecture = data;

    // Download Docx Button
    const dlBtn = el('downloadDocxBtn');
    if (data.brief) {
      dlBtn.style.display = 'inline-flex';
      dlBtn.onclick = (e) => {
        e.preventDefault();
        downloadDocxDirect(data.id, data.title);
      };
    } else {
      dlBtn.style.display = 'none';
    }

    // Summarize Button
    const sumBtn = el('summarizeBtn');
    sumBtn.textContent = data.brief ? '✨ สร้างบทสรุปใหม่' : '✨ สร้าง Executive Brief';
    sumBtn.onclick = () => generateBrief(data.id);

    // Share Button
    el('shareBtn').onclick = () => openShareModal(data.share_token);

    // Copy Button
    el('copyBtn').onclick = () => copyBriefContent();

    // Delete Button
    el('deleteBtn').onclick = () => deleteLecture(data.id, data.title, true);

    // Render Preview
    if (data.brief_html) {
      paper.innerHTML = data.brief_html;
    } else if (data.brief) {
      paper.innerHTML = `<pre style="white-space:pre-wrap; font-family:inherit;">${escapeHtml(data.brief)}</pre>`;
    } else {
      paper.innerHTML = `
        <div style="text-align:center; padding: 48px 12px; color: var(--text-muted);">
          <h3 style="color:var(--primary); font-size:16px; margin-bottom:8px;">บันทึกข้อมูลและเสียงสำเร็จแล้ว</h3>
          <p style="font-size:13px; margin-bottom:16px;">ยังไม่มีเอกสารสรุป Executive Brief สำหรับบทเรียนนี้</p>
          <button class="btn-gold" onclick="generateBrief('${data.id}')">
            ✨ คลิกที่นี่เพื่อสร้าง Executive Brief ด้วย AI
          </button>
        </div>
      `;
    }
  } catch (err) {
    paper.innerHTML = `<p style="color:red; text-align:center;">${escapeHtml(err.message)}</p>`;
  }
}

// Generate Brief
async function generateBrief(id) {
  const btn = el('summarizeBtn');
  btn.disabled = true;
  showBanner('AI กำลังวิเคราะห์สไลด์ เสียงบรรยาย และสร้าง Executive Brief...', 'info', 0);
  try {
    const res = await api(`/api/lectures/${id}/summarize`, { method: 'POST' });
    showBanner('สร้าง Executive Brief เสร็จสมบูรณ์แล้ว!', 'success');
    await loadLectureDetail(id);
    await loadDashboard();
  } catch (err) {
    showBanner('ผิดพลาด: ' + err.message, 'error', 8000);
  } finally {
    btn.disabled = false;
  }
}

// Download Docx with Auth Token
async function downloadDocxDirect(id, title) {
  const token = localStorage.getItem('thaindc_token');
  showBanner('กำลังจัดเตรียมไฟล์ Word (.docx)...', 'info', 3000);
  try {
    const res = await fetch(`/api/lectures/${id}/download-docx`, {
      headers: token ? { 'Authorization': 'Bearer ' + token } : {}
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'ไม่สามารถดาวน์โหลดไฟล์ได้');
    }
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `Executive_Brief_${title || 'lecture'}.docx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
    showBanner('ดาวน์โหลดไฟล์ Word สำเร็จ!', 'success');
  } catch (err) {
    showBanner('ดาวน์โหลดไม่สำเร็จ: ' + err.message, 'error');
  }
}

// Copy Brief Content
async function copyBriefContent() {
  const paper = el('briefPaper');
  if (!currentLecture || !currentLecture.brief) {
    return showBanner('ยังไม่มีบทสรุปสำหรับคัดลอก', 'error');
  }
  try {
    if (navigator.clipboard && window.ClipboardItem && currentLecture.brief_html) {
      const blob = new Blob([currentLecture.brief_html], { type: 'text/html' });
      const textBlob = new Blob([paper.innerText || paper.textContent], { type: 'text/plain' });
      await navigator.clipboard.write([new ClipboardItem({ 'text/html': blob, 'text/plain': textBlob })]);
      showBanner('คัดลอกเรียบร้อย! สามารถวาง (Ctrl+V) ลงใน Word หรือโปรแกรมอื่นได้ทันที', 'success');
    } else {
      await navigator.clipboard.writeText(paper.innerText || paper.textContent);
      showBanner('คัดลอกข้อความสรุปเรียบร้อยแล้ว', 'success');
    }
  } catch (err) {
    showBanner('ไม่สามารถคัดลอกได้: ' + err.message, 'error');
  }
}

// Delete Lecture
async function deleteLecture(id, title, redirectDashboard = false) {
  if (!confirm(`คุณต้องการลบบันทึก "${title}" ใช่หรือไม่? (การลบจะไม่สามารถกู้คืนได้)`)) {
    return;
  }
  try {
    await api('/api/lectures/' + id, { method: 'DELETE' });
    showBanner('ลบบันทึกบทเรียนเรียบร้อยแล้ว', 'success');
    if (redirectDashboard) {
      showView('dashboard');
    } else {
      await loadDashboard();
    }
  } catch (err) {
    showBanner('ลบไม่สำเร็จ: ' + err.message, 'error');
  }
}

// Share Modal
function openShareModal(shareToken) {
  if (!shareToken) return showBanner('ไม่มีรหัสแชร์สำหรับรายการนี้', 'error');
  const shareUrl = window.location.origin + '/share/' + shareToken;
  el('shareUrlInput').value = shareUrl;
  el('shareModal').style.display = 'flex';

  el('copyShareUrlBtn').onclick = async () => {
    try {
      await navigator.clipboard.writeText(shareUrl);
      showBanner('คัดลอกลิงก์แชร์เรียบร้อย ส่งให้ผู้อื่นได้ทันที!', 'success');
      closeShareModal();
    } catch (_) {
      el('shareUrlInput').select();
      document.execCommand('copy');
      showBanner('คัดลอกลิงก์เรียบร้อย!', 'success');
      closeShareModal();
    }
  };
}

function closeShareModal() {
  el('shareModal').style.display = 'none';
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// Initialize on load
window.addEventListener('DOMContentLoaded', initAuth);
