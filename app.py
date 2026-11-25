"""
🎹 피아노학원 관리 웹앱 (Streamlit)
- 사용자 등록 / 로그인 (users: userid, password, created_at)
- 사이드바 라디오 메뉴
- learninghistory(userid, menu_id, wating_time, create_at) : 메뉴 클릭 시 저장, 체류 시간(초) 기록
- 로그아웃 후 재로그인 시 learninghistory 기준으로 메뉴 순서 재배치
- 학원 기능: 출석 키오스크(번호 뒷자리) / 학생 관리 / 진도 관리 / 결제 관리 / 하트 스티커

실행:  streamlit run app.py
"""
import hashlib
import os
import socket
import sqlite3
import time
from datetime import date, datetime, timedelta, time as dtime

import pandas as pd
import streamlit as st

# ─────────────────────────────────────────────
# 기본 설정
# ─────────────────────────────────────────────
# app.py와 같은 폴더에 DB 파일 생성 (Streamlit Cloud에서는 /mount/src/<저장소>/piano_academy.db)
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "piano_academy.db")
ACADEMY_NAME = "해오름 피아노"

MENUS = {
    "home": "🏠 홈",
    "attendance": "✅ 출석 관리",
    "students": "👩‍🎓 학생 관리",
    "progress": "🎼 진도 관리",
    "payment": "💳 결제 관리",
    "heart": "❤️ 하트 스티커",
    "growth": "📈 학습 이력",
    "usagelog": "🖥️ 앱 사용 로그",
    "dbadmin": "🗄️ DB 관리",
    # 학부모·학생용 메뉴
    "my_home": "🏠 한눈에 보기",
    "my_progress": "🎼 진도 기록",
    "my_heart": "❤️ 내 하트판",
    "my_attendance": "✅ 출석 기록",
    "my_payment": "💳 수강료 결제",
    "my_growth": "📈 학습 이력",
}
# 역할별로 보이는 메뉴 (기본 순서)
ROLE_MENUS = {
    "teacher": ["home", "attendance", "students", "progress", "payment", "heart", "growth", "usagelog", "dbadmin"],
    "parent": ["my_home", "my_growth", "my_progress", "my_heart", "my_attendance", "my_payment"],
    "student": ["my_home", "my_heart", "my_growth", "my_progress", "my_attendance"],
}

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
GRADES = ["유치", "초1", "초2", "초3", "초4", "초5", "초6", "중1", "중2", "중3", "고1", "고2", "고3", "성인"]
BOOKS = ["바이엘 상", "바이엘 하", "체르니 100", "체르니 30", "체르니 40", "부르크뮐러",
         "소나티네", "소나타", "하농", "동요/가요", "기타(직접 입력)"]
PROGRESS_STATUS = ["🌱 시작", "🎵 연습 중", "⭐ 완성"]
HEART_REASONS = ["🏠 숙제 완료", "🔥 연습 열심히", "⭐ 곡 완성", "🧍 바른 자세", "🎼 악보 잘 읽기", "😊 수업 태도"]
REWARDS = [("🍬 간식 쿠폰", 10), ("✏️ 예쁜 문구", 20), ("🎁 깜짝 선물", 30)]
PAY_METHODS = ["카드", "계좌이체", "현금", "지역화폐"]

# 학습 이력용 설정
EVAL_ITEMS = {"rhythm": "🥁 리듬·박자", "accuracy": "🎯 음 정확도", "posture": "✋ 손 모양·자세", "expression": "🎨 셈여림 표현"}
DIFFICULTY_TAGS = ["양손 맞추기", "손가락 번호", "리듬", "악보 읽기", "박자 유지", "셈여림", "페달", "도약·옥타브", "암보"]
VIDEO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "videos")        # 연주 영상 저장 폴더

st.set_page_config(page_title=f"{ACADEMY_NAME} 관리", page_icon="🎹", layout="wide")


# ─────────────────────────────────────────────
# DB 유틸
# ─────────────────────────────────────────────
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def run(sql, params=()):
    """INSERT/UPDATE/DELETE 실행 후 lastrowid 반환"""
    conn = get_conn()
    cur = conn.execute(sql, params)
    conn.commit()
    last_id = cur.lastrowid
    conn.close()
    return last_id


def fetch(sql, params=()):
    conn = get_conn()
    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]  # 위젯 옵션으로 쓰려면 dict로 변환
    conn.close()
    return rows


def to_df(sql, params=()):
    conn = get_conn()
    d = pd.read_sql_query(sql, conn, params=params)
    conn.close()
    return d


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_db():
    conn = get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users(
            userid      TEXT PRIMARY KEY,
            password    TEXT NOT NULL,          -- SHA-256 해시로 저장
            created_at  TEXT NOT NULL,
            role        TEXT DEFAULT 'teacher', -- teacher / parent / student
            student_id  INTEGER                 -- 학부모·학생 계정이 연결된 students.id
        );
        CREATE TABLE IF NOT EXISTS learninghistory(
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            userid      TEXT NOT NULL,
            menu_id     TEXT NOT NULL,
            wating_time INTEGER DEFAULT 0,      -- 체류 시간(초)
            create_at   TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS students(
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            grade        TEXT,
            parent_phone TEXT,
            phone_last4  TEXT NOT NULL,
            lesson_days  TEXT,                  -- 예: '월,수,금'
            lesson_time  TEXT,                  -- 예: '14:00'
            pay_day      INTEGER DEFAULT 1,     -- 매월 결제일(1~28)
            fee          INTEGER DEFAULT 150000,
            current_book TEXT,
            start_date   TEXT,
            active       INTEGER DEFAULT 1,
            created_at   TEXT
        );
        CREATE TABLE IF NOT EXISTS attendance(
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id  INTEGER NOT NULL,
            check_date  TEXT NOT NULL,
            check_time  TEXT NOT NULL,             -- 입장 시각
            message     TEXT,
            leave_time  TEXT                       -- 하원 시각
        );
        CREATE TABLE IF NOT EXISTS progress(
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id  INTEGER NOT NULL,
            lesson_date TEXT,
            book        TEXT,
            piece       TEXT,
            measures    TEXT,
            status      TEXT,
            comment     TEXT,
            created_at  TEXT
        );
        CREATE TABLE IF NOT EXISTS payments(
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id  INTEGER NOT NULL,
            pay_month   TEXT NOT NULL,          -- 'YYYY-MM'
            amount      INTEGER,
            method      TEXT,
            paid_at     TEXT
        );
        CREATE TABLE IF NOT EXISTS hearts(
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id  INTEGER NOT NULL,
            amount      INTEGER NOT NULL,       -- +지급 / -보상 교환
            reason      TEXT,
            given_by    TEXT,
            created_at  TEXT
        );
        -- ── 학습 이력 ──────────────────────────────
        CREATE TABLE IF NOT EXISTS lesson_evals(        -- 수업 평가 점수 + 어려움 유형 태그 (선생님 입력)
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            progress_id INTEGER,               -- progress.id (어느 수업 기록의 평가인지)
            student_id  INTEGER NOT NULL,
            lesson_date TEXT,
            piece       TEXT,
            rhythm      INTEGER,               -- 1~5점
            accuracy    INTEGER,
            posture     INTEGER,
            expression  INTEGER,
            tags        TEXT,                  -- 예: '양손 맞추기,리듬'
            created_at  TEXT
        );
        CREATE TABLE IF NOT EXISTS videos(              -- 🎬 선생님이 찍어 올린 연주 영상
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id    INTEGER NOT NULL,
            piece         TEXT,
            recorded_date TEXT,
            file_path     TEXT,                -- videos/ 폴더 기준 상대경로 (파일 업로드)
            youtube_url   TEXT,                -- 또는 유튜브 '일부 공개' 링크
            comment       TEXT,                -- 선생님 한마디
            uploaded_by   TEXT,
            created_at    TEXT
        );
        CREATE TABLE IF NOT EXISTS notifications(       -- 🔔 학부모 알림함 (입장·하원 등)
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id  INTEGER NOT NULL,
            kind        TEXT,                  -- arrive / leave
            message     TEXT,
            created_at  TEXT,
            read_at     TEXT                   -- 학부모가 확인한 시각 (NULL이면 안 읽음)
        );
        -- ── 앱 사용 로그 ───────────────────────────
        CREATE TABLE IF NOT EXISTS comment_reads(       -- 학부모·학생이 선생님 코멘트를 읽은 기록
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            userid      TEXT NOT NULL,
            progress_id INTEGER NOT NULL,
            read_at     TEXT,
            UNIQUE(userid, progress_id)
        );
        """
    )
    conn.commit()
    conn.close()

    # 이미 만들어진 DB에 새 컬럼 추가 (ALTER TABLE 마이그레이션)
    cols = [r["name"] for r in fetch("PRAGMA table_info(users)")]
    if "role" not in cols:
        run("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'teacher'")   # 기존 계정은 선생님으로
    if "student_id" not in cols:
        run("ALTER TABLE users ADD COLUMN student_id INTEGER")            # 학부모·학생 → students.id
    if "leave_time" not in [r["name"] for r in fetch("PRAGMA table_info(attendance)")]:
        run("ALTER TABLE attendance ADD COLUMN leave_time TEXT")          # 하원 시각


# ─────────────────────────────────────────────
# 1. 사용자 등록 / 로그인 (역할: teacher / parent / student)
# ─────────────────────────────────────────────
ROLES = {"teacher": "👩‍🏫 선생님", "parent": "👪 학부모", "student": "🧒 학생"}


def teacher_code():
    """선생님 가입 인증코드: Streamlit Cloud의 Secrets에 TEACHER_CODE로 설정 (없으면 기본값)"""
    try:
        return st.secrets.get("TEACHER_CODE", "piano1234")
    except Exception:
        return "piano1234"


def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()


def register_user(userid, password, role="teacher", student_id=None):
    if fetch("SELECT 1 FROM users WHERE userid=?", (userid,)):
        return False
    run("INSERT INTO users(userid, password, created_at, role, student_id) VALUES(?,?,?,?,?)",
        (userid, hash_pw(password), now_str(), role, student_id))
    return True


def check_login(userid, password):
    """로그인 성공 시 사용자 정보(dict), 실패 시 None"""
    rows = fetch("SELECT userid, role, student_id FROM users WHERE userid=? AND password=?",
                 (userid, hash_pw(password)))
    return rows[0] if rows else None


def find_student(name, last4):
    """학부모·학생 가입 시 학원에 등록된 학생인지 확인 (이름 + 전화 뒷자리)"""
    rows = fetch("SELECT * FROM students WHERE name=? AND phone_last4=? AND active=1", (name, last4))
    return rows[0] if rows else None


# ─────────────────────────────────────────────
# 3·4. learninghistory : 체류 시간 기록 & 메뉴 재정렬
# ─────────────────────────────────────────────
def get_menu_order(userid, role="teacher"):
    """누적 체류시간(1순위) → 클릭 횟수(2순위) 순으로 정렬, 기록 없는 메뉴는 기본 순서로 뒤에
    (역할별로 볼 수 있는 메뉴만)"""
    allowed = ROLE_MENUS[role]
    rows = fetch(
        """SELECT menu_id, SUM(wating_time) AS total, COUNT(*) AS cnt
           FROM learninghistory WHERE userid=?
           GROUP BY menu_id ORDER BY total DESC, cnt DESC""",
        (userid,),
    )
    ordered = [r["menu_id"] for r in rows if r["menu_id"] in allowed]
    return ordered + [m for m in allowed if m not in ordered]


def save_dwell():
    """현재 열려 있는 메뉴 기록의 체류 시간(초)을 갱신"""
    hid = st.session_state.get("hist_id")
    if hid:
        sec = int(time.time() - st.session_state.menu_start)
        run("UPDATE learninghistory SET wating_time=? WHERE id=?", (sec, hid))


def track_menu(menu_id):
    """메뉴가 바뀌면: 이전 메뉴 체류시간 확정 → 새 메뉴 클릭 기록 저장"""
    if st.session_state.get("current_menu") != menu_id:
        save_dwell()
        st.session_state.hist_id = run(
            "INSERT INTO learninghistory(userid, menu_id, wating_time, create_at) VALUES(?,?,0,?)",
            (st.session_state.userid, menu_id, now_str()),
        )
        st.session_state.current_menu = menu_id
        st.session_state.menu_start = time.time()
    else:
        # 같은 메뉴 안에서 버튼을 누를 때마다 중간 저장 (로그아웃 없이 창을 닫는 경우 대비)
        save_dwell()


def logout():
    save_dwell()
    for k in list(st.session_state.keys()):
        del st.session_state[k]


def fmt_sec(sec):
    sec = int(sec or 0)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}시간 {m}분"
    if m:
        return f"{m}분 {s}초"
    return f"{s}초"


# ─────────────────────────────────────────────
# 학원 공통 함수
# ─────────────────────────────────────────────
def active_students():
    return fetch("SELECT * FROM students WHERE active=1 ORDER BY name")


def student_label(s):
    return f"{s['name']} ({s['grade'] or '-'})"


def select_student(label="학생 선택", key=None):
    studs = active_students()
    if not studs:
        st.info("등록된 학생이 없어요. **👩‍🎓 학생 관리**에서 먼저 학생을 등록해 주세요.")
        return None
    s = st.selectbox(label, studs, format_func=student_label, key=key)
    return s


def heart_balance(student_id):
    r = fetch("SELECT COALESCE(SUM(amount),0) AS t FROM hearts WHERE student_id=?", (student_id,))
    return r[0]["t"]


def give_heart(student_id, amount, reason):
    run("INSERT INTO hearts(student_id, amount, reason, given_by, created_at) VALUES(?,?,?,?,?)",
        (student_id, amount, reason, st.session_state.userid, now_str()))


def payment_status(s, today=None):
    """이번 달 결제 상태: 완료 / 연체 / 임박(D-3 이내) / 예정"""
    today = today or date.today()
    ym = today.strftime("%Y-%m")
    paid = fetch("SELECT * FROM payments WHERE student_id=? AND pay_month=?", (s["id"], ym))
    if paid:
        return "✅ 완료", paid[0]["paid_at"][:10]
    due = date(today.year, today.month, min(max(int(s["pay_day"] or 1), 1), 28))
    d = (due - today).days
    if d < 0:
        return "🔴 연체", f"{-d}일 지남"
    if d <= 3:
        return "🟠 임박", "오늘" if d == 0 else f"D-{d}"
    return "⚪ 예정", f"D-{d}"


def mark_read(progress_ids):
    """학부모·학생이 선생님 코멘트를 화면에서 본 기록 (같은 코멘트는 한 번만)"""
    if st.session_state.get("role") == "teacher":
        return
    for pid in progress_ids:
        run("INSERT OR IGNORE INTO comment_reads(userid, progress_id, read_at) VALUES(?,?,?)",
            (st.session_state.userid, pid, now_str()))


def student_pieces(student_id):
    """학생이 배운(배우는) 곡 목록 - 최근 순"""
    rows = fetch("""SELECT piece, MAX(lesson_date) d FROM progress WHERE student_id=? AND piece<>''
                    GROUP BY piece ORDER BY d DESC""", (student_id,))
    return [r["piece"] for r in rows]


def send_sms(phone, text):
    """
    학부모 문자 발송 자리.
    실제 발송은 솔라피(SOLAPI)·알리고 같은 문자 API를 연동해야 합니다
    (API 키, 사전 등록한 발신번호 필요, 건당 요금 발생).
    데모 버전에서는 실제로 보내지 않고 출석 기록에 메시지만 남깁니다.
    """
    return True


def seed_samples():
    today = date.today()
    samples = [
        ("김하린", "초3", "010-1234-5678", "월,수,금", "14:00", 5, 150000, "체르니 100"),
        ("이서준", "초5", "010-2345-1111", "화,목", "15:00", 10, 140000, "체르니 30"),
        ("박지우", "초1", "010-3456-2222", "월,화,수,목,금", "13:30", 25, 180000, "바이엘 하"),
        ("최유나", "중1", "010-9876-5678", "수,토", "17:00", 1, 160000, "소나티네"),  # 뒷자리 중복 예시
        ("정민호", "초4", "010-5555-3333", "월,목", "16:00", 15, 140000, "부르크뮐러"),
    ]
    ids = []
    for n, g, p, days, t, pd_, fee, book in samples:
        ids.append(run(
            """INSERT INTO students(name, grade, parent_phone, phone_last4, lesson_days, lesson_time,
                                    pay_day, fee, current_book, start_date, active, created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,1,?)""",
            (n, g, p, p[-4:], days, t, pd_, fee, book, "2026-03-02", now_str())))
    # 하트·진도·결제 샘플
    for sid, cnt in zip(ids, [12, 7, 3, 18, 9]):
        for i in range(cnt):
            give_heart(sid, 1, HEART_REASONS[i % len(HEART_REASONS)])
    run("""INSERT INTO progress(student_id, lesson_date, book, piece, measures, status, comment, created_at)
           VALUES(?,?,?,?,?,?,?,?)""",
        (ids[0], today.isoformat(), "체르니 100", "12번", "1~16마디", "🎵 연습 중",
         "왼손 리듬이 조금 빨라짐. 메트로놈 60으로 연습", now_str()))
    run("INSERT INTO payments(student_id, pay_month, amount, method, paid_at) VALUES(?,?,?,?,?)",
        (ids[3], today.strftime("%Y-%m"), 160000, "카드", now_str()))


# ─────────────────────────────────────────────
# 페이지: 로그인 / 회원가입
# ─────────────────────────────────────────────
def page_login():
    _, mid, _ = st.columns([1, 1.4, 1])
    with mid:
        st.markdown(f"<h1 style='text-align:center'>🎹 {ACADEMY_NAME}</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align:center;color:gray'>진도 · 출석 · 결제 · 하트 스티커를 한 곳에서</p>",
                    unsafe_allow_html=True)
        tab_login, tab_join = st.tabs(["🔑 로그인", "📝 사용자 등록"])

        with tab_login:
            with st.form("login_form"):
                uid = st.text_input("아이디")
                pw = st.text_input("비밀번호", type="password")
                ok = st.form_submit_button("로그인", use_container_width=True, type="primary")
            if ok:
                user = check_login(uid.strip(), pw)
                if user:
                    role = user["role"] or "teacher"
                    st.session_state.userid = user["userid"]
                    st.session_state.role = role
                    st.session_state.student_id = user["student_id"]
                    order = get_menu_order(user["userid"], role)   # ← 4. 로그인 시 메뉴 재배치
                    st.session_state.menu_order = order
                    st.session_state.menu_radio = order[0]          # 가장 많이 머문 메뉴로 바로 진입
                    st.rerun()
                else:
                    st.error("아이디 또는 비밀번호가 맞지 않아요.")

        with tab_join:
            # 역할 선택은 form 밖에 둬야 선택에 따라 입력칸이 바로 바뀜
            role = st.radio("가입 유형", list(ROLES), format_func=ROLES.get, horizontal=True, key="join_role")
            with st.form("join_form", clear_on_submit=True):
                new_id = st.text_input("아이디")
                new_pw = st.text_input("비밀번호 (4자 이상)", type="password")
                new_pw2 = st.text_input("비밀번호 확인", type="password")
                if role == "teacher":
                    code = st.text_input("선생님 인증코드", type="password",
                                         help="원장님께 받은 코드 (Secrets의 TEACHER_CODE)")
                else:
                    st.caption("학원에 등록된 학생 정보로 확인해요.")
                    c1, c2 = st.columns(2)
                    s_name = c1.text_input("학생 이름")
                    s_last4 = c2.text_input("학부모 전화 뒷자리 4자리", max_chars=4)
                ok2 = st.form_submit_button("등록하기", use_container_width=True)
            if ok2:
                new_id = new_id.strip()
                student_id = None
                if not new_id or len(new_pw) < 4:
                    st.error("아이디를 입력하고, 비밀번호는 4자 이상으로 해주세요.")
                    return
                if new_pw != new_pw2:
                    st.error("비밀번호 확인이 일치하지 않아요.")
                    return
                if role == "teacher":
                    if code != teacher_code():
                        st.error("선생님 인증코드가 맞지 않아요.")
                        return
                else:
                    s = find_student(s_name.strip(), s_last4.strip())
                    if not s:
                        st.error("학원에 등록된 학생을 찾을 수 없어요. 이름과 번호를 확인하거나 선생님께 문의해 주세요.")
                        return
                    student_id = s["id"]
                if register_user(new_id, new_pw, role, student_id):
                    st.success(f"{ROLES[role]} 계정 등록 완료! 로그인 탭에서 로그인해 주세요.")
                else:
                    st.error("이미 있는 아이디예요.")


# ─────────────────────────────────────────────
# 페이지: 홈
# ─────────────────────────────────────────────
def page_home():
    today = date.today()
    wd = WEEKDAYS[today.weekday()]
    st.title("🏠 오늘의 학원")
    st.caption(f"{today:%Y년 %m월 %d일} ({wd})")

    studs = active_students()
    todays = [s for s in studs if wd in (s["lesson_days"] or "").split(",")]
    att = {r["student_id"]: r for r in fetch("SELECT * FROM attendance WHERE check_date=?", (today.isoformat(),))}
    statuses = [(s, *payment_status(s, today)) for s in studs]
    need_pay = [x for x in statuses if x[1].startswith(("🔴", "🟠"))]
    month_hearts = fetch("SELECT COALESCE(SUM(amount),0) t FROM hearts WHERE amount>0 AND created_at LIKE ?",
                         (today.strftime("%Y-%m") + "%",))[0]["t"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("재원생", f"{len(studs)}명")
    c2.metric("오늘 출석", f"{len(att)} / {len(todays)}명")
    c3.metric("결제 확인 필요", f"{len(need_pay)}명")
    c4.metric("이번 달 하트", f"❤️ {month_hearts}개")

    left, right = st.columns(2)
    with left:
        st.subheader(f"📅 오늘({wd}) 수업")
        if not todays:
            st.write("오늘 수업 예정인 학생이 없어요.")
        for s in sorted(todays, key=lambda x: x["lesson_time"] or ""):
            a = att.get(s["id"])
            mark = "⏳ 아직" if not a else f"✅ {a['check_time']} 도착" + (f" · 👋 {a['leave_time']} 하원" if a["leave_time"] else "")
            st.write(f"**{s['lesson_time']}** · {s['name']} ({s['current_book'] or '-'}) — {mark}")
    with right:
        st.subheader("💳 결제 확인 필요")
        if not need_pay:
            st.write("모두 정상이에요 👍")
        for s, stt, info in need_pay:
            st.write(f"{stt} {s['name']} — 매월 {s['pay_day']}일 · {s['fee']:,}원 ({info})")

        st.subheader("❤️ 하트 TOP 3")
        top = fetch("""SELECT s.name, COALESCE(SUM(h.amount),0) t FROM students s
                       LEFT JOIN hearts h ON h.student_id=s.id WHERE s.active=1
                       GROUP BY s.id ORDER BY t DESC LIMIT 3""")
        for i, r in enumerate(top):
            st.write(f"{['🥇', '🥈', '🥉'][i]} {r['name']} — ❤️ {r['t']}개")


# ─────────────────────────────────────────────
# 출석 키오스크 (헬스장 방식: 로그인 없이 번호 4자리 → 입장 / 하원)
# ─────────────────────────────────────────────
KIOSK_RESET_SEC = 4     # 결과 화면을 보여준 뒤 처음 화면으로 돌아가는 시간(초)
MIN_STAY_MIN = 10       # 입장 후 이 시간 안에 다시 누르면 하원으로 처리하지 않음 (실수 방지)


def kiosk_key():
    """키오스크 주소의 비밀키: Secrets의 KIOSK_KEY (없으면 기본값)"""
    try:
        return str(st.secrets.get("KIOSK_KEY", "haeorum"))
    except Exception:
        return "haeorum"


def local_ip():
    """같은 와이파이의 태블릿이 접속할 이 PC의 IP (UDP 연결 흉내만 내고 실제 전송은 없음)"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except Exception:
        return None


def notify_parent(s, kind, msg):
    """학부모 알림: 앱 안 알림함에 저장 + 문자 발송 자리(send_sms)"""
    run("INSERT INTO notifications(student_id, kind, message, created_at) VALUES(?,?,?,?)",
        (s["id"], kind, msg, now_str()))
    send_sms(s["parent_phone"], msg)


def kiosk_action(s, force=None):
    """입장/하원을 자동으로 판단해서 처리. force='in'/'out'이면 그대로 처리(선생님 수동 처리용)"""
    today = date.today().isoformat()
    now = datetime.now()
    t = now.strftime("%H:%M")
    rows = fetch("SELECT * FROM attendance WHERE student_id=? AND check_date=?", (s["id"], today))
    action = force or ("in" if not rows else "out")

    if action == "in":
        if rows:
            return dict(kind="info", title=f"{s['name']} 학생은 이미 입장했어요 😊",
                        sub=f"{rows[0]['check_time']} 입장", msg=None)
        msg = f"[{ACADEMY_NAME}] {s['name']} 학생이 {t}에 학원에 도착했습니다. 오늘도 즐겁게 연주할게요 🎹"
        run("INSERT INTO attendance(student_id, check_date, check_time, message) VALUES(?,?,?,?)",
            (s["id"], today, t, msg))
        notify_parent(s, "arrive", msg)
        return dict(kind="in", title=f"🎹 {s['name']} 학생, 반가워요!",
                    sub=f"{t} 입장  ·  모은 하트 ❤️ {heart_balance(s['id'])}개", msg=msg)

    # 하원
    if not rows:
        return dict(kind="info", title=f"{s['name']} 학생은 오늘 입장 기록이 없어요", sub="선생님께 말씀해 주세요", msg=None)
    r = rows[0]
    if r["leave_time"]:
        return dict(kind="info", title=f"{s['name']} 학생은 {r['leave_time']}에 하원했어요", sub="", msg=None)
    stay = int((now - datetime.combine(date.today(), datetime.strptime(r["check_time"], "%H:%M").time()))
               .total_seconds() // 60)
    if force is None and stay < MIN_STAY_MIN:
        return dict(kind="info", title=f"{s['name']} 학생은 {r['check_time']}에 입장했어요 😊",
                    sub="수업 끝나고 집에 갈 때 다시 눌러 주세요", msg=None)
    msg = f"[{ACADEMY_NAME}] {s['name']} 학생이 {t}에 수업을 마치고 하원했습니다. (학원에 {stay}분) 오늘도 수고했어요 👏"
    run("UPDATE attendance SET leave_time=? WHERE id=?", (t, r["id"]))
    notify_parent(s, "leave", msg)
    return dict(kind="out", title=f"👋 {s['name']} 학생, 잘 가요!", sub=f"{t} 하원  ·  오늘 {stay}분 함께했어요", msg=msg)


KIOSK_CSS = """
<style>
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"], [data-testid="stHeader"],
[data-testid="stToolbar"], footer {display: none !important;}
.block-container {padding-top: 1.2rem !important; max-width: 560px !important;}
div[data-testid="stButton"] button {height: 78px; border-radius: 18px;}
div[data-testid="stButton"] button p {font-size: 32px !important; font-weight: 700;}
.k-title {text-align: center; font-size: 34px; font-weight: 800; margin-bottom: 0;}
.k-guide {text-align: center; font-size: 20px; color: #555;}
.k-pin {text-align: center; font-size: 54px; letter-spacing: 20px; margin: 4px 0 14px;}
.k-result {text-align: center; padding: 56px 12px; border-radius: 26px; margin-top: 40px;}
</style>
"""


def kp_press(k):
    pin = st.session_state.get("pin", "")
    if k == "←":
        pin = pin[:-1]
    elif k == "C":
        pin = ""
    elif len(pin) < 4:
        pin += k
    st.session_state.pin = pin


def kp_submit():
    pin = st.session_state.get("pin", "")
    st.session_state.pin = ""
    matches = fetch("SELECT * FROM students WHERE phone_last4=? AND active=1", (pin,))
    if not matches:
        st.session_state.kiosk_result = dict(kind="err", title="등록되지 않은 번호예요 🤔",
                                             sub="번호를 다시 확인하거나 선생님께 말씀해 주세요", msg=None)
    elif len(matches) == 1:
        st.session_state.kiosk_result = kiosk_action(matches[0])
    else:
        st.session_state.kiosk_dup = [m["id"] for m in matches]   # 형제처럼 번호가 같으면 이름 선택


def kp_pick(sid):
    st.session_state.pop("kiosk_dup", None)
    if sid is not None:
        st.session_state.kiosk_result = kiosk_action(fetch("SELECT * FROM students WHERE id=?", (sid,))[0])


def page_kiosk():
    st.markdown(KIOSK_CSS, unsafe_allow_html=True)
    ss = st.session_state
    ss.setdefault("pin", "")

    # ① 결과 화면 → 몇 초 뒤 자동으로 처음 화면
    res = ss.get("kiosk_result")
    if res:
        bg = {"in": "#E8F5E9", "out": "#E3F2FD", "err": "#FFEBEE"}.get(res["kind"], "#FFF8E1")
        sent = "<div style='font-size:19px;margin-top:22px;color:#555'>📩 보호자에게 알림을 보냈어요</div>" if res["msg"] else ""
        st.markdown(f"<div class='k-result' style='background:{bg}'>"
                    f"<div style='font-size:40px;font-weight:800'>{res['title']}</div>"
                    f"<div style='font-size:24px;margin-top:14px'>{res['sub']}</div>{sent}</div>",
                    unsafe_allow_html=True)
        time.sleep(KIOSK_RESET_SEC)
        ss.pop("kiosk_result", None)
        st.rerun()

    st.markdown(f"<p class='k-title'>🎹 {ACADEMY_NAME}</p>", unsafe_allow_html=True)

    # ② 번호가 같은 학생이 여러 명 → 이름 선택
    if ss.get("kiosk_dup"):
        st.markdown("<p class='k-guide'>내 이름을 눌러 주세요</p>", unsafe_allow_html=True)
        for sid in ss.kiosk_dup:
            s = fetch("SELECT name FROM students WHERE id=?", (sid,))[0]
            st.button(s["name"], key=f"pick_{sid}", on_click=kp_pick, args=(sid,), use_container_width=True)
        st.button("↩ 취소", key="pick_cancel", on_click=kp_pick, args=(None,), use_container_width=True)
        return

    # ③ 숫자 키패드
    pin = ss.pin
    st.markdown("<p class='k-guide'>보호자 전화번호 <b>뒷자리 4자리</b>를 눌러 주세요</p>", unsafe_allow_html=True)
    st.markdown(f"<div class='k-pin'>{'●' * len(pin)}{'○' * (4 - len(pin))}</div>", unsafe_allow_html=True)
    for row in [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"], ["C", "0", "←"]]:
        cols = st.columns(3)
        for col, k in zip(cols, row):
            col.button(k, key=f"kp_{k}", on_click=kp_press, args=(k,), use_container_width=True)
    st.button("입장 / 하원", key="kp_ok", type="primary", on_click=kp_submit,
              disabled=len(pin) < 4, use_container_width=True)


# ─────────────────────────────────────────────
# 페이지: 출석 관리 (선생님)
# ─────────────────────────────────────────────
def show_action_result(res):
    (st.success if res["kind"] in ("in", "out") else st.info)(f"{res['title']}  {res['sub']}")
    if res["msg"]:
        st.caption(f"📩 학부모 알림: {res['msg']}")


def page_attendance():
    st.title("✅ 출석 관리")
    tab_today, tab_kiosk, tab_book = st.tabs(["📋 오늘 등원 현황", "📱 키오스크 설정", "🗓️ 출석부"])

    with tab_today:
        today = date.today()
        wd = WEEKDAYS[today.weekday()]
        studs = [s for s in active_students() if wd in (s["lesson_days"] or "").split(",")]
        att = {r["student_id"]: r for r in fetch("SELECT * FROM attendance WHERE check_date=?", (today.isoformat(),))}
        extra = [fetch("SELECT * FROM students WHERE id=?", (sid,))[0] for sid in att if sid not in {s["id"] for s in studs}]
        rows = []
        for s in sorted(studs + extra, key=lambda x: x["lesson_time"] or ""):
            a = att.get(s["id"])
            state = "⏳ 미등원" if not a else ("👋 하원" if a["leave_time"] else "🎹 수업 중")
            rows.append({"수업시간": s["lesson_time"], "이름": s["name"], "상태": state,
                         "도착": a["check_time"] if a else "", "하원": (a["leave_time"] or "") if a else ""})
        c1, c2, c3 = st.columns(3)
        c1.metric("오늘 수업", f"{len(studs)}명")
        c2.metric("수업 중", f"{sum(r['상태'] == '🎹 수업 중' for r in rows)}명")
        c3.metric("하원", f"{sum(r['상태'] == '👋 하원' for r in rows)}명")
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        if st.button("🔄 새로고침"):
            st.rerun()

        st.subheader("✋ 수동 처리 (번호를 잊었을 때)")
        s = select_student(key="manual_sel")
        if s:
            c1, c2 = st.columns(2)
            if c1.button("🎹 입장 처리", use_container_width=True):
                show_action_result(kiosk_action(s, "in"))
            if c2.button("👋 하원 처리", use_container_width=True):
                show_action_result(kiosk_action(s, "out"))

    with tab_kiosk:
        key = kiosk_key()
        ip = local_ip()
        st.markdown("학원 입구 태블릿에서 아래 주소를 열어 두세요. **로그인 없이 출석 키패드만** 보여요.")
        st.code(f"http://{ip or '이PC의IP'}:8501/?kiosk={key}", language=None)
        st.link_button("🖥️ 이 PC에서 키오스크 화면 열어보기", f"/?kiosk={key}")
        st.markdown(f"""
**태블릿 설정 방법**
1. 앱을 `streamlit run app.py --server.address 0.0.0.0` 으로 실행해요. (태블릿이 PC에 접속할 수 있게)
2. 태블릿을 PC와 **같은 와이파이**에 연결하고 위 주소를 열어요.
3. 브라우저 메뉴 → **홈 화면에 추가**하면 전체 화면 앱처럼 열려요. 화면 꺼짐 시간은 '안 함'으로 바꿔 두세요.

**사용 방법:** 학생이 번호 4자리 → [입장 / 하원]
- 오늘 처음 누르면 **입장**, 다시 누르면 **하원**으로 자동 처리돼요. (입장 후 {MIN_STAY_MIN}분 안에는 하원 처리 안 됨)
- 입장·하원 때마다 출석부에 기록되고, 학부모 알림함과 문자 발송 자리(`send_sms`)로 알림이 가요.
- 주소의 비밀키는 Secrets의 `KIOSK_KEY`로 바꿀 수 있어요. 키가 틀리면 화면이 열리지 않아요.
""")

    with tab_book:
        d = st.date_input("날짜", value=date.today())
        day_df = to_df("""SELECT s.name AS 이름, s.grade AS 학년, a.check_time AS 도착, a.leave_time AS 하원
                          FROM attendance a JOIN students s ON s.id=a.student_id
                          WHERE a.check_date=? ORDER BY a.check_time""", (d.isoformat(),))
        st.write(f"**{d:%m월 %d일} 출석 {len(day_df)}명**")
        st.dataframe(day_df, hide_index=True, use_container_width=True)

        ym = d.strftime("%Y-%m")
        st.write(f"**{d:%Y년 %m월} 학생별 출석 횟수**")
        mon_df = to_df("""SELECT s.name AS 이름, s.lesson_days AS 수강요일, COUNT(a.id) AS 출석횟수
                          FROM students s LEFT JOIN attendance a
                            ON a.student_id=s.id AND a.check_date LIKE ?
                          WHERE s.active=1 GROUP BY s.id ORDER BY 출석횟수 DESC""", (ym + "%",))
        st.dataframe(mon_df, hide_index=True, use_container_width=True)


# ─────────────────────────────────────────────
# 페이지: 학생 관리
# ─────────────────────────────────────────────
def student_form(prefix, s=None):
    """등록/수정 공용 입력 폼. 입력값 dict 반환"""
    c1, c2, c3 = st.columns(3)
    name = c1.text_input("이름", value=s["name"] if s else "", key=f"{prefix}_name")
    grade = c2.selectbox("학년", GRADES, index=GRADES.index(s["grade"]) if s and s["grade"] in GRADES else 3,
                         key=f"{prefix}_grade")
    phone = c3.text_input("학부모 연락처", value=s["parent_phone"] if s else "", placeholder="010-0000-0000",
                          key=f"{prefix}_phone")
    c4, c5 = st.columns([2, 1])
    days = c4.multiselect("수강 요일", WEEKDAYS,
                          default=(s["lesson_days"].split(",") if s and s["lesson_days"] else []),
                          key=f"{prefix}_days")
    t_default = datetime.strptime(s["lesson_time"], "%H:%M").time() if s and s["lesson_time"] else dtime(14, 0)
    ltime = c5.time_input("수업 시간", value=t_default, step=1800, key=f"{prefix}_time")
    c6, c7, c8 = st.columns(3)
    pay_day = c6.number_input("매월 결제일", 1, 28, value=int(s["pay_day"]) if s else 1, key=f"{prefix}_payday")
    fee = c7.number_input("월 수강료(원)", 0, 1_000_000, value=int(s["fee"]) if s else 150000, step=10000,
                          key=f"{prefix}_fee")
    cur = s["current_book"] if s else BOOKS[0]
    book = c8.selectbox("현재 교재", BOOKS, index=BOOKS.index(cur) if cur in BOOKS else len(BOOKS) - 1,
                        key=f"{prefix}_book")
    if book == "기타(직접 입력)":
        book = st.text_input("교재 이름", value=cur if cur not in BOOKS else "", key=f"{prefix}_book_etc")
    return dict(name=name.strip(), grade=grade, phone=phone.strip(), days=",".join(
        [d for d in WEEKDAYS if d in days]), time=ltime.strftime("%H:%M"), pay_day=pay_day, fee=fee, book=book)


def valid_student(v):
    digits = "".join(ch for ch in v["phone"] if ch.isdigit())
    if not v["name"]:
        st.error("이름을 입력해 주세요.")
        return None
    if len(digits) < 8:
        st.error("학부모 연락처를 정확히 입력해 주세요. (뒷자리 4자리가 출석 번호가 돼요)")
        return None
    return digits[-4:]


def page_students():
    st.title("👩‍🎓 학생 관리")
    tab_list, tab_add, tab_edit = st.tabs(["📋 학생 목록", "➕ 신규 등록", "✏️ 수정 · 퇴원"])

    with tab_list:
        d = to_df("""SELECT s.name AS 이름, s.grade AS 학년, s.lesson_days AS 수강요일, s.lesson_time AS 시간,
                            s.current_book AS 현재교재, s.pay_day AS 결제일, s.fee AS 수강료,
                            s.phone_last4 AS 출석번호, COALESCE(SUM(h.amount),0) AS 하트,
                            (SELECT GROUP_CONCAT(u.userid || '(' || u.role || ')', ', ')
                               FROM users u WHERE u.student_id = s.id) AS 연결계정
                     FROM students s LEFT JOIN hearts h ON h.student_id=s.id
                     WHERE s.active=1 GROUP BY s.id ORDER BY s.name""")
        st.write(f"재원생 **{len(d)}명**")
        st.dataframe(d, hide_index=True, use_container_width=True)
        if d.empty and st.button("🧪 시연용 샘플 학생 5명 넣기"):
            seed_samples()
            st.rerun()

    with tab_add:
        v = student_form("add")
        if st.button("등록하기", type="primary"):
            last4 = valid_student(v)
            if last4:
                run("""INSERT INTO students(name, grade, parent_phone, phone_last4, lesson_days, lesson_time,
                                            pay_day, fee, current_book, start_date, active, created_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,1,?)""",
                    (v["name"], v["grade"], v["phone"], last4, v["days"], v["time"], v["pay_day"], v["fee"],
                     v["book"], date.today().isoformat(), now_str()))
                st.success(f"{v['name']} 학생 등록 완료! 출석 번호는 **{last4}** 이에요.")

    with tab_edit:
        s = select_student(key="edit_sel")
        if s:
            v = student_form(f"edit{s['id']}", s)
            b1, b2 = st.columns([1, 5])
            if b1.button("저장", type="primary"):
                last4 = valid_student(v)
                if last4:
                    run("""UPDATE students SET name=?, grade=?, parent_phone=?, phone_last4=?, lesson_days=?,
                               lesson_time=?, pay_day=?, fee=?, current_book=? WHERE id=?""",
                        (v["name"], v["grade"], v["phone"], last4, v["days"], v["time"], v["pay_day"], v["fee"],
                         v["book"], s["id"]))
                    st.success("저장했어요.")
            if b2.button("🚪 퇴원 처리"):
                run("UPDATE students SET active=0 WHERE id=?", (s["id"],))
                st.success(f"{s['name']} 학생을 퇴원 처리했어요. (기록은 보관됩니다)")
                st.rerun()


# ─────────────────────────────────────────────
# 페이지: 진도 관리
# ─────────────────────────────────────────────
def page_progress():
    st.title("🎼 진도 관리")
    s = select_student(key="prog_sel")
    if not s:
        return

    done = fetch("SELECT COUNT(*) c FROM progress WHERE student_id=? AND status=?", (s["id"], PROGRESS_STATUS[2]))[0]["c"]
    last = fetch("SELECT * FROM progress WHERE student_id=? ORDER BY lesson_date DESC, id DESC LIMIT 1", (s["id"],))
    c1, c2, c3 = st.columns(3)
    c1.metric("현재 교재", s["current_book"] or "-")
    c2.metric("완성한 곡", f"⭐ {done}곡")
    c3.metric("보유 하트", f"❤️ {heart_balance(s['id'])}개")
    if last:
        l = last[0]
        st.info(f"**지난 수업 메모** ({l['lesson_date']}) · {l['book']} {l['piece']} {l['measures'] or ''} "
                f"— {l['status']}\n\n{l['comment'] or ''}")

    # 최근 수업에서 자주 어려워한 부분 (지난 평가 태그)
    recent_tags = to_df("SELECT tags FROM lesson_evals WHERE student_id=? ORDER BY lesson_date DESC, id DESC LIMIT 5",
                        (s["id"],))["tags"].dropna().str.split(",").explode().str.strip()
    recent_tags = recent_tags[recent_tags != ""].value_counts()
    if not recent_tags.empty:
        st.warning("🧩 **최근 5회 수업에서 어려워한 부분:** " +
                   " · ".join(f"{t} ({n}회)" for t, n in recent_tags.head(3).items()))

    st.subheader("📝 오늘 수업 기록")
    c1, c2 = st.columns(2)
    lesson_date = c1.date_input("수업 날짜", value=date.today(), key="prog_date")
    cur = s["current_book"] or BOOKS[0]
    book = c2.selectbox("교재", BOOKS, index=BOOKS.index(cur) if cur in BOOKS else len(BOOKS) - 1,
                        key=f"prog_book_{s['id']}")
    if book == "기타(직접 입력)":
        book = st.text_input("교재 이름", value=cur if cur not in BOOKS else "", key=f"prog_book_etc_{s['id']}")
    c3, c4 = st.columns(2)
    piece = c3.text_input("곡 / 번호", placeholder="예: 12번, 작은별 변주곡", key="prog_piece")
    measures = c4.text_input("진행 마디", placeholder="예: 1~16마디", key="prog_meas")
    status = st.radio("상태", PROGRESS_STATUS, horizontal=True, key="prog_status")
    comment = st.text_area("선생님 코멘트", placeholder="잘한 점, 다음 시간까지 연습할 부분", key="prog_comment")

    st.markdown("**📊 수업 평가** (1 = 많이 부족 · 3 = 보통 · 5 = 아주 잘함)")
    ecols = st.columns(4)
    scores = {k: ecols[i].slider(label, 1, 5, 3, key=f"eval_{k}") for i, (k, label) in enumerate(EVAL_ITEMS.items())}
    tags = st.multiselect("🧩 오늘 어려워한 부분", DIFFICULTY_TAGS, key="eval_tags")
    with_heart = st.checkbox("❤️ 하트 1개도 함께 주기", key="prog_heart")

    if st.button("기록 저장", type="primary"):
        if not piece.strip():
            st.error("곡 / 번호를 입력해 주세요.")
        else:
            pid = run("""INSERT INTO progress(student_id, lesson_date, book, piece, measures, status, comment, created_at)
                         VALUES(?,?,?,?,?,?,?,?)""",
                      (s["id"], lesson_date.isoformat(), book, piece.strip(), measures.strip(), status,
                       comment.strip(), now_str()))
            run("""INSERT INTO lesson_evals(progress_id, student_id, lesson_date, piece, rhythm, accuracy, posture,
                                            expression, tags, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (pid, s["id"], lesson_date.isoformat(), piece.strip(), scores["rhythm"], scores["accuracy"],
                 scores["posture"], scores["expression"], ",".join(tags), now_str()))
            run("UPDATE students SET current_book=? WHERE id=?", (book, s["id"]))
            if with_heart:
                give_heart(s["id"], 1, f"🎼 진도: {piece.strip()} {status}")
            st.success("저장했어요!" + (" ❤️ 하트도 1개 줬어요." if with_heart else ""))
            if status == PROGRESS_STATUS[2]:
                st.balloons()

    st.subheader("📚 진도 기록")
    hist = to_df("""SELECT p.lesson_date AS 날짜, p.book AS 교재, p.piece AS 곡, p.measures AS 마디,
                           p.status AS 상태, p.comment AS 코멘트,
                           CASE WHEN EXISTS(SELECT 1 FROM comment_reads r JOIN users u ON u.userid=r.userid
                                            WHERE r.progress_id=p.id AND u.role='parent')
                                THEN '✅' ELSE '' END AS 학부모확인
                    FROM progress p WHERE p.student_id=? ORDER BY p.lesson_date DESC, p.id DESC""", (s["id"],))
    st.dataframe(hist, hide_index=True, use_container_width=True)


# ─────────────────────────────────────────────
# 페이지: 결제 관리
# ─────────────────────────────────────────────
def page_payment():
    st.title("💳 결제 관리")
    today = date.today()
    ym = today.strftime("%Y-%m")
    studs = active_students()
    if not studs:
        st.info("등록된 학생이 없어요.")
        return

    rows = []
    for s in studs:
        stt, info = payment_status(s, today)
        rows.append({"이름": s["name"], "결제일": f"매월 {s['pay_day']}일", "수강료": f"{s['fee']:,}원",
                     "상태": stt, "비고": info})
    status_df = pd.DataFrame(rows)
    paid_sum = fetch("SELECT COALESCE(SUM(amount),0) t FROM payments WHERE pay_month=?", (ym,))[0]["t"]
    expected = sum(s["fee"] for s in studs)

    c1, c2, c3 = st.columns(3)
    c1.metric(f"{today.month}월 결제 완료", f"{(status_df['상태'] == '✅ 완료').sum()} / {len(studs)}명")
    c2.metric("연체 · 임박", f"{status_df['상태'].str.startswith(('🔴', '🟠')).sum()}명")
    c3.metric("수납액 / 예정액", f"{paid_sum:,} / {expected:,}원")

    st.subheader(f"📅 {today.month}월 결제 현황")
    order = {"🔴": 0, "🟠": 1, "⚪": 2, "✅": 3}
    status_df = status_df.sort_values("상태", key=lambda c: c.str[0].map(order))
    st.dataframe(status_df, hide_index=True, use_container_width=True)

    st.subheader("💰 결제 처리")
    unpaid = [s for s in studs if not payment_status(s, today)[0].startswith("✅")]
    if not unpaid:
        st.success("이번 달은 모두 결제 완료! 🎉")
    else:
        c1, c2, c3 = st.columns(3)
        s = c1.selectbox("학생", unpaid, format_func=student_label, key="pay_sel")
        amount = c2.number_input("금액(원)", 0, 1_000_000, value=int(s["fee"]), step=10000, key=f"pay_amt_{s['id']}")
        method = c3.selectbox("결제 수단", PAY_METHODS, key="pay_method")
        if st.button("결제 완료 처리", type="primary"):
            run("INSERT INTO payments(student_id, pay_month, amount, method, paid_at) VALUES(?,?,?,?,?)",
                (s["id"], ym, amount, method, now_str()))
            st.success(f"{s['name']} 학생 {today.month}월 수강료 {amount:,}원 결제 완료")
            st.rerun()

    st.subheader("🧾 결제 이력")
    months = [r["pay_month"] for r in fetch("SELECT DISTINCT pay_month FROM payments ORDER BY pay_month DESC")]
    if months:
        m = st.selectbox("월 선택", months)
        st.dataframe(to_df("""SELECT s.name AS 이름, p.amount AS 금액, p.method AS 수단, p.paid_at AS 결제일시
                              FROM payments p JOIN students s ON s.id=p.student_id
                              WHERE p.pay_month=? ORDER BY p.paid_at DESC""", (m,)),
                     hide_index=True, use_container_width=True)
    else:
        st.write("아직 결제 이력이 없어요.")


# ─────────────────────────────────────────────
# 페이지: 하트 스티커
# ─────────────────────────────────────────────
def heart_row(n, per_row=10):
    """보유 하트를 스티커판처럼 표시 (빈칸은 🤍)"""
    goal = max(10, ((n // per_row) + 1) * per_row)
    icons = ["❤️"] * n + ["🤍"] * (goal - n)
    return "<br>".join(" ".join(icons[i:i + per_row]) for i in range(0, goal, per_row))


def page_heart():
    st.title("❤️ 하트 스티커")
    tab_give, tab_board, tab_reward, tab_log = st.tabs(["🎁 하트 주기", "📋 하트판", "🛍️ 보상 교환", "🗂️ 기록"])

    with tab_give:
        s = select_student(key="heart_sel")
        if s:
            st.markdown(f"#### {s['name']} — 지금 ❤️ **{heart_balance(s['id'])}개**")
            st.caption("잘한 이유를 누르면 하트 1개가 바로 붙어요.")
            cols = st.columns(3)
            for i, reason in enumerate(HEART_REASONS):
                if cols[i % 3].button(reason, key=f"hr_{i}", use_container_width=True):
                    give_heart(s["id"], 1, reason)
                    st.toast(f"{s['name']}에게 ❤️ +1 ({reason})")
                    st.rerun()
            with st.expander("직접 입력해서 주기"):
                c1, c2 = st.columns([1, 3])
                n = c1.number_input("개수", 1, 10, 1, key="heart_n")
                r = c2.text_input("이유", placeholder="예: 연주회 무대 멋지게 마무리", key="heart_r")
                if st.button("하트 주기", type="primary"):
                    give_heart(s["id"], int(n), r.strip() or "칭찬")
                    st.toast(f"{s['name']}에게 ❤️ +{n}")
                    st.rerun()

    with tab_board:
        ym = date.today().strftime("%Y-%m")
        board = fetch("""SELECT s.id, s.name,
                                COALESCE(SUM(h.amount),0) AS bal,
                                COALESCE(SUM(CASE WHEN h.amount>0 AND h.created_at LIKE ? THEN h.amount END),0) AS mon
                         FROM students s LEFT JOIN hearts h ON h.student_id=s.id
                         WHERE s.active=1 GROUP BY s.id ORDER BY bal DESC""", (ym + "%",))
        if not board:
            st.info("등록된 학생이 없어요.")
        next_goal = REWARDS[0][1]
        for r in board:
            c1, c2 = st.columns([1, 3])
            c1.markdown(f"**{r['name']}**  \n보유 ❤️ {r['bal']} · 이번 달 +{r['mon']}")
            c2.markdown(f"<div style='font-size:1.3rem;line-height:1.6'>{heart_row(r['bal'])}</div>",
                        unsafe_allow_html=True)
            goal = next((c for _, c in REWARDS if c > r["bal"]), None)
            if goal:
                c2.progress(min(r["bal"] / goal, 1.0), text=f"다음 보상까지 {goal - r['bal']}개")
            else:
                c2.progress(1.0, text="모든 보상 교환 가능! 🎉")
            st.divider()

    with tab_reward:
        st.caption(" · ".join(f"{name} = ❤️ {cost}" for name, cost in REWARDS))
        s = select_student(key="reward_sel")
        if s:
            bal = heart_balance(s["id"])
            st.markdown(f"#### {s['name']} — 보유 ❤️ **{bal}개**")
            reward = st.radio("보상 선택", REWARDS, format_func=lambda x: f"{x[0]} (❤️ {x[1]})", horizontal=True)
            if st.button("교환하기", type="primary"):
                if bal < reward[1]:
                    st.error(f"하트가 {reward[1] - bal}개 부족해요.")
                else:
                    give_heart(s["id"], -reward[1], f"보상 교환: {reward[0]}")
                    st.success(f"{s['name']} 학생이 {reward[0]}을(를) 받았어요! 🎉")
                    st.balloons()

    with tab_log:
        st.dataframe(to_df("""SELECT h.created_at AS 일시, s.name AS 이름, h.amount AS 개수,
                                     h.reason AS 이유, h.given_by AS 준사람
                              FROM hearts h JOIN students s ON s.id=h.student_id
                              ORDER BY h.id DESC LIMIT 200"""),
                     hide_index=True, use_container_width=True)


# ─────────────────────────────────────────────
# 페이지: 학습 이력 (성장 대시보드)
# ─────────────────────────────────────────────
def piece_durations(prog):
    """곡별 완성 소요: 처음 배운 날 → 처음 '완성'한 날까지 걸린 기간과 수업 횟수"""
    rows = []
    for piece, g in prog.groupby("piece", sort=False):
        start = g["lesson_date"].min()
        done = g.loc[g["status"] == PROGRESS_STATUS[2], "lesson_date"]
        end = done.min() if not done.empty else None
        upto = g if end is None else g[g["lesson_date"] <= end]
        rows.append({
            "곡": piece, "시작일": start, "완성일": end or "-",
            "걸린 기간(일)": (date.fromisoformat(end) - date.fromisoformat(start)).days if end else None,
            "수업 횟수": len(upto),
            "상태": "⭐ 완성" if end else "🎵 진행 중",
        })
    return pd.DataFrame(rows)


def avg_score(df):
    return df[list(EVAL_ITEMS)].mean(axis=1).mean()


def attendance_rate(s, days=56):
    """최근 days일 동안 수업 예정일 대비 출석 비율(%)"""
    today = date.today()
    lesson_days = (s["lesson_days"] or "").split(",")
    scheduled = sum(1 for i in range(1, days + 1) if WEEKDAYS[(today - timedelta(days=i)).weekday()] in lesson_days)
    attended = fetch("SELECT COUNT(*) c FROM attendance WHERE student_id=? AND check_date>=? AND check_date<?",
                     (s["id"], (today - timedelta(days=days)).isoformat(), today.isoformat()))[0]["c"]
    return round(attended / scheduled * 100) if scheduled else None


def eval_near(sid, piece, d):
    """그 곡의 d 날짜 무렵 수업 평가 평균"""
    r = fetch("""SELECT (rhythm + accuracy + posture + expression) / 4.0 AS a FROM lesson_evals
                 WHERE student_id=? AND piece=? AND lesson_date<=? ORDER BY lesson_date DESC LIMIT 1""", (sid, piece, d))
    return r[0]["a"] if r else None


def show_video(col, v, label):
    col.markdown(f"**{label}** · {v['recorded_date']}")
    path = os.path.join(VIDEO_DIR, v["file_path"]) if v["file_path"] else None
    if path and os.path.exists(path):
        col.video(path)
    elif v["youtube_url"]:
        col.video(v["youtube_url"])
    else:
        col.write("(영상 파일 없음)")
    if v["comment"]:
        col.caption(f"💬 {v['comment']}")
    if st.session_state.get("role") == "teacher" and col.button("🗑️ 삭제", key=f"vdel_{v['id']}_{label}"):
        if path and os.path.exists(path):
            os.remove(path)
        run("DELETE FROM videos WHERE id=?", (v["id"],))
        st.rerun()


def video_upload_form(sid):
    """선생님: 수업 중 찍은 연주 영상 올리기 (파일 또는 유튜브 링크)"""
    with st.expander("⬆️ 연주 영상 올리기", expanded=False):
        opts = student_pieces(sid) + ["✏️ 직접 입력"]
        c1, c2 = st.columns(2)
        piece = c1.selectbox("곡", opts, key=f"v_piece_{sid}")
        if piece == "✏️ 직접 입력":
            piece = c1.text_input("곡 이름", key=f"v_piece_etc_{sid}").strip()
        vdate = c2.date_input("촬영일", value=date.today(), max_value=date.today(), key=f"v_date_{sid}")
        how = st.radio("방식", ["📁 영상 파일", "🔗 유튜브 링크"], horizontal=True, key=f"v_how_{sid}")
        up, url = None, ""
        if how == "📁 영상 파일":
            up = st.file_uploader("영상 파일 (mp4 · mov · webm)", type=["mp4", "mov", "m4v", "webm"], key=f"v_file_{sid}")
            st.caption("휴대폰 영상은 용량이 커요. 기본 업로드 한도는 200MB이고, 넘으면 유튜브 '일부 공개' 링크를 쓰세요.")
        else:
            url = st.text_input("유튜브 링크", placeholder="https://youtu.be/...", key=f"v_url_{sid}").strip()
        comment = st.text_input("선생님 한마디", placeholder="예: 왼손 반주가 훨씬 안정됐어요!", key=f"v_cmt_{sid}")
        if st.button("영상 저장", type="primary", key=f"v_save_{sid}"):
            if not piece:
                st.error("곡을 선택하거나 입력해 주세요.")
            elif not up and not url.startswith("http"):
                st.error("영상 파일을 올리거나 링크를 입력해 주세요.")
            else:
                rel = None
                if up:
                    folder = os.path.join(VIDEO_DIR, str(sid))
                    os.makedirs(folder, exist_ok=True)
                    rel = f"{sid}/{datetime.now():%Y%m%d_%H%M%S}{os.path.splitext(up.name)[1].lower()}"
                    with open(os.path.join(VIDEO_DIR, rel), "wb") as f:
                        f.write(up.getvalue())
                run("""INSERT INTO videos(student_id, piece, recorded_date, file_path, youtube_url, comment,
                                          uploaded_by, created_at) VALUES(?,?,?,?,?,?,?,?)""",
                    (sid, piece, vdate.isoformat(), rel, url or None, comment.strip(), st.session_state.userid, now_str()))
                st.success("영상을 올렸어요! 학부모 화면의 '🎬 성장 영상'에 바로 보여요.")


def render_videos(s):
    sid = s["id"]
    if st.session_state.get("role") == "teacher":
        video_upload_form(sid)
    vids = fetch("SELECT * FROM videos WHERE student_id=? ORDER BY recorded_date, id", (sid,))
    if not vids:
        st.info("아직 연주 영상이 없어요. 선생님이 수업 중 연주를 찍어 올리면 여기에 모여요.")
        return
    view = st.radio("보기", ["🎵 곡별 전후 비교", "🗓️ 타임라인"], horizontal=True, key=f"v_view_{sid}")
    if view == "🗓️ 타임라인":
        for v in reversed(vids):
            c1, c2 = st.columns([3, 2])
            show_video(c1, v, f"🎵 {v['piece']}")
            c2.caption(f"올린 날 {v['created_at'][:10]}")
            st.divider()
        return

    by_piece = {}
    for v in vids:
        by_piece.setdefault(v["piece"], []).append(v)
    for piece, lst in sorted(by_piece.items(), key=lambda kv: kv[1][-1]["recorded_date"], reverse=True):
        st.markdown(f"#### 🎵 {piece}")
        first, last = lst[0], lst[-1]
        if len(lst) == 1:
            show_video(st, first, "첫 영상")
            st.caption("같은 곡 영상을 한 번 더 올리면 처음과 지금을 나란히 비교할 수 있어요.")
        else:
            c1, c2 = st.columns(2)
            show_video(c1, first, "처음")
            show_video(c2, last, "지금")
            days = (date.fromisoformat(last["recorded_date"]) - date.fromisoformat(first["recorded_date"])).days
            lessons = fetch("""SELECT COUNT(*) n FROM progress WHERE student_id=? AND piece=?
                               AND lesson_date BETWEEN ? AND ?""",
                            (sid, piece, first["recorded_date"], last["recorded_date"]))[0]["n"]
            a, b = eval_near(sid, piece, first["recorded_date"]), eval_near(sid, piece, last["recorded_date"])
            change = f" · 수업 평가 {a:.1f} → {b:.1f}점" if a and b else ""
            st.info(f"📈 **{days}일** 동안 수업 **{lessons}회**{change}")
        st.divider()


def render_growth(s):
    """학생 한 명의 학습 이력 대시보드 (선생님·학부모·학생 공용)"""
    sid = s["id"]
    evals = to_df("""SELECT lesson_date, piece, rhythm, accuracy, posture, expression, tags
                     FROM lesson_evals WHERE student_id=? ORDER BY lesson_date, id""", (sid,))
    prog = to_df("SELECT lesson_date, piece, status FROM progress WHERE student_id=? ORDER BY lesson_date, id", (sid,))
    pieces = piece_durations(prog)

    # ── 상단 요약
    c1, c2, c3, c4 = st.columns(4)
    rate = attendance_rate(s)
    c1.metric("출석률 (최근 8주)", f"{rate}%" if rate is not None else "-")
    if len(evals) >= 2:
        first, recent = avg_score(evals.head(3)), avg_score(evals.tail(3))
        c2.metric("평가 평균 (최근 3회)", f"{recent:.1f}점", f"{recent - first:+.1f} (처음 3회 대비)")
    else:
        c2.metric("평가 평균", "-")
    done = pieces[pieces["상태"] == "⭐ 완성"] if not pieces.empty else pieces
    c3.metric("완성한 곡", f"⭐ {len(done)}곡")
    c4.metric("곡당 평균 완성 기간", f"{done['걸린 기간(일)'].mean():.0f}일" if not done.empty else "-")

    t0, t2, t3, t4 = st.tabs(["🎬 성장 영상", "📊 평가 점수", "🧩 어려운 부분", "⭐ 곡별 완성"])

    with t0:   # 🎬 선생님이 찍은 연주 영상
        render_videos(s)

    with t2:   # 수업 평가 점수
        if evals.empty:
            st.info("아직 수업 평가가 없어요. 선생님이 **🎼 진도 관리**에서 점수를 매기면 쌓여요.")
        else:
            chart = evals.groupby("lesson_date")[list(EVAL_ITEMS)].mean().rename(columns=EVAL_ITEMS)
            st.write("**평가 항목별 점수 변화 (최근 3회 이동평균)**")
            st.line_chart(chart.rolling(3, min_periods=1).mean(), y_label="점수(1~5)")
            comp = pd.DataFrame({
                "항목": list(EVAL_ITEMS.values()),
                "처음 3회": [evals.head(3)[k].mean().round(1) for k in EVAL_ITEMS],
                "최근 3회": [evals.tail(3)[k].mean().round(1) for k in EVAL_ITEMS],
            })
            comp["변화"] = (comp["최근 3회"] - comp["처음 3회"]).map(lambda x: f"{x:+.1f}")
            st.dataframe(comp, hide_index=True, use_container_width=True)

    with t3:   # 어려움 유형
        tags = evals["tags"].dropna().str.split(",").explode().str.strip() if not evals.empty else pd.Series(dtype=str)
        tags = tags[tags != ""]
        if tags.empty:
            st.info("아직 기록된 어려움 유형이 없어요.")
        else:
            cnt = tags.value_counts()
            st.write("**자주 막히는 부분 TOP 3:** " + " · ".join(f"{t} ({n}회)" for t, n in cnt.head(3).items()))
            recent = evals.tail(5)["tags"].dropna().str.split(",").explode().str.strip()
            recent = recent[recent != ""].value_counts()
            st.bar_chart(pd.DataFrame({"전체": cnt, "최근 5회 수업": recent}).fillna(0))
            st.caption("전체에서는 많았는데 최근 5회에서 줄었다면, 그 부분이 좋아지고 있다는 뜻이에요.")

    with t4:   # 곡별 완성 소요
        if pieces.empty:
            st.info("아직 진도 기록이 없어요.")
        else:
            st.dataframe(pieces.iloc[::-1], hide_index=True, use_container_width=True)
            st.caption("걸린 기간 = 처음 배운 날 → 처음 '완성'한 날")


def corr_text(r):
    if pd.isna(r):
        return "데이터 부족"
    strength = "강한" if abs(r) >= 0.5 else "보통" if abs(r) >= 0.3 else "약한" if abs(r) >= 0.1 else "거의 없는"
    return f"r = {r:.2f} ({strength} {'양' if r > 0 else '음'}의 상관)"


def render_academy_analysis():
    """학원 전체 학습 분석 (Learning Analytics) - 수업·출석·하트 데이터만 사용"""
    rows = []
    for s in active_students():
        sid = s["id"]
        prog = to_df("SELECT lesson_date, piece, status FROM progress WHERE student_id=? ORDER BY lesson_date, id", (sid,))
        ev = to_df("SELECT rhythm, accuracy, posture, expression FROM lesson_evals WHERE student_id=? ORDER BY lesson_date, id",
                   (sid,))
        pcs = piece_durations(prog)
        done = pcs[pcs["상태"] == "⭐ 완성"] if not pcs.empty else pcs
        rows.append({
            "이름": s["name"],
            "출석률(%)": attendance_rate(s),
            "곡당 수업 수": round(done["수업 횟수"].mean(), 1) if not done.empty else None,
            "평가 평균": round(avg_score(ev), 2) if not ev.empty else None,
            "평가 향상": round(avg_score(ev.tail(3)) - avg_score(ev.head(3)), 2) if len(ev) >= 6 else None,
            "받은 하트": fetch("SELECT COALESCE(SUM(amount),0) t FROM hearts WHERE student_id=? AND amount>0",
                           (sid,))[0]["t"],
        })
    df = pd.DataFrame(rows)
    if df.empty:
        st.info("학생 데이터가 없어요.")
        return
    st.caption("학생별 출석·진도·평가·하트 데이터를 모아, 학습 요인 사이의 관계를 살펴봐요. (출석률은 최근 8주 기준)")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**① 꾸준히 출석하면 곡을 더 빨리 완성할까?**")
        st.scatter_chart(df, x="출석률(%)", y="곡당 수업 수")
        st.caption(corr_text(df["출석률(%)"].corr(df["곡당 수업 수"])))
    with c2:
        st.markdown("**② 꾸준히 출석한 학생이 실력도 더 늘었을까?**")
        st.scatter_chart(df, x="출석률(%)", y="평가 향상")
        st.caption(corr_text(df["출석률(%)"].corr(df["평가 향상"])) + " · 평가 향상 = 최근 3회 − 처음 3회")
    c3, c4 = st.columns(2)
    with c3:
        st.markdown("**③ 하트를 많이 받은 학생은 출석도 잘할까?**")
        st.scatter_chart(df, x="받은 하트", y="출석률(%)")
        st.caption(corr_text(df["받은 하트"].corr(df["출석률(%)"])))
    with c4:
        st.markdown("**④ 학원 전체 자주 막히는 부분 (최근 8주)**")
        tags = to_df("SELECT tags FROM lesson_evals WHERE lesson_date>=?",
                     ((date.today() - timedelta(days=55)).isoformat(),))["tags"]
        tags = tags.dropna().str.split(",").explode().str.strip()
        tags = tags[tags != ""]
        if not tags.empty:
            st.bar_chart(tags.value_counts())
    st.caption("※ 상관관계는 함께 움직이는 경향일 뿐, 원인과 결과(인과)를 뜻하지는 않아요.")
    st.dataframe(df, hide_index=True, use_container_width=True)


def page_growth():
    st.title("📈 학습 이력")
    tab_one, tab_all = st.tabs(["👤 학생별 성장", "🏫 학원 전체 분석"])
    with tab_one:
        s = select_student(key="growth_sel")
        if s:
            render_growth(s)
    with tab_all:
        render_academy_analysis()


# ─────────────────────────────────────────────
# 페이지: 앱 사용 로그 (learninghistory · 선생님 전용)
# ─────────────────────────────────────────────
def page_usagelog():
    uid = st.session_state.userid
    st.title("🖥️ 앱 사용 로그")
    st.caption("메뉴를 클릭할 때 learninghistory에 기록되고, 다른 메뉴로 이동할 때까지 머문 시간(초)이 저장돼요.")
    tab1, tab2, tab3 = st.tabs(["👥 사용자별 이용 현황", "💬 코멘트 확인율", "🔁 내 메뉴 순서"])

    with tab1:
        roles = st.multiselect("역할", list(ROLES), default=list(ROLES), format_func=ROLES.get)
        d = to_df("""SELECT l.userid, COALESCE(u.role,'?') AS role, l.menu_id,
                            SUM(l.wating_time) AS total, COUNT(*) AS cnt, MAX(l.create_at) AS last
                     FROM learninghistory l LEFT JOIN users u ON u.userid = l.userid
                     GROUP BY l.userid, l.menu_id""")
        d = d[d["role"].isin(roles)]
        if d.empty:
            st.info("기록이 없어요.")
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("사용자 수", f"{d['userid'].nunique()}명")
            c2.metric("총 체류 시간", fmt_sec(d["total"].sum()))
            c3.metric("총 메뉴 클릭", f"{d['cnt'].sum()}회")
            d["메뉴"] = d["menu_id"].map(lambda m: MENUS.get(m, m))
            st.write("**메뉴별 누적 체류 시간(분)**")
            st.bar_chart((d.groupby("메뉴")["total"].sum() / 60).round(1).sort_values(ascending=False))
            per_user = d.sort_values("total", ascending=False).groupby("userid").agg(
                역할=("role", lambda x: ROLES.get(x.iloc[0], x.iloc[0])),
                총체류=("total", "sum"), 클릭=("cnt", "sum"), 마지막사용=("last", "max"),
                가장많이쓴메뉴=("메뉴", "first")).sort_values("총체류", ascending=False)
            per_user["총체류"] = per_user["총체류"].map(fmt_sec)
            st.dataframe(per_user, use_container_width=True)
            with st.expander("최근 원본 기록 50건 (learninghistory)"):
                st.dataframe(to_df("SELECT * FROM learninghistory ORDER BY id DESC LIMIT 50"),
                             hide_index=True, use_container_width=True)

    with tab2:
        st.caption("학부모가 선생님 코멘트(진도 기록)를 앱에서 실제로 열어 봤는지 (comment_reads)")
        cr = to_df("""SELECT s.name AS 학생, COUNT(p.id) AS 코멘트수,
                             SUM(CASE WHEN EXISTS(SELECT 1 FROM comment_reads r JOIN users u ON u.userid=r.userid
                                                  WHERE r.progress_id=p.id AND u.role='parent') THEN 1 ELSE 0 END) AS 확인수,
                             (SELECT MAX(r.read_at) FROM comment_reads r JOIN users u ON u.userid=r.userid
                              WHERE u.role='parent' AND u.student_id=s.id) AS 마지막확인
                      FROM students s LEFT JOIN progress p ON p.student_id=s.id AND COALESCE(p.comment,'')<>''
                      WHERE s.active=1 GROUP BY s.id""")
        if cr.empty or cr["코멘트수"].sum() == 0:
            st.info("코멘트 기록이 없어요.")
        else:
            cr["확인율(%)"] = (cr["확인수"] / cr["코멘트수"].replace(0, pd.NA) * 100).round(0)
            st.metric("전체 확인율", f"{cr['확인수'].sum() / cr['코멘트수'].sum() * 100:.0f}%")
            st.dataframe(cr.sort_values("확인율(%)"), hide_index=True, use_container_width=True)
            st.caption("확인율이 낮은 가정에는 문자나 상담으로 직접 전달해 보세요.")

    with tab3:
        st.write("  →  ".join(MENUS[m] for m in get_menu_order(uid, st.session_state.role)))
        st.caption("다음 로그인 때 메뉴 순서 · 기준: ① 누적 체류 시간이 긴 순 ② 같으면 클릭 수가 많은 순")


# ─────────────────────────────────────────────
# 페이지: DB 관리 (SQLite 직접 들여다보기 · SQL 실습 · 백업/복원)
# ─────────────────────────────────────────────
READ_PREFIXES = ("select", "pragma", "with", "explain")


def page_dbadmin():
    st.title("🗄️ DB 관리")
    size_kb = os.path.getsize(DB_PATH) / 1024 if os.path.exists(DB_PATH) else 0
    st.caption(f"📁 DB 파일 위치: `{DB_PATH}`  ·  크기 {size_kb:.1f} KB")

    tables = [r["name"] for r in fetch(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    tab_view, tab_sql, tab_backup = st.tabs(["📋 테이블 보기", "⌨️ SQL 실행", "💾 백업 · 복원"])

    # ① 테이블 보기
    with tab_view:
        counts = [{"테이블": t, "행 수": fetch(f"SELECT COUNT(*) c FROM {t}")[0]["c"]} for t in tables]
        st.dataframe(pd.DataFrame(counts), hide_index=True, use_container_width=True)
        t = st.selectbox("테이블 선택", tables, key="db_table")
        if t:
            with st.expander("🔧 테이블 구조 (PRAGMA table_info)"):
                st.dataframe(to_df(f"PRAGMA table_info({t})")[["name", "type", "notnull", "dflt_value", "pk"]],
                             hide_index=True, use_container_width=True)
                st.code(fetch("SELECT sql FROM sqlite_master WHERE name=?", (t,))[0]["sql"], language="sql")
            limit = st.slider("최근 몇 행까지 볼까요?", 10, 500, 50, step=10)
            st.dataframe(to_df(f"SELECT * FROM {t} ORDER BY rowid DESC LIMIT ?", (limit,)),
                         hide_index=True, use_container_width=True)

    # ② SQL 실행
    with tab_sql:
        st.caption("예시를 골라 실행해 보거나 직접 SQL을 작성해 보세요.")
        examples = {
            "직접 작성": "",
            "회원 목록": "SELECT userid, created_at FROM users ORDER BY created_at;",
            "메뉴별 누적 체류시간": "SELECT userid, menu_id, SUM(wating_time) AS total_sec, COUNT(*) AS clicks\n"
                            "FROM learninghistory\nGROUP BY userid, menu_id\nORDER BY userid, total_sec DESC;",
            "학생별 하트 순위": "SELECT s.name, SUM(h.amount) AS hearts\nFROM students s JOIN hearts h ON h.student_id = s.id\n"
                          "GROUP BY s.id\nORDER BY hearts DESC;",
            "평가 항목별 평균": "SELECT s.name, ROUND(AVG(e.rhythm),1) AS 리듬, ROUND(AVG(e.accuracy),1) AS 정확도,\n"
                          "       ROUND(AVG(e.posture),1) AS 자세, ROUND(AVG(e.expression),1) AS 표현\n"
                          "FROM lesson_evals e JOIN students s ON s.id = e.student_id\nGROUP BY s.id;",
            "학부모 코멘트 확인 기록": "SELECT r.userid, s.name, p.lesson_date, p.comment, r.read_at\n"
                              "FROM comment_reads r JOIN progress p ON p.id = r.progress_id\n"
                              "JOIN students s ON s.id = p.student_id\nORDER BY r.read_at DESC;",
            "이번 달 출석 횟수": "SELECT s.name, COUNT(*) AS cnt\nFROM attendance a JOIN students s ON s.id = a.student_id\n"
                           "WHERE a.check_date LIKE strftime('%Y-%m', 'now', 'localtime') || '%'\nGROUP BY s.id;",
        }
        ex = st.selectbox("예시 쿼리", list(examples), key="db_ex")
        sql = st.text_area("SQL", value=examples[ex], height=150, key=f"db_sql_{ex}")
        allow_write = st.checkbox("⚠️ INSERT / UPDATE / DELETE 허용 (데이터가 실제로 바뀌어요)", key="db_write")
        if st.button("▶ 실행", type="primary"):
            q = sql.strip().rstrip(";")
            if not q:
                st.warning("SQL을 입력해 주세요.")
            elif q.lower().startswith(READ_PREFIXES):
                try:
                    res = to_df(q)
                    st.success(f"{len(res)}행 조회")
                    st.dataframe(res, hide_index=True, use_container_width=True)
                except Exception as e:
                    st.error(f"오류: {e}")
            elif not allow_write:
                st.error("조회(SELECT) 외의 쿼리는 위 체크박스를 켜야 실행돼요.")
            else:
                try:
                    conn = get_conn()
                    cur = conn.execute(q)
                    conn.commit()
                    st.success(f"실행 완료 · 영향받은 행: {cur.rowcount}")
                    conn.close()
                except Exception as e:
                    st.error(f"오류: {e}")

    # ③ 백업 · 복원
    with tab_backup:
        st.info("Streamlit Cloud는 재부팅하거나 코드를 다시 배포하면 DB 파일이 초기화돼요.\n\n"
                "**코드 수정 전에 백업 다운로드 → 재배포 후 복원 업로드** 순서로 데이터를 지킬 수 있어요.")
        with open(DB_PATH, "rb") as f:
            st.download_button("⬇️ DB 백업 다운로드", f.read(),
                               file_name=f"piano_academy_{datetime.now():%Y%m%d_%H%M}.db",
                               mime="application/x-sqlite3", use_container_width=True)
        st.divider()
        up = st.file_uploader("⬆️ 백업 파일로 복원 (.db)", type=["db", "sqlite", "sqlite3"])
        if up:
            data = up.getvalue()
            if not data.startswith(b"SQLite format 3\x00"):
                st.error("SQLite DB 파일이 아니에요.")
            else:
                sure = st.checkbox("지금 DB를 이 파일로 덮어쓰는 것에 동의합니다 (현재 데이터는 사라져요)")
                if st.button("복원하기", type="primary", disabled=not sure):
                    with open(DB_PATH, "wb") as f:
                        f.write(data)
                    init_db()   # 빠진 테이블이 있으면 생성
                    st.success("복원 완료! 다시 로그인해 주세요.")
                    for k in list(st.session_state.keys()):
                        del st.session_state[k]
                    st.rerun()


# ─────────────────────────────────────────────
# 학부모 · 학생 페이지 (연결된 자녀/본인 정보만 조회)
# ─────────────────────────────────────────────
def my_student():
    rows = fetch("SELECT * FROM students WHERE id=?", (st.session_state.get("student_id"),))
    if not rows:
        st.error("연결된 학생 정보가 없어요. 선생님께 문의해 주세요.")
        return None
    return rows[0]


def is_parent():
    return st.session_state.get("role") == "parent"


def page_my_home():
    s = my_student()
    if not s:
        return
    today = date.today()
    st.title(f"🏠 {s['name']} 학생 소식" if is_parent() else f"🏠 {s['name']}의 피아노 🎹")
    st.caption(f"수업: 매주 {s['lesson_days'] or '-'} {s['lesson_time'] or ''}  ·  현재 교재: {s['current_book'] or '-'}")

    # 🔔 알림함 (최근 3일 입장·하원 알림)
    notes = fetch("SELECT * FROM notifications WHERE student_id=? AND created_at>=? ORDER BY id DESC LIMIT 6",
                  (s["id"], (today - timedelta(days=2)).isoformat()))
    if notes:
        st.subheader("🔔 알림")
        for n in notes:
            icon = {"arrive": "🎹", "leave": "👋"}.get(n["kind"], "📢")
            new = " **NEW**" if is_parent() and not n["read_at"] else ""
            st.write(f"{icon} `{n['created_at'][5:16]}` {n['message'].split('] ', 1)[-1]}{new}")
        if is_parent():
            run("UPDATE notifications SET read_at=? WHERE student_id=? AND read_at IS NULL", (now_str(), s["id"]))
    vnew = fetch("SELECT piece, recorded_date FROM videos WHERE student_id=? AND created_at>=? ORDER BY id DESC",
                 (s["id"], (today - timedelta(days=7)).isoformat()))
    if vnew:
        st.success(f"🎬 새 연주 영상이 올라왔어요! ({vnew[0]['piece']}) → **📈 학습 이력 › 🎬 성장 영상**에서 확인하세요")

    att_cnt = fetch("SELECT COUNT(*) c FROM attendance WHERE student_id=? AND check_date LIKE ?",
                    (s["id"], today.strftime("%Y-%m") + "%"))[0]["c"]
    bal = heart_balance(s["id"])
    done = fetch("SELECT COUNT(*) c FROM progress WHERE student_id=? AND status=?",
                 (s["id"], PROGRESS_STATUS[2]))[0]["c"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"{today.month}월 출석", f"{att_cnt}회")
    c2.metric("모은 하트", f"❤️ {bal}개")
    c3.metric("완성한 곡", f"⭐ {done}곡")
    if is_parent():
        stt, info = payment_status(s, today)
        c4.metric(f"{today.month}월 수강료", stt, info, delta_color="off")
    else:
        c4.metric("현재 교재", s["current_book"] or "-")

    last = fetch("SELECT * FROM progress WHERE student_id=? ORDER BY lesson_date DESC, id DESC LIMIT 1", (s["id"],))
    if last:
        l = last[0]
        st.subheader("💬 선생님 한마디")
        st.info(f"**{l['lesson_date']}** · {l['book']} {l['piece']} {l['measures'] or ''} — {l['status']}\n\n"
                f"{l['comment'] or '오늘도 수고했어요!'}")
        mark_read([l["id"]])

    goal = next((c for _, c in REWARDS if c > bal), None)
    st.subheader("🎁 다음 보상까지")
    if goal:
        name = next(n for n, c in REWARDS if c == goal)
        st.progress(bal / goal, text=f"{name}까지 하트 {goal - bal}개 남았어요!")
    else:
        st.progress(1.0, text="모든 보상을 받을 수 있어요! 선생님께 말해 보세요 🎉")


def page_my_progress():
    s = my_student()
    if not s:
        return
    st.title("🎼 진도 기록")
    st.caption(f"현재 교재: {s['current_book'] or '-'}")
    d = to_df("""SELECT id, lesson_date AS 날짜, book AS 교재, piece AS 곡, measures AS 마디,
                        status AS 상태, comment AS 선생님코멘트
                 FROM progress WHERE student_id=? ORDER BY lesson_date DESC, id DESC""", (s["id"],))
    if d.empty:
        st.info("아직 진도 기록이 없어요.")
    else:
        mark_read(d.loc[d["선생님코멘트"].fillna("") != "", "id"].head(20).tolist())   # 화면에 보인 최근 코멘트
        st.dataframe(d.drop(columns="id"), hide_index=True, use_container_width=True)

def page_my_growth():
    s = my_student()
    if not s:
        return
    st.title(f"📈 {s['name']} 학습 이력" if is_parent() else "📈 나의 성장 기록")
    render_growth(s)


def page_my_heart():
    s = my_student()
    if not s:
        return
    bal = heart_balance(s["id"])
    st.title("❤️ 내 하트판" if not is_parent() else f"❤️ {s['name']} 하트판")
    st.markdown(f"<div style='font-size:2rem;line-height:1.5'>{heart_row(bal)}</div>", unsafe_allow_html=True)
    st.write(f"지금 하트 **{bal}개**")
    st.caption("보상: " + " · ".join(f"{n} = ❤️ {c}" for n, c in REWARDS))
    st.subheader("🗂️ 하트 받은 기록")
    st.dataframe(to_df("""SELECT created_at AS 일시, amount AS 개수, reason AS 이유
                          FROM hearts WHERE student_id=? ORDER BY id DESC""", (s["id"],)),
                 hide_index=True, use_container_width=True)


def page_my_attendance():
    s = my_student()
    if not s:
        return
    st.title("✅ 출석 기록")
    d = to_df("""SELECT check_date AS 날짜, check_time AS 도착시간
                 FROM attendance WHERE student_id=? ORDER BY check_date DESC""", (s["id"],))
    if d.empty:
        st.info("아직 출석 기록이 없어요.")
        return
    d["월"] = d["날짜"].str[:7]
    m = st.selectbox("월 선택", sorted(d["월"].unique(), reverse=True))
    sel = d[d["월"] == m].drop(columns="월")
    st.write(f"**{m} 출석 {len(sel)}회**")
    st.dataframe(sel, hide_index=True, use_container_width=True)


def page_my_payment():
    s = my_student()
    if not s:
        return
    today = date.today()
    st.title("💳 수강료 결제")
    stt, info = payment_status(s, today)
    c1, c2, c3 = st.columns(3)
    c1.metric("월 수강료", f"{s['fee']:,}원")
    c2.metric("결제일", f"매월 {s['pay_day']}일")
    c3.metric(f"{today.month}월 상태", stt, info, delta_color="off")
    st.caption("결제는 학원에서 해주시면 선생님이 확인 후 '완료'로 바뀌어요.")
    st.subheader("🧾 결제 이력")
    st.dataframe(to_df("""SELECT pay_month AS 대상월, amount AS 금액, method AS 수단, paid_at AS 결제일시
                          FROM payments WHERE student_id=? ORDER BY pay_month DESC""", (s["id"],)),
                 hide_index=True, use_container_width=True)


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────
PAGES = {
    "my_home": page_my_home,
    "my_progress": page_my_progress,
    "my_heart": page_my_heart,
    "my_attendance": page_my_attendance,
    "my_payment": page_my_payment,
    "dbadmin": page_dbadmin,
    "home": page_home,
    "attendance": page_attendance,
    "students": page_students,
    "progress": page_progress,
    "payment": page_payment,
    "heart": page_heart,
    "growth": page_growth,
    "usagelog": page_usagelog,
    "my_growth": page_my_growth,
}


def main():
    init_db()

    # 출석 키오스크: ?kiosk=비밀키 로 접속하면 로그인 없이 키패드 화면
    if "kiosk" in st.query_params:
        if st.query_params["kiosk"] == kiosk_key():
            page_kiosk()
        else:
            st.error("키오스크 주소가 올바르지 않아요. 선생님께 문의해 주세요.")
        return

    if "userid" not in st.session_state:
        page_login()
        return

    # 2. 사이드바 라디오 메뉴 (순서는 로그인할 때 정해진 menu_order)
    with st.sidebar:
        st.markdown(f"## 🎹 {ACADEMY_NAME}")
        role = st.session_state.get("role", "teacher")
        st.caption(f"{ROLES[role]} · {st.session_state.userid} 님")
        if role == "parent" and st.session_state.get("student_id"):
            unread = fetch("SELECT COUNT(*) c FROM notifications WHERE student_id=? AND read_at IS NULL",
                           (st.session_state.student_id,))[0]["c"]
            if unread:
                st.info(f"🔔 새 알림 {unread}개 → 🏠 한눈에 보기")
        menu = st.radio("메뉴", st.session_state.menu_order, format_func=lambda m: MENUS[m], key="menu_radio")
        st.caption("💡 메뉴 순서는 로그인할 때 많이 머문 순서로 바뀌어요.")
        st.divider()
        logout_clicked = st.button("🚪 로그아웃", use_container_width=True)

    if logout_clicked:
        logout()
        st.rerun()

    if menu not in ROLE_MENUS[role]:      # 권한 없는 메뉴 차단
        st.error("이 메뉴를 볼 권한이 없어요.")
        return
    track_menu(menu)   # 3. learninghistory 기록
    PAGES[menu]()


main()
