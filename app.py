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
import sqlite3
import time
from datetime import date, datetime, time as dtime

import pandas as pd
import streamlit as st

# ─────────────────────────────────────────────
# 기본 설정
# ─────────────────────────────────────────────
DB_PATH = "piano_academy.db"
ACADEMY_NAME = "해오름 피아노"

MENUS = {
    "home": "🏠 홈",
    "attendance": "✅ 출석 체크",
    "students": "👩‍🎓 학생 관리",
    "progress": "🎼 진도 관리",
    "payment": "💳 결제 관리",
    "heart": "❤️ 하트 스티커",
    "history": "📊 학습 이력",
}
DEFAULT_ORDER = list(MENUS.keys())

WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
GRADES = ["유치", "초1", "초2", "초3", "초4", "초5", "초6", "중1", "중2", "중3", "고1", "고2", "고3", "성인"]
BOOKS = ["바이엘 상", "바이엘 하", "체르니 100", "체르니 30", "체르니 40", "부르크뮐러",
         "소나티네", "소나타", "하농", "동요/가요", "기타(직접 입력)"]
PROGRESS_STATUS = ["🌱 시작", "🎵 연습 중", "⭐ 완성"]
HEART_REASONS = ["🏠 숙제 완료", "🔥 연습 열심히", "⭐ 곡 완성", "🧍 바른 자세", "🎼 악보 잘 읽기", "😊 수업 태도"]
REWARDS = [("🍬 간식 쿠폰", 10), ("✏️ 예쁜 문구", 20), ("🎁 깜짝 선물", 30)]
PAY_METHODS = ["카드", "계좌이체", "현금", "지역화폐"]

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
            created_at  TEXT NOT NULL
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
            check_time  TEXT NOT NULL,
            message     TEXT
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
        """
    )
    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
# 1. 사용자 등록 / 로그인
# ─────────────────────────────────────────────
def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()


def register_user(userid, password):
    if fetch("SELECT 1 FROM users WHERE userid=?", (userid,)):
        return False
    run("INSERT INTO users(userid, password, created_at) VALUES(?,?,?)",
        (userid, hash_pw(password), now_str()))
    return True


def check_login(userid, password):
    return bool(fetch("SELECT 1 FROM users WHERE userid=? AND password=?",
                      (userid, hash_pw(password))))


# ─────────────────────────────────────────────
# 3·4. learninghistory : 체류 시간 기록 & 메뉴 재정렬
# ─────────────────────────────────────────────
def get_menu_order(userid):
    """누적 체류시간(1순위) → 클릭 횟수(2순위) 순으로 정렬, 기록 없는 메뉴는 기본 순서로 뒤에"""
    rows = fetch(
        """SELECT menu_id, SUM(wating_time) AS total, COUNT(*) AS cnt
           FROM learninghistory WHERE userid=?
           GROUP BY menu_id ORDER BY total DESC, cnt DESC""",
        (userid,),
    )
    ordered = [r["menu_id"] for r in rows if r["menu_id"] in MENUS]
    return ordered + [m for m in DEFAULT_ORDER if m not in ordered]


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
                if check_login(uid.strip(), pw):
                    uid = uid.strip()
                    st.session_state.userid = uid
                    order = get_menu_order(uid)          # ← 4. 로그인 시 메뉴 재배치
                    st.session_state.menu_order = order
                    st.session_state.menu_radio = order[0]  # 가장 많이 머문 메뉴로 바로 진입
                    st.rerun()
                else:
                    st.error("아이디 또는 비밀번호가 맞지 않아요.")

        with tab_join:
            with st.form("join_form", clear_on_submit=True):
                new_id = st.text_input("아이디")
                new_pw = st.text_input("비밀번호 (4자 이상)", type="password")
                new_pw2 = st.text_input("비밀번호 확인", type="password")
                ok2 = st.form_submit_button("등록하기", use_container_width=True)
            if ok2:
                new_id = new_id.strip()
                if not new_id or len(new_pw) < 4:
                    st.error("아이디를 입력하고, 비밀번호는 4자 이상으로 해주세요.")
                elif new_pw != new_pw2:
                    st.error("비밀번호 확인이 일치하지 않아요.")
                elif register_user(new_id, new_pw):
                    st.success("등록 완료! 로그인 탭에서 로그인해 주세요.")
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
    att = {r["student_id"]: r["check_time"] for r in
           fetch("SELECT student_id, check_time FROM attendance WHERE check_date=?", (today.isoformat(),))}
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
            mark = f"✅ {att[s['id']]} 도착" if s["id"] in att else "⏳ 아직"
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
# 페이지: 출석 체크 (키오스크)
# ─────────────────────────────────────────────
def do_checkin(s):
    today = date.today().isoformat()
    t = datetime.now().strftime("%H:%M")
    if fetch("SELECT 1 FROM attendance WHERE student_id=? AND check_date=?", (s["id"], today)):
        st.session_state.kiosk_msg = ("info", f"{s['name']} 학생은 오늘 이미 출석했어요 😊", None, None)
        return
    msg = f"[{ACADEMY_NAME}] {s['name']} 학생이 {t}에 학원에 도착했습니다. 오늘도 즐겁게 연주할게요 🎹"
    send_sms(s["parent_phone"], msg)
    run("INSERT INTO attendance(student_id, check_date, check_time, message) VALUES(?,?,?,?)",
        (s["id"], today, t, msg))
    st.session_state.kiosk_msg = (
        "success", f"🎉 {s['name']} 학생, 반가워요!  지금까지 모은 하트 ❤️ {heart_balance(s['id'])}개",
        msg, s["parent_phone"])


def page_attendance():
    st.title("✅ 출석 체크")
    tab1, tab2 = st.tabs(["📱 출석 키오스크", "📋 출석부"])

    with tab1:
        st.caption("학원 입구 태블릿에 이 화면을 띄워 두면, 학생이 학부모 전화번호 뒷자리 4자리를 눌러 출석해요.")
        with st.form("kiosk", clear_on_submit=True):
            num = st.text_input("📞 전화번호 뒷자리 4자리", max_chars=4, placeholder="예: 5678")
            ok = st.form_submit_button("출석하기 🎹", use_container_width=True, type="primary")
        if ok:
            st.session_state.pop("kiosk_msg", None)
            st.session_state.pop("dup", None)
            if not (num.isdigit() and len(num) == 4):
                st.error("숫자 4자리를 입력해 주세요.")
            else:
                matches = fetch("SELECT * FROM students WHERE phone_last4=? AND active=1", (num,))
                if not matches:
                    st.error("등록된 번호가 없어요. 선생님께 말씀해 주세요.")
                elif len(matches) == 1:
                    do_checkin(matches[0])
                else:
                    st.session_state.dup = [m["id"] for m in matches]

        # 뒷자리가 같은 학생이 여러 명일 때 이름 선택
        if st.session_state.get("dup"):
            st.warning("같은 번호의 학생이 여러 명이에요. 내 이름을 눌러 주세요.")
            cands = [fetch("SELECT * FROM students WHERE id=?", (i,))[0] for i in st.session_state.dup]
            cols = st.columns(len(cands))
            for col, s in zip(cols, cands):
                if col.button(s["name"], key=f"dup_{s['id']}", use_container_width=True):
                    do_checkin(s)
                    st.session_state.pop("dup", None)
                    st.rerun()

        km = st.session_state.get("kiosk_msg")
        if km:
            kind, text, sms, phone = km
            (st.success if kind == "success" else st.info)(text)
            if sms:
                st.info(f"📩 **학부모 문자 (미리보기)** → {phone}\n\n{sms}")

    with tab2:
        d = st.date_input("날짜", value=date.today())
        day_df = to_df("""SELECT s.name AS 이름, s.grade AS 학년, a.check_time AS 도착시간
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
                            s.phone_last4 AS 출석번호, COALESCE(SUM(h.amount),0) AS 하트
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
    with_heart = st.checkbox("❤️ 하트 1개도 함께 주기", key="prog_heart")

    if st.button("기록 저장", type="primary"):
        if not piece.strip():
            st.error("곡 / 번호를 입력해 주세요.")
        else:
            run("""INSERT INTO progress(student_id, lesson_date, book, piece, measures, status, comment, created_at)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (s["id"], lesson_date.isoformat(), book, piece.strip(), measures.strip(), status,
                 comment.strip(), now_str()))
            run("UPDATE students SET current_book=? WHERE id=?", (book, s["id"]))
            if with_heart:
                give_heart(s["id"], 1, f"🎼 진도: {piece.strip()} {status}")
            st.success("저장했어요!" + (" ❤️ 하트도 1개 줬어요." if with_heart else ""))
            if status == PROGRESS_STATUS[2]:
                st.balloons()

    st.subheader("📚 진도 기록")
    hist = to_df("""SELECT lesson_date AS 날짜, book AS 교재, piece AS 곡, measures AS 마디,
                           status AS 상태, comment AS 코멘트
                    FROM progress WHERE student_id=? ORDER BY lesson_date DESC, id DESC""", (s["id"],))
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
# 페이지: 학습 이력 (learninghistory)
# ─────────────────────────────────────────────
def page_history():
    uid = st.session_state.userid
    st.title("📊 학습 이력")
    st.caption("메뉴를 클릭할 때마다 기록되고, 다른 메뉴로 이동할 때까지 머문 시간(초)이 저장돼요.")

    d = to_df("""SELECT menu_id, SUM(wating_time) AS total, COUNT(*) AS cnt
                 FROM learninghistory WHERE userid=? GROUP BY menu_id
                 ORDER BY total DESC, cnt DESC""", (uid,))
    if d.empty:
        st.info("아직 기록이 없어요.")
        return
    d["메뉴"] = d["menu_id"].map(MENUS)
    c1, c2 = st.columns(2)
    c1.metric("총 체류 시간", fmt_sec(d["total"].sum()))
    c2.metric("총 메뉴 클릭", f"{d['cnt'].sum()}회")

    st.subheader("메뉴별 누적 체류 시간(초)")
    st.bar_chart(d.set_index("메뉴")["total"])

    show = d[["메뉴", "total", "cnt"]].rename(columns={"total": "누적 체류(초)", "cnt": "클릭 수"})
    show["평균 체류"] = (d["total"] / d["cnt"]).round(1).astype(str) + "초"
    st.dataframe(show, hide_index=True, use_container_width=True)

    st.subheader("🔁 다음 로그인 때 메뉴 순서")
    st.write("  →  ".join(MENUS[m] for m in get_menu_order(uid)))
    st.caption("기준: ① 누적 체류 시간이 긴 순 ② 같으면 클릭 수가 많은 순")

    st.subheader("최근 기록 30건")
    st.dataframe(to_df("""SELECT create_at, menu_id, wating_time FROM learninghistory
                          WHERE userid=? ORDER BY id DESC LIMIT 30""", (uid,)),
                 hide_index=True, use_container_width=True)


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────
PAGES = {
    "home": page_home,
    "attendance": page_attendance,
    "students": page_students,
    "progress": page_progress,
    "payment": page_payment,
    "heart": page_heart,
    "history": page_history,
}


def main():
    init_db()
    if "userid" not in st.session_state:
        page_login()
        return

    # 2. 사이드바 라디오 메뉴 (순서는 로그인할 때 정해진 menu_order)
    with st.sidebar:
        st.markdown(f"## 🎹 {ACADEMY_NAME}")
        st.caption(f"👤 {st.session_state.userid} 님")
        menu = st.radio("메뉴", st.session_state.menu_order, format_func=lambda m: MENUS[m], key="menu_radio")
        st.caption("💡 메뉴 순서는 로그인할 때 많이 머문 순서로 바뀌어요.")
        st.divider()
        logout_clicked = st.button("🚪 로그아웃", use_container_width=True)

    if logout_clicked:
        logout()
        st.rerun()

    track_menu(menu)   # 3. learninghistory 기록
    PAGES[menu]()


main()
