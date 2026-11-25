"""
🎹 피아노학원 앱 테스트 데이터 생성기
- app.py와 같은 폴더에서 실행:  python seed_test_data.py
- 기존 DB를 지우고 새로 만들려면:  python seed_test_data.py --reset

생성되는 데이터: 학생 15명, 계정, 출석, 진도, 결제, 하트,
               수업 평가, 연주 영상(videos 폴더, ffmpeg 필요),
               입장·하원 알림, 코멘트 확인, 앱 사용 로그

생성되는 계정 (비밀번호는 모두 1234)
  선생님 : teacher
  학부모 : p01 ~ p15   (students.id 순서대로 연결)
  학생   : s01 ~ s15
"""
import hashlib
import math
import os
import random
import shutil
import sqlite3
import struct
import subprocess
import sys
import wave
from datetime import date, datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "piano_academy.db")
VIDEO_DIR = os.path.join(BASE_DIR, "videos")
PASSWORD = "1234"
START = date(2026, 9, 1)          # 이 날짜부터 오늘까지 기록 생성
TODAY = date.today()
random.seed(42)                   # 실행할 때마다 같은 데이터가 나오도록

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]

# 이름, 학년, 학부모 연락처, 수강요일, 시간, 결제일, 수강료, 교재
STUDENTS = [
    ("김하린", "초3", "010-1234-5678", "월,수,금", "14:00", 5, 150000, "체르니 100"),
    ("김하준", "초1", "010-1234-5678", "월,수,금", "14:30", 5, 150000, "바이엘 하"),   # 하린이 동생 (같은 번호)
    ("이서준", "초5", "010-2345-1111", "화,목", "15:00", 10, 140000, "체르니 30"),
    ("박지우", "초1", "010-3456-2222", "월,화,수,목,금", "13:30", 25, 180000, "바이엘 상"),
    ("최유나", "중1", "010-9876-4321", "수,토", "17:00", 1, 160000, "소나티네"),
    ("정민호", "초4", "010-5555-3333", "월,목", "16:00", 15, 140000, "부르크뮐러"),
    ("강다은", "초2", "010-4444-7777", "화,목", "14:00", 20, 140000, "바이엘 하"),
    ("윤시우", "초6", "010-8282-1004", "월,수,금", "16:30", 3, 150000, "체르니 30"),
    ("한예린", "중2", "010-7070-2580", "화,금", "18:00", 12, 160000, "소나타"),
    ("오지호", "초3", "010-3131-9090", "수,금", "15:30", 28, 140000, "체르니 100"),
    ("서아인", "유치", "010-6060-1212", "화,목", "13:00", 7, 130000, "바이엘 상"),
    ("임도윤", "초4", "010-1111-8888", "월,수", "17:00", 18, 140000, "부르크뮐러"),
    ("조하은", "초5", "010-2222-3434", "화,목,토", "15:00", 22, 160000, "체르니 30"),
    ("신우진", "고1", "010-9999-5656", "토", "11:00", 9, 120000, "소나타"),
    ("배수아", "초2", "010-5050-6767", "월,수,금", "13:30", 1, 150000, "동요/가요"),
]

# 교재별 곡 목록 (진도 기록용)
PIECES = {
    "바이엘 상": [f"{n}번" for n in range(1, 40, 3)],
    "바이엘 하": [f"{n}번" for n in range(50, 106, 4)],
    "체르니 100": [f"{n}번" for n in range(1, 60, 3)],
    "체르니 30": [f"{n}번" for n in range(1, 31)],
    "부르크뮐러": ["1. 솔직함", "2. 아라베스크", "3. 목가", "4. 작은 모임", "5. 순진함", "6. 진보",
               "7. 맑은 시냇물", "8. 우아함", "9. 사냥", "10. 다정한 꽃"],
    "소나티네": ["클레멘티 Op.36-1", "클레멘티 Op.36-2", "클레멘티 Op.36-3", "쿨라우 Op.20-1", "쿨라우 Op.55-1"],
    "소나타": ["모차르트 K.545 1악장", "모차르트 K.545 2악장", "베토벤 Op.49-2 1악장", "하이든 Hob.XVI:35 1악장"],
    "동요/가요": ["작은 별", "곰 세 마리", "산토끼", "학교 종", "나비야", "떴다 떴다 비행기"],
}
COMMENTS = {
    "🌱 시작": ["새 곡 시작! 오른손 먼저 천천히 연습해요", "악보 읽기부터 차근차근 해봤어요",
               "리듬 박수 치기로 곡을 익혔어요"],
    "🎵 연습 중": ["왼손 리듬이 조금 빨라져요. 메트로놈 60으로 연습", "손목 힘을 빼면 소리가 더 예뻐져요",
               "셈여림을 살려서 연습해 오기", "양손 맞추기 연습이 필요해요", "손가락 번호 지키기!"],
    "⭐ 완성": ["끝까지 틀리지 않고 완주했어요 👏", "표현이 아주 좋아졌어요!", "오늘 완성! 다음 곡으로 넘어가요"],
}
HEART_REASONS = ["🏠 숙제 완료", "🔥 연습 열심히", "⭐ 곡 완성", "🧍 바른 자세", "🎼 악보 잘 읽기", "😊 수업 태도"]
TEACHER_MENUS = ["home", "attendance", "students", "progress", "payment", "heart", "growth", "usagelog", "dbadmin"]
FAMILY_MENUS = ["my_home", "my_growth", "my_progress", "my_heart", "my_attendance", "my_payment"]
DIFFICULTY_TAGS = ["양손 맞추기", "손가락 번호", "리듬", "악보 읽기", "박자 유지", "셈여림", "페달", "도약·옥타브", "암보"]


def h(pw):
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()


def ts(d, hhmm, jitter_min=0):
    """날짜 + 'HH:MM' + 분 단위 흔들림 → 'YYYY-MM-DD HH:MM:SS'"""
    t = datetime.combine(d, datetime.strptime(hhmm, "%H:%M").time()) + timedelta(minutes=jitter_min)
    return t.strftime("%Y-%m-%d %H:%M:%S")


def create_tables(c):
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(userid TEXT PRIMARY KEY, password TEXT NOT NULL, created_at TEXT NOT NULL,
        role TEXT DEFAULT 'teacher', student_id INTEGER);
    CREATE TABLE IF NOT EXISTS learninghistory(id INTEGER PRIMARY KEY AUTOINCREMENT, userid TEXT NOT NULL,
        menu_id TEXT NOT NULL, wating_time INTEGER DEFAULT 0, create_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS students(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, grade TEXT,
        parent_phone TEXT, phone_last4 TEXT NOT NULL, lesson_days TEXT, lesson_time TEXT, pay_day INTEGER DEFAULT 1,
        fee INTEGER DEFAULT 150000, current_book TEXT, start_date TEXT, active INTEGER DEFAULT 1, created_at TEXT);
    CREATE TABLE IF NOT EXISTS attendance(id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL,
        check_date TEXT NOT NULL, check_time TEXT NOT NULL, message TEXT, leave_time TEXT);
    CREATE TABLE IF NOT EXISTS videos(id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL, piece TEXT,
        recorded_date TEXT, file_path TEXT, youtube_url TEXT, comment TEXT, uploaded_by TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL,
        kind TEXT, message TEXT, created_at TEXT, read_at TEXT);
    CREATE TABLE IF NOT EXISTS progress(id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL,
        lesson_date TEXT, book TEXT, piece TEXT, measures TEXT, status TEXT, comment TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL,
        pay_month TEXT NOT NULL, amount INTEGER, method TEXT, paid_at TEXT);
    CREATE TABLE IF NOT EXISTS hearts(id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER NOT NULL,
        amount INTEGER NOT NULL, reason TEXT, given_by TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS lesson_evals(id INTEGER PRIMARY KEY AUTOINCREMENT, progress_id INTEGER,
        student_id INTEGER NOT NULL, lesson_date TEXT, piece TEXT, rhythm INTEGER, accuracy INTEGER, posture INTEGER,
        expression INTEGER, tags TEXT, created_at TEXT);
    CREATE TABLE IF NOT EXISTS comment_reads(id INTEGER PRIMARY KEY AUTOINCREMENT, userid TEXT NOT NULL,
        progress_id INTEGER NOT NULL, read_at TEXT, UNIQUE(userid, progress_id));
    """)
    cols = [r[1] for r in c.execute("PRAGMA table_info(users)")]
    if "role" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'teacher'")
    if "student_id" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN student_id INTEGER")


def lesson_dates(days_str):
    """START~TODAY 중 수강 요일에 해당하는 날짜들"""
    days = days_str.split(",")
    d, out = START, []
    while d <= TODAY:
        if WEEKDAYS[d.weekday()] in days:
            out.append(d)
        d += timedelta(days=1)
    return out


def seed(c):
    created = START.strftime("%Y-%m-%d 09:00:00")

    # 1) 선생님 계정
    c.execute("INSERT OR IGNORE INTO users VALUES(?,?,?,?,?)", ("teacher", h(PASSWORD), created, "teacher", None))

    for idx, (name, grade, phone, days, ltime, pay_day, fee, book) in enumerate(STUDENTS, start=1):
        # 2) 학생
        cur = c.execute("""INSERT INTO students(name, grade, parent_phone, phone_last4, lesson_days, lesson_time,
                               pay_day, fee, current_book, start_date, active, created_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,1,?)""",
                        (name, grade, phone, phone[-4:], days, ltime, pay_day, fee, book, START.isoformat(), created))
        sid = cur.lastrowid

        # 3) 학부모·학생 계정 (p01 / s01 ...)
        c.execute("INSERT OR IGNORE INTO users VALUES(?,?,?,?,?)",
                  (f"p{idx:02d}", h(PASSWORD), created, "parent", sid))
        c.execute("INSERT OR IGNORE INTO users VALUES(?,?,?,?,?)",
                  (f"s{idx:02d}", h(PASSWORD), created, "student", sid))

        # 학생마다 성향을 다르게: 성실도(출석) · 연습량 · 실력 · 자주 막히는 부분
        diligence = random.uniform(0.6, 0.98)                            # 출석률
        focus = min(0.95, max(0.05, 0.3 + (diligence - 0.6) * 1.3 + random.gauss(0, 0.15)))  # 수업 집중도 (성실한 학생이 대체로 높게)
        skill = random.uniform(2.0, 3.4)                                  # 평가 점수의 출발점
        weak_tags = random.sample(DIFFICULTY_TAGS, 2)
        pieces = PIECES.get(book, ["연습곡"])
        p_idx, stage = 0, 0                         # 현재 곡 번호, 단계(0 시작 → 1 연습 중 → 2 완성)
        lessons = set(lesson_dates(days))
        d = START
        while d <= TODAY:
            piece = pieces[p_idx % len(pieces)]
            if d not in lessons or d >= TODAY or random.random() > diligence:   # 수업 없는 날 / 오늘(키오스크로 직접) / 결석
                d += timedelta(days=1)
                continue

            # ② 출석 (수업 시간 -10분 ~ +5분 사이 도착)
            arrive = ts(d, ltime, random.randint(-10, 5))
            hhmm = arrive[11:16]
            stay = random.randint(45, 70)
            leave = ts(d, hhmm, stay)
            msg_in = f"[해오름 피아노] {name} 학생이 {hhmm}에 학원에 도착했습니다. 오늘도 즐겁게 연주할게요 🎹"
            msg_out = (f"[해오름 피아노] {name} 학생이 {leave[11:16]}에 수업을 마치고 하원했습니다. "
                       f"(학원에 {stay}분) 오늘도 수고했어요 👏")
            c.execute("""INSERT INTO attendance(student_id, check_date, check_time, message, leave_time)
                         VALUES(?,?,?,?,?)""", (sid, d.isoformat(), hhmm, msg_in, leave[11:16]))
            read = (TODAY - d).days > 3 or random.random() < 0.5      # 최근 며칠 것만 일부 '안 읽음'

            for kind, msg, when in [("arrive", msg_in, arrive), ("leave", msg_out, leave)]:
                c.execute("INSERT INTO notifications(student_id, kind, message, created_at, read_at) VALUES(?,?,?,?,?)",
                          (sid, kind, msg, when, ts(d, leave[11:16], random.randint(1, 120)) if read else None))

            # ③ 진도 (곡마다 시작 → 연습 중 → 완성, 집 연습을 많이 할수록 빨리 완성)
            status = ["🌱 시작", "🎵 연습 중", "⭐ 완성"][stage]
            measures = "전체" if stage == 2 else f"1~{random.choice([8, 16, 24, 32])}마디"
            cur = c.execute("""INSERT INTO progress(student_id, lesson_date, book, piece, measures, status, comment,
                                   created_at) VALUES(?,?,?,?,?,?,?,?)""",
                            (sid, d.isoformat(), book, piece, measures, status, random.choice(COMMENTS[status]),
                             ts(d, ltime, 45)))
            pid = cur.lastrowid

            # ④ 수업 평가 (실력이 조금씩 늘고, 연습을 많이 한 날 더 높게) + 어려움 태그
            skill = min(4.6, skill + 0.005 + focus * 0.05)   # 꾸준히·집중해서 배울수록 빨리 성장
            def score(bias=0.0):
                return max(1, min(5, round(skill + bias + random.gauss(0, 0.6))))
            tags = [t for t in weak_tags if random.random() < 0.45]
            if random.random() < 0.2:
                tags.append(random.choice(DIFFICULTY_TAGS))
            c.execute("""INSERT INTO lesson_evals(progress_id, student_id, lesson_date, piece, rhythm, accuracy,
                             posture, expression, tags, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                      (pid, sid, d.isoformat(), piece, score(-0.4 if "리듬" in weak_tags else 0), score(),
                       score(0.2), score(-0.5), ",".join(dict.fromkeys(tags)), ts(d, ltime, 45)))

            if stage == 0:
                stage = 1
            elif stage == 1 and random.random() < min(0.85, 0.05 + focus * 0.55):
                stage = 2
            elif stage == 2:
                stage, p_idx = 0, p_idx + 1

            # ⑤ 하트 (곡 완성이면 꼭, 연습을 많이 했으면 더 자주)
            if status == "⭐ 완성":
                c.execute("INSERT INTO hearts(student_id, amount, reason, given_by, created_at) VALUES(?,?,?,?,?)",
                          (sid, 1, f"🎼 진도: {piece} ⭐ 완성", "teacher", ts(d, ltime, 46)))
            if random.random() < 0.2 + focus * 0.5:
                reason = random.choice(HEART_REASONS)
                c.execute("INSERT INTO hearts(student_id, amount, reason, given_by, created_at) VALUES(?,?,?,?,?)",
                          (sid, 1, reason, "teacher", ts(d, ltime, 40)))
            d += timedelta(days=1)

        # ⑥ 연주 영상: 완성한 첫 곡의 '첫 연주'와 '완성 연주' (예시 음원 + 제목 화면으로 mp4 생성)
        if idx <= 6:
            first = c.execute("""SELECT piece, MIN(lesson_date) s, MIN(CASE WHEN status='⭐ 완성' THEN lesson_date END) e
                                 FROM progress WHERE student_id=? GROUP BY piece
                                 HAVING e IS NOT NULL ORDER BY s LIMIT 1""", (sid,)).fetchone()
            if first:
                for kind, day, clean in [("🌱 첫 연주", first[1], False), ("⭐ 완성 연주", first[2], True)]:
                    vrel = f"{sid}/{day.replace('-', '')}_{'final' if clean else 'first'}.mp4"
                    wav = os.path.join(VIDEO_DIR, vrel.replace(".mp4", ".wav"))
                    make_wav(wav, clean)
                    ok = make_video(os.path.join(VIDEO_DIR, vrel), wav,
                                  f"{name} · {first[0]}", f"{'첫 연주' if not clean else '완성 연주'} · {day}")
                    os.remove(wav)
                    if ok:
                        c.execute("""INSERT INTO videos(student_id, piece, recorded_date, file_path, youtube_url, comment,
                                         uploaded_by, created_at) VALUES(?,?,?,?,?,?,?,?)""",
                                  (sid, first[0], day, vrel, None,
                                   "처음 배운 날 연주예요. 천천히 음을 찾아가요" if not clean
                                   else "끝까지 멈추지 않고 완주했어요! 손 모양도 좋아졌어요 👏",
                                   "teacher", ts(date.fromisoformat(day), ltime, 50)))
        # 보상 교환 (하트가 많이 모인 학생은 한 번 교환한 기록)
        total = c.execute("SELECT SUM(amount) FROM hearts WHERE student_id=?", (sid,)).fetchone()[0] or 0
        if total >= 25:
            c.execute("INSERT INTO hearts(student_id, amount, reason, given_by, created_at) VALUES(?,?,?,?,?)",
                      (sid, -10, "보상 교환: 🍬 간식 쿠폰", "teacher", ts(date(2026, 11, 1), "15:00")))

        # 7) 결제 (지난 달까지 완납, 이번 달은 결제일이 지난 학생 중 일부만 결제 → 연체 시연용)
        m = date(START.year, START.month, 1)
        while m <= TODAY:
            due = date(m.year, m.month, min(pay_day, 28))
            this_month = (m.year, m.month) == (TODAY.year, TODAY.month)
            if due <= TODAY and (not this_month or random.random() < 0.7):
                paid = due + timedelta(days=random.choice([0, 0, 0, 1, 2]))
                c.execute("INSERT INTO payments(student_id, pay_month, amount, method, paid_at) VALUES(?,?,?,?,?)",
                          (sid, m.strftime("%Y-%m"), fee, random.choice(["카드", "카드", "계좌이체", "지역화폐"]),
                           ts(paid, "15:00", random.randint(0, 180))))
            m = date(m.year + (m.month == 12), m.month % 12 + 1, 1)

    # 8) 학부모 코멘트 확인 기록 (가정마다 확인율이 다르게)
    for (sid, idx) in c.execute("SELECT id, id FROM students").fetchall():
        read_rate = random.uniform(0.2, 0.95)
        for (pid, d) in c.execute("SELECT id, lesson_date FROM progress WHERE student_id=? AND comment<>''",
                                  (sid,)).fetchall():
            if random.random() < read_rate:
                c.execute("INSERT OR IGNORE INTO comment_reads(userid, progress_id, read_at) VALUES(?,?,?)",
                          (f"p{idx:02d}", pid, ts(date.fromisoformat(d), f"{random.randint(18, 22)}:{random.randint(0, 59):02d}")))

    # 9) 앱 사용 로그 (사용자마다 자주 쓰는 메뉴가 다르게 → 로그인 시 메뉴 순서가 달라짐)
    users = [("teacher", TEACHER_MENUS)] + \
            [(f"p{i:02d}", FAMILY_MENUS) for i in range(1, len(STUDENTS) + 1)] + \
            [(f"s{i:02d}", [m for m in FAMILY_MENUS if m != "my_payment"]) for i in range(1, len(STUDENTS) + 1)]
    for uid, menus in users:
        weights = [random.uniform(0.2, 3) for _ in menus]   # 사용자별 메뉴 선호도
        for _ in range(random.randint(10, 40)):
            menu = random.choices(menus, weights)[0]
            day = START + timedelta(days=random.randint(0, (TODAY - START).days))
            c.execute("INSERT INTO learninghistory(userid, menu_id, wating_time, create_at) VALUES(?,?,?,?)",
                      (uid, menu, random.randint(3, 240), ts(day, f"{random.randint(8, 21):02d}:{random.randint(0, 59):02d}")))


FONT_CANDIDATES = ["C:/Windows/Fonts/malgun.ttf", "/System/Library/Fonts/AppleSDGothicNeo.ttc",
                   "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                   "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"]


def make_video(path, wav_path, title, sub):
    """예시 연주 영상: 제목 화면(이미지) + 녹음 소리 → mp4. ffmpeg·Pillow가 없으면 건너뜀"""
    if shutil.which("ffmpeg") is None:
        return False
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return False
    font_path = next((f for f in FONT_CANDIDATES if os.path.exists(f)), None)
    img = Image.new("RGB", (640, 360), (255, 248, 240))
    dr = ImageDraw.Draw(img)
    for i in range(14):                                  # 건반 그림
        dr.rectangle([40 + i * 40, 230, 78 + i * 40, 330], fill="white", outline=(60, 60, 60))
        if i % 7 not in (2, 6) and i < 13:
            dr.rectangle([66 + i * 40, 230, 92 + i * 40, 290], fill=(30, 30, 30))
    if font_path:
        f1, f2 = ImageFont.truetype(font_path, 40), ImageFont.truetype(font_path, 26)
        dr.text((40, 60), title, font=f1, fill=(50, 40, 40))
        dr.text((40, 130), sub + "  (테스트용 예시 영상)", font=f2, fill=(110, 90, 90))
    png = path.replace(".mp4", ".png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(png)
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", png, "-i", wav_path,
                        "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p", "-r", "5",
                        "-c:a", "aac", "-shortest", path])
    os.remove(png)
    return r.returncode == 0


def make_wav(path, clean, sr=8000):
    """'작은 별' 첫 소절을 사인파로 만든 짧은 예시 음원 (첫 연주는 느리고 틀린 음·박자 흔들림 포함)"""
    melody = [261.6, 261.6, 392.0, 392.0, 440.0, 440.0, 392.0, 0, 349.2, 349.2, 329.6, 329.6, 293.7, 293.7, 261.6]
    frames = bytearray()
    for i, f in enumerate(melody):
        dur = 0.32 if clean else 0.45 + random.uniform(-0.1, 0.25)
        if not clean and f and random.random() < 0.2:
            f *= random.choice([1.06, 0.94])            # 틀린 음
        if not clean and random.random() < 0.15:
            frames += b"\x00\x00" * int(sr * 0.4)      # 머뭇거림
        n = int(sr * dur)
        for t in range(n):
            env = min(1, t / 200) * (1 - t / n) ** 1.5   # 피아노처럼 감쇠
            v = 0 if not f else math.sin(2 * math.pi * f * t / sr) * env * 0.5
            frames += struct.pack("<h", int(v * 32767))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(bytes(frames))


def main():
    if "--reset" in sys.argv:
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
        shutil.rmtree(VIDEO_DIR, ignore_errors=True)
        print("기존 DB · 영상 폴더 삭제")
    conn = sqlite3.connect(DB_PATH)
    create_tables(conn)
    if conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]:
        print("⚠️ 이미 학생 데이터가 있어요. 새로 만들려면 --reset 옵션을 붙여 실행하세요.")
        return
    seed(conn)
    conn.commit()
    print(f"✅ 테스트 데이터 생성 완료 → {DB_PATH}")
    for t in ["users", "students", "attendance", "progress", "payments", "hearts",
              "lesson_evals", "videos", "notifications", "comment_reads", "learninghistory"]:
        print(f"   {t:16s} {conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]:>5}행")
    conn.close()


if __name__ == "__main__":
    main()
