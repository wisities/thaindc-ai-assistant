# ThaiNDC AI Learning Assistant — Microsoft Word Add-in

ผู้ช่วยสรุปบทเรียนสำหรับผู้บริหาร วปอ. (ThaiNDC) ใช้งานผ่าน Microsoft Word Add-in พร้อมระบบถอดเสียงและวิเคราะห์บทเรียนด้วย Google Gemini AI

## สิ่งที่ทำได้
- บันทึกวันที่/หัวข้อ/วิทยากร/โน้ต รายวันในฐานข้อมูล SQLite
- อ่านไฟล์สไลด์ PPTX, PDF และ TXT (อัปโหลดหรือไม่ก็ได้)
- ถอดเสียงบรรยาย MP3/M4A/WAV/WEBM ด้วย Gemini AI พร้อมระบบ fallback อัตโนมัติ
- สร้าง Executive Brief ภาษาไทย สำหรับผู้บริหาร วปอ.
- แทรกเอกสารสรุปลงท้ายเอกสาร Word ผ่าน Office.js ตามรูปแบบทางการ (ฟอนต์ TH SarabunPSK, ตารางหัวเรื่อง, หัวข้อ Heading 1)

---

## การ Deploy บน Cloud ส่วนตัวด้วย Docker (แนะนำ)
1. คัดลอกโปรเจกต์นี้ไปยังเครื่อง Server / Private Cloud
2. สร้างไฟล์ `.env` จากตัวอย่าง:
   ```bash
   cp .env.example .env
   # แก้ไขใส่ GEMINI_API_KEY ของคุณในไฟล์ .env
   ```
3. สั่งรันด้วย Docker Compose:
   ```bash
   docker compose up -d --build
   ```
4. ชี้ Reverse Proxy (เช่น Nginx หรือ Caddy) พร้อมทำ HTTPS (Let's Encrypt) ส่งต่อไปที่พอร์ต `8000`
5. แก้ไข URL ใน `manifest.xml` ทั้ง 3 จุดให้เป็นชื่อโดเมน HTTPS ของคุณ แล้วนำไปติดตั้งใน Word

6. ทดสอบหน้าเว็บที่ `https://localhost:8443/` ก่อน
7. ใน Word เลือก **Add-ins → More Add-ins → Upload My Add-in** (รายการเมนูขึ้นกับรุ่น/นโยบายองค์กร) แล้วเลือก `manifest.xml` หรือใช้วิธี sideload ตามเอกสาร Microsoft
8. เพิ่มบันทึกและไฟล์ → สร้าง Brief → แทรกลง Word

**หมายเหตุ:** 1) จำเป็นต้องใช้ Word รุ่นที่รองรับ Office Add-ins และเชื่อถือ certificate 2) Word on the web อาจเข้าถึง localhost ฝั่งเซิร์ฟเวอร์ไม่ได้ตามบริบทของผู้ใช้; สำหรับใช้งานหลายคนให้ deploy ผ่าน HTTPS domain และแก้ URL ทั้ง 3 จุดใน manifest 3) ตัวอย่างยังไม่มีระบบล็อกอิน, แบ่งสิทธิ์, งานเบื้องหลัง, backup, การเข้ารหัสข้อมูลพัก, retention policy, การสรุปข้อความที่ยาวเกิน 100,000 อักขระ หรือการถอดเสียงเป็น timecode 4) ไม่ควรนำข้อมูลการบรรยายที่เป็นความลับขึ้นระบบทดสอบหรือ API โดยไม่ได้รับอนุญาต

## แนวทางก่อนใช้งานจริง
- Microsoft Entra ID / SSO + role-based access, per-class tenant
- Private object storage และการเข้ารหัส; ตั้งอายุเก็บไฟล์เสียงและสิทธิ์เข้าถึง
- Speech chunking, queue workers, retry และ asynchronous summarization
- แบ่งเนื้อหายาวเป็นช่วงพร้อม timestamp และอ้างหน้า slide; hybrid retrieval / citations
- Workflow ตรวจทาน/อนุมัติ Brief ก่อนส่งผู้เรียน
- Export DOCX/PDF ที่มีรูปแบบและสารบัญ และแดชบอร์สรุปรายสัปดาห์/รายหลักสูตร

อ่านเอกสาร Office Add-ins: https://learn.microsoft.com/en-us/office/dev/add-ins/word/  และ https://learn.microsoft.com/en-us/office/dev/add-ins/testing/sideload-office-add-ins-for-testing
