"""
Photo Swap Tool — Web Version (Streamlit)
Phiên bản nâng cấp giao diện & trải nghiệm người dùng
"""

import streamlit as st
from PIL import Image
import io
import csv
import time
import datetime
import zipfile
import pandas as pd
import requests
from pathlib import Path
from google import genai
from google.genai import types

st.set_page_config(
    page_title="Photo Swap Studio",
    layout="wide",
    page_icon="🪄",
    initial_sidebar_state="expanded",
)

# ==================== CONFIG ====================
MODEL_OPTIONS = {
    "Nano Banana 2 — Khuyến nghị": "gemini-3.1-flash-image",
    "Nano Banana 2 Lite — Nhanh & rẻ nhất": "gemini-3.1-flash-lite-image",
    "Nano Banana Pro — Chất lượng cao nhất": "gemini-3-pro-image",
    "Nano Banana gốc (2.5)": "gemini-2.5-flash-image",
}

RESOLUTION_OPTIONS = {
    "Tự động (mặc định)": None,
    "512px — Tiết kiệm": "512",
    "1K (~1024px)": "1K",
    "2K (~2048px) — Khuyến nghị": "2K",
    "4K (~4096px)": "4K",
}

TOKENS_PER_IMAGE = {"512": 747, "1K": 1120, "2K": 1680, "4K": 2520}
PRICE_TABLE = {
    "gemini-3.1-flash-image": {"512": 0.030, "1K": 0.045, "2K": 0.067, "4K": 0.090},
    "gemini-3.1-flash-lite-image": {"512": 0.022, "1K": 0.034, "2K": 0.050, "4K": 0.070},
    "gemini-3-pro-image": {"512": 0.090, "1K": 0.134, "2K": 0.200, "4K": 0.270},
    "gemini-2.5-flash-image": {"512": 0.039, "1K": 0.039, "2K": 0.039, "4K": 0.039},
}

MAX_RETRIES = 4
RETRY_BASE_DELAY = 5
USD_TO_VND = 26000  # tỷ giá ước tính, có thể chỉnh lại cho đúng thời điểm

LOG_DIR = Path.home() / "PhotoSwap_Logs"
LOG_PATH = LOG_DIR / "billing_log.csv"
LOG_FIELDS = [
    "timestamp", "user", "model", "resolution", "format",
    "ref_image", "status", "cost_usd", "cost_vnd",
]

# ⚠️ ĐỔI MẬT KHẨU NÀY trước khi chia sẻ app cho bạn bè!
# Chỉ ai biết mật khẩu này mới xem được mục "Lịch sử sử dụng & thanh toán".
# Nếu deploy lên Streamlit Cloud, nên tạo file .streamlit/secrets.toml với dòng:
#   admin_password = "mật khẩu của bạn"
# để không lộ mật khẩu ngay trong code.
try:
    ADMIN_PASSWORD = st.secrets["admin_password"]
except Exception:
    ADMIN_PASSWORD = "doimatkhaunay123"

# ==================== ĐỒNG BỘ LOG VỀ 1 NƠI (KHÔNG CẦN DATABASE) ====================
# Nếu bạn bè chạy app trên MÁY CỦA HỌ (không phải chung 1 server), log CSV sẽ nằm
# trên máy của từng người, bạn sẽ không tự động thấy được.
# Cách khắc phục không cần database thật: dùng 1 Google Sheet làm nơi lưu trữ chung.
# Mỗi máy chạy app sẽ tự gửi 1 dòng log lên Sheet đó qua đường link Web App bên dưới.
#
# Cách lấy URL này (làm 1 lần, chỉ chủ app cần làm):
#   1. Tạo 1 Google Sheet mới (trên Drive của bạn).
#   2. Vào Extensions > Apps Script, xoá code mẫu, dán đoạn script mình đưa kèm.
#   3. Bấm Deploy > New deployment > chọn loại "Web app".
#      - Execute as: Me
#      - Who has access: Anyone
#   4. Copy "Web app URL" và dán vào biến REMOTE_LOG_WEBHOOK_URL bên dưới.
#   5. (Tuỳ chọn) Dán link chia sẻ (chỉ xem) của chính Google Sheet vào REMOTE_SHEET_VIEW_URL
#      để có nút mở nhanh trong app.
#
# Nếu để trống, app vẫn hoạt động bình thường — chỉ là log sẽ chỉ lưu cục bộ trên từng máy.
try:
    REMOTE_LOG_WEBHOOK_URL = st.secrets["remote_log_webhook_url"]
except Exception:
    REMOTE_LOG_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbxKYNYVmQ6JASp5xOf9EmuSjRT3l4w25bll9gg22fSFBmYhGNVhfg5FAxS6zxqG6FBS/exec"  # dán URL Web App (Google Apps Script) vào đây

try:
    REMOTE_SHEET_VIEW_URL = st.secrets["remote_sheet_view_url"]
except Exception:
    REMOTE_SHEET_VIEW_URL = ""  # dán link chia sẻ (chỉ xem) của Google Sheet vào đây, không bắt buộc

SIZE_PRESETS = {
    "Giữ nguyên": None,
    "9:16 (1080x1920)": (1080, 1920),
    "3:4 (1080x1440)": (1080, 1440),
    "Instagram (1080x1080)": (1080, 1080),
    "Dọc (1080x1350)": (1080, 1350),
    "16:9 (1920x1080)": (1920, 1080),
    "Tuỳ chỉnh": "custom",
}

# ==================== SESSION STATE ====================
for key, default in {
    "api_key": "",
    "results": [],
    "saved_paths": [],
    "errors": [],
    "has_run": False,
    "is_processing": False,
    "last_run_output_dir": "",
    "proc_running": False,
    "proc_idx": 0,
    "proc_total": 0,
    "proc_start_time": None,
    "proc_log": [],
    "used_names": set(),
    "stop_requested": False,
    "user_name": "",
    "is_admin": False,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ==================== STYLE ====================
st.markdown(
    """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header[data-testid="stHeader"] {
        background: transparent;
        height: 3rem;
    }
    /* Giữ lại nút thu/mở sidebar, chỉ chỉnh màu cho rõ trên nền tối */
    [data-testid="collapsedControl"] {
        visibility: visible !important;
        display: flex !important;
        color: var(--ps-text, #F1EEFB) !important;
        z-index: 999999;
    }
    [data-testid="collapsedControl"] svg {
        fill: #F1EEFB !important;
    }
    [data-testid="stSidebarCollapseButton"] svg,
    [data-testid="baseButton-headerNoPadding"] svg {
        fill: #F1EEFB !important;
    }

    :root {
        --ps-primary: #A78BFA;
        --ps-primary-dark: #C4B5FD;
        --ps-accent: #F472B6;
        --ps-bg: #15121F;
        --ps-surface: #221D36;
        --ps-surface-2: #2A2444;
        --ps-border: #3A3358;
        --ps-text: #F1EEFB;
        --ps-text-muted: #B4ACD1;
    }

    .stApp {
        background: linear-gradient(180deg, #15121F 0%, #1B1730 100%);
        color: var(--ps-text);
    }

    /* Đảm bảo mọi chữ mặc định trong app đều tương phản với nền tối */
    .stApp, .stApp p, .stApp span, .stApp label, .stApp div,
    .stMarkdown, .stCaption, .stText {
        color: var(--ps-text) !important;
    }
    .stApp .st-emotion-cache-1v0mbdj, .stApp small,
    [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {
        color: var(--ps-text-muted) !important;
    }

    section[data-testid="stSidebar"] {
        background: #1B1730;
        border-right: 1px solid var(--ps-border);
    }
    section[data-testid="stSidebar"] * {
        color: var(--ps-text) !important;
    }

    .ps-hero {
        background: linear-gradient(120deg, #6D28D9 0%, #DB2777 100%);
        padding: 28px 32px;
        border-radius: 20px;
        color: white;
        margin-bottom: 22px;
        box-shadow: 0 10px 30px rgba(124, 58, 237, 0.35);
    }
    .ps-hero h1 {
        margin: 0 0 4px 0;
        font-size: 1.7rem;
        font-weight: 800;
        color: white !important;
    }
    .ps-hero p {
        margin: 0;
        opacity: 0.92;
        font-size: 0.95rem;
        color: white !important;
    }

    .ps-card {
        background: var(--ps-surface);
        border: 1px solid var(--ps-border);
        border-radius: 16px;
        padding: 18px 20px;
        box-shadow: 0 2px 12px rgba(0, 0, 0, 0.25);
        margin-bottom: 16px;
    }
    .ps-card, .ps-card p, .ps-card span, .ps-card div {
        color: var(--ps-text) !important;
    }

    .ps-step-badge {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 26px; height: 26px;
        border-radius: 50%;
        background: var(--ps-primary);
        color: #1B1730 !important;
        font-weight: 800;
        font-size: 0.85rem;
        margin-right: 8px;
    }
    .ps-section-title {
        font-size: 1.05rem;
        font-weight: 700;
        color: var(--ps-text) !important;
        display: flex;
        align-items: center;
        margin-bottom: 10px;
    }

    .ps-status-ok {
        background: rgba(52, 211, 153, 0.15); color: #6EE7B7 !important;
        border: 1px solid rgba(52, 211, 153, 0.4);
        padding: 6px 12px; border-radius: 999px;
        font-size: 0.82rem; font-weight: 600;
        display: inline-block;
    }
    .ps-status-warn {
        background: rgba(251, 191, 36, 0.15); color: #FCD34D !important;
        border: 1px solid rgba(251, 191, 36, 0.4);
        padding: 6px 12px; border-radius: 999px;
        font-size: 0.82rem; font-weight: 600;
        display: inline-block;
    }

    .ps-cost-box {
        background: linear-gradient(120deg, #2A2444, #3B1E33);
        border: 1px solid var(--ps-border);
        border-radius: 14px;
        padding: 14px 18px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .ps-cost-num {
        font-size: 1.4rem;
        font-weight: 800;
        color: var(--ps-primary-dark) !important;
    }
    .ps-cost-label {
        font-size: 0.8rem;
        color: var(--ps-text-muted) !important;
    }

    .ps-empty {
        text-align: center;
        padding: 50px 20px;
        color: var(--ps-text-muted) !important;
        border: 1px dashed var(--ps-border);
        border-radius: 12px;
    }

    div.stButton > button[kind="primary"] {
        background: linear-gradient(120deg, #7C3AED, var(--ps-accent));
        border: none;
        border-radius: 12px;
        padding: 0.7rem 1rem;
        font-weight: 700;
        color: white !important;
        box-shadow: 0 6px 16px rgba(124,58,237,0.40);
        transition: transform 0.15s ease;
    }
    div.stButton > button[kind="primary"]:hover {
        transform: translateY(-1px);
    }
    div.stButton > button[kind="secondary"] {
        background: var(--ps-surface-2);
        color: var(--ps-text) !important;
        border: 1px solid var(--ps-border);
        border-radius: 10px;
    }

    section[data-testid="stFileUploaderDropzone"] {
        border-radius: 14px !important;
        border: 1.5px dashed #6D28D9 !important;
        background: var(--ps-surface-2) !important;
    }
    section[data-testid="stFileUploaderDropzone"] * {
        color: var(--ps-text) !important;
    }

    .stTextInput input, .stNumberInput input, .stTextArea textarea {
        background: var(--ps-surface-2) !important;
        color: var(--ps-text) !important;
        border: 1px solid var(--ps-border) !important;
    }

    [data-baseweb="select"] > div {
        background: var(--ps-surface-2) !important;
        color: var(--ps-text) !important;
        border-color: var(--ps-border) !important;
    }

    .stTabs [data-baseweb="tab-list"] { gap: 6px; }
    .stTabs [data-baseweb="tab"] {
        border-radius: 10px 10px 0 0;
        padding: 8px 16px;
        font-weight: 600;
        color: var(--ps-text) !important;
    }

    [data-testid="stExpander"] {
        background: var(--ps-surface-2);
        border: 1px solid var(--ps-border);
        border-radius: 12px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def extract_pil_image(part):
    inline = getattr(part, "inline_data", None)
    data = getattr(inline, "data", None) if inline else None
    if data:
        if isinstance(data, str):
            import base64
            data = base64.b64decode(data)
        return Image.open(io.BytesIO(data))
    return None


def save_image(pil_image, output_dir: Path, filename: str, fmt: str, quality: int):
    """filename đã bao gồm đuôi mở rộng và đã được đảm bảo không trùng."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename

    if fmt == "JPG" and pil_image.mode in ("RGBA", "P"):
        pil_image = pil_image.convert("RGB")
    pil_image.save(path, quality=quality if fmt == "JPG" else None)
    return path


def get_unique_name(base_name: str, ext: str, used_names: set, output_dir: Path = None) -> str:
    """Trả về tên file (kèm đuôi) không bị trùng với file đã tạo trong phiên này
    lẫn file đã có sẵn trong folder đích (nếu auto_save bật)."""
    candidate = f"{base_name}{ext}"
    counter = 1
    while candidate in used_names or (output_dir and (output_dir / candidate).exists()):
        candidate = f"{base_name}_{counter}{ext}"
        counter += 1
    used_names.add(candidate)
    return candidate


# Các mã lỗi phổ biến của Gemini API mà KHÔNG bị trừ token/tiền
# (theo trang billing chính thức: request lỗi 400/500 không bị tính phí token;
#  logic tương tự áp dụng cho các lỗi khác vì request bị từ chối trước khi model
#  kịp sinh nội dung, nên chưa phát sinh chi phí):
#   400 INVALID_ARGUMENT, 401/403 PERMISSION_DENIED, 404 NOT_FOUND,
#   429 RESOURCE_EXHAUSTED (hết quota/rate limit), 500 INTERNAL,
#   503 UNAVAILABLE (quá tải), 504 DEADLINE_EXCEEDED (timeout)
NON_BILLABLE_STATUSES = {"error", "no_image"}


def log_usage(user, model_label, res_label, fmt, ref_image, status, cost_usd):
    """Ghi 1 dòng log mỗi khi xử lý xong 1 ảnh (thành công hoặc lỗi).
    Chỉ tính tiền (cost_usd > 0) khi status == "success" — các lỗi API
    phổ biến (400/429/500/503...) không làm tốn token nên được ghi 0đ."""
    if status in NON_BILLABLE_STATUSES:
        cost_usd = 0.0

    row = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user": user or "Không rõ",
        "model": model_label,
        "resolution": res_label,
        "format": fmt,
        "ref_image": ref_image,
        "status": status,
        "cost_usd": round(cost_usd, 4),
        "cost_vnd": round(cost_usd * USD_TO_VND),
    }

    # --- Ghi cục bộ trên máy đang chạy app ---
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    is_new = not LOG_PATH.exists()
    with open(LOG_PATH, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow(row)

    # --- Gửi thêm lên Google Sheet trung tâm (nếu đã cấu hình) ---
    # Không chặn app nếu gửi lỗi/mất mạng — log cục bộ vẫn luôn được ghi ở trên.
    if REMOTE_LOG_WEBHOOK_URL:
        try:
            requests.post(REMOTE_LOG_WEBHOOK_URL, json=row, timeout=5)
        except Exception:
            pass


def load_usage_log() -> pd.DataFrame:
    if not LOG_PATH.exists():
        return pd.DataFrame(columns=LOG_FIELDS)
    try:
        return pd.read_csv(LOG_PATH)
    except Exception:
        return pd.DataFrame(columns=LOG_FIELDS)


def pick_folder_dialog():
    """Mở hộp thoại chọn thư mục của hệ điều hành (chỉ hoạt động khi chạy app
    trên máy tính cá nhân có giao diện, không hoạt động khi deploy lên server)."""
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.wm_attributes("-topmost", 1)
        folder = filedialog.askdirectory()
        root.destroy()
        return folder or None
    except Exception:
        return None


def make_zip(results):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for res in results:
            zf.writestr(res["name"], res["bytes"])
    buf.seek(0)
    return buf


# ==================== HERO HEADER ====================
st.markdown(
    """
    <div class="ps-hero">
        <h1>🪄 Photo Swap Studio</h1>
        <p>Thay trang phục hàng loạt bằng AI — nhanh, đẹp, chuyên nghiệp</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ==================== SIDEBAR ====================
with st.sidebar:
    st.markdown("### 🔑 API Key")
    api_key_input = st.text_input(
        "Gemini API Key",
        type="password",
        value=st.session_state.get("api_key", ""),
        placeholder="Dán API key vào đây...",
        label_visibility="collapsed",
    )
    col_save, col_status = st.columns([1, 1])
    with col_save:
        if st.button("💾 Lưu key", use_container_width=True):
            st.session_state["api_key"] = api_key_input
            st.toast("Đã lưu API key cho phiên này ✅")

    if st.session_state.get("api_key"):
        st.markdown('<span class="ps-status-ok">● Đã kết nối</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="ps-status-warn">● Chưa có API key</span>', unsafe_allow_html=True)

    st.caption("[Lấy API Key miễn phí →](https://aistudio.google.com/apikey)")
    st.divider()

    st.markdown("### 👤 Người dùng")
    user_name_input = st.text_input(
        "Tên/nickname của bạn",
        value=st.session_state.get("user_name", ""),
        placeholder="VD: Minh, Lan, Hùng...",
        help="Dùng để ghi nhận vào lịch sử thanh toán, vì app đang dùng chung 1 API Key.",
    )
    st.session_state["user_name"] = user_name_input
    if not user_name_input:
        st.markdown(
            '<span class="ps-status-warn">● Nhập tên để ghi nhận chi phí</span>',
            unsafe_allow_html=True,
        )
    st.divider()

    st.markdown("### ⚙️ Cấu hình model")

    if "model_select" not in st.session_state:
        st.session_state["model_select"] = list(MODEL_OPTIONS.keys())[0]
    if "res_select" not in st.session_state:
        st.session_state["res_select"] = list(RESOLUTION_OPTIONS.keys())[3]

    qcol1, qcol2 = st.columns(2)
    with qcol1:
        if st.button("⚡ Rẻ nhất\n(512px)", use_container_width=True):
            st.session_state["model_select"] = "Nano Banana 2 Lite — Nhanh & rẻ nhất"
            st.session_state["res_select"] = "512px — Tiết kiệm"
            st.rerun()
    with qcol2:
        if st.button("🎯 Chất lượng\n(Flash)", use_container_width=True):
            st.session_state["model_select"] = "Nano Banana 2 — Khuyến nghị"
            st.session_state["res_select"] = "2K (~2048px) — Khuyến nghị"
            st.rerun()

    model_label = st.selectbox("Model", list(MODEL_OPTIONS.keys()), key="model_select")
    model_id = MODEL_OPTIONS[model_label]

    res_label = st.selectbox("Độ phân giải", list(RESOLUTION_OPTIONS.keys()), key="res_select")
    resolution_code = RESOLUTION_OPTIONS[res_label]

    st.divider()
    st.markdown("### 📤 Xuất file")
    output_format = st.selectbox("Định dạng", ["PNG", "JPG"], index=0)
    jpg_quality = st.slider("Chất lượng JPG", 70, 100, 92) if output_format == "JPG" else 95

    size_choice = st.selectbox("Kích thước xuất", list(SIZE_PRESETS.keys()))
    if size_choice == "Tuỳ chỉnh":
        cw, ch = st.columns(2)
        custom_w = cw.number_input("Rộng", 512, 4096, 1024)
        custom_h = ch.number_input("Cao", 512, 4096, 1024)
        custom_size = (custom_w, custom_h)
    else:
        custom_size = SIZE_PRESETS[size_choice]

    st.divider()
    st.markdown("### 💾 Lưu kết quả")
    auto_save = st.checkbox("Tự động lưu vào folder máy tính", value=True)

    if "output_path" not in st.session_state:
        st.session_state["output_path"] = str(Path.home() / "PhotoSwap_Results")

    col_path, col_pick = st.columns([3, 1])
    with col_path:
        output_path = st.text_input(
            "Đường dẫn folder",
            key="output_path",
            disabled=not auto_save,
            label_visibility="collapsed",
        )
    with col_pick:
        if st.button("📁", use_container_width=True, disabled=not auto_save, help="Chọn thư mục"):
            picked = pick_folder_dialog()
            if picked:
                st.session_state["output_path"] = picked
                st.rerun()
            else:
                st.toast("Không mở được hộp thoại chọn thư mục trên môi trường này, hãy dán đường dẫn thủ công.")

    st.divider()
    with st.expander("🔒 Khu vực quản trị"):
        if st.session_state.get("is_admin"):
            st.markdown(
                '<span class="ps-status-ok">● Đang xem với quyền quản trị</span>',
                unsafe_allow_html=True,
            )
            if st.button("Đăng xuất quản trị", use_container_width=True):
                st.session_state["is_admin"] = False
                st.rerun()
        else:
            admin_pwd = st.text_input("Mật khẩu quản trị", type="password", key="admin_pwd_input")
            if st.button("Đăng nhập", use_container_width=True):
                if admin_pwd == ADMIN_PASSWORD:
                    st.session_state["is_admin"] = True
                    st.rerun()
                else:
                    st.error("Sai mật khẩu.")

# ==================== YÊU CẦU NHẬP TÊN TRƯỚC KHI DÙNG ====================
if not st.session_state.get("user_name"):
    st.markdown('<div class="ps-card">', unsafe_allow_html=True)
    st.markdown(
        '<div class="ps-section-title">👋 Chào bạn, trước khi bắt đầu...</div>',
        unsafe_allow_html=True,
    )
    st.warning(
        "App đang dùng chung 1 API Key nên cần bạn nhập **tên/nickname** ở mục "
        "**👤 Người dùng** trên thanh bên trái trước, để hệ thống ghi nhận đúng chi phí của từng người."
    )
    st.markdown("</div>", unsafe_allow_html=True)
    st.stop()

# ==================== BƯỚC 1: ẢNH ====================
st.markdown('<div class="ps-card">', unsafe_allow_html=True)
st.markdown(
    '<div class="ps-section-title"><span class="ps-step-badge">1</span>Tải ảnh lên</div>',
    unsafe_allow_html=True,
)

col1, col2 = st.columns([1, 1.2], gap="large")

with col1:
    st.markdown("**📷 Ảnh gốc (người mẫu)**")
    base_file = st.file_uploader(
        "Chọn ảnh gốc", type=["jpg", "jpeg", "png", "webp"], key="base",
        label_visibility="collapsed",
    )
    if base_file:
        st.image(base_file, caption="Ảnh gốc", width=140)
    else:
        st.markdown(
            '<div class="ps-empty">⬆️ Kéo thả hoặc chọn ảnh người mẫu</div>',
            unsafe_allow_html=True,
        )

with col2:
    st.markdown("**👕 Ảnh tham chiếu (trang phục)** — có thể chọn nhiều ảnh")
    ref_files = st.file_uploader(
        "Chọn nhiều ảnh tham chiếu",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        key="refs",
        label_visibility="collapsed",
    )
    if ref_files:
        st.markdown(
            f'<span class="ps-status-ok">✅ Đã chọn {len(ref_files)} ảnh</span>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="ps-empty">⬆️ Kéo thả hoặc chọn ảnh trang phục</div>',
            unsafe_allow_html=True,
        )
st.markdown("</div>", unsafe_allow_html=True)

# ==================== BƯỚC 2: PROMPT ====================
st.markdown('<div class="ps-card">', unsafe_allow_html=True)
st.markdown(
    '<div class="ps-section-title"><span class="ps-step-badge">2</span>Mô tả yêu cầu</div>',
    unsafe_allow_html=True,
)
prompt = st.text_area(
    "Mô tả cách thay trang phục",
    value="Thay áo trong ảnh thứ 2 vào người ở ảnh thứ 1, giữ nguyên dáng người, khuôn mặt và nền.",
    height=90,
    label_visibility="collapsed",
)
st.markdown("</div>", unsafe_allow_html=True)

# ==================== BƯỚC 3: CHI PHÍ + CHẠY ====================
st.markdown('<div class="ps-card">', unsafe_allow_html=True)
st.markdown(
    '<div class="ps-section-title"><span class="ps-step-badge">3</span>Xử lý</div>',
    unsafe_allow_html=True,
)

if ref_files:
    tier = resolution_code or "1K"
    total_price_usd = len(ref_files) * PRICE_TABLE.get(model_id, {}).get(tier, 0.05)
    total_price_vnd = total_price_usd * USD_TO_VND
    st.markdown(
        f"""
        <div class="ps-cost-box">
            <div>
                <div class="ps-cost-label">Số ảnh sẽ xử lý</div>
                <div class="ps-cost-num">{len(ref_files)} ảnh</div>
            </div>
            <div style="text-align:right;">
                <div class="ps-cost-label">Chi phí ước tính</div>
                <div class="ps-cost-num">{total_price_vnd:,.0f}₫</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(f"Tỷ giá quy đổi tạm tính: 1 USD ≈ {USD_TO_VND:,.0f}₫")
    st.write("")

# ==================== NÚT ĐIỀU KHIỂN ====================
if st.session_state.get("proc_running"):
    if st.button("⏹ Dừng tiến trình", use_container_width=True):
        st.session_state["stop_requested"] = True
    start_clicked = False
else:
    start_clicked = st.button(
        "🚀 Bắt đầu xử lý",
        type="primary",
        use_container_width=True,
    )
if not (base_file and ref_files):
    st.caption("⚠️ Vui lòng tải lên ảnh gốc và ít nhất một ảnh tham chiếu để bắt đầu.")

st.markdown("</div>", unsafe_allow_html=True)

# ==================== KIỂM TRA ĐIỀU KIỆN & KHỞI TẠO BATCH MỚI ====================
if start_clicked:
    missing = []
    if not base_file:
        missing.append("ảnh gốc (người mẫu)")
    if not ref_files:
        missing.append("ảnh tham chiếu (trang phục)")
    if not st.session_state.get("api_key"):
        missing.append("API Key (nhập ở thanh bên trái rồi bấm 'Lưu key')")
    if not st.session_state.get("user_name"):
        missing.append("Tên của bạn (để ghi nhận chi phí, nhập ở thanh bên trái)")

    if missing:
        st.error("❌ Chưa thể bắt đầu, còn thiếu: " + ", ".join(missing))
    else:
        st.session_state["proc_running"] = True
        st.session_state["proc_idx"] = 0
        st.session_state["proc_total"] = len(ref_files)
        st.session_state["proc_start_time"] = time.time()
        st.session_state["proc_log"] = []
        st.session_state["used_names"] = set()
        st.session_state["results"] = []
        st.session_state["saved_paths"] = []
        st.session_state["errors"] = []
        st.session_state["has_run"] = False
        st.session_state["stop_requested"] = False
        st.session_state["last_run_output_dir"] = str(output_path)
        st.rerun()

# ==================== XỬ LÝ: MỖI LẦN RERUN XỬ LÝ 1 ẢNH ====================
# (Cách này giúp nút "Dừng tiến trình" có thể bấm được giữa chừng,
#  vì Streamlit chỉ nhận thao tác của người dùng giữa các lần rerun.)
if st.session_state.get("proc_running"):
    idx = st.session_state["proc_idx"]
    total = st.session_state["proc_total"]

    st.markdown('<div class="ps-card">', unsafe_allow_html=True)
    st.markdown('<div class="ps-section-title">⏳ Đang xử lý</div>', unsafe_allow_html=True)
    st.progress(idx / total if total else 0, text=f"{idx}/{total} ảnh")

    if st.session_state.get("stop_requested"):
        st.session_state["proc_running"] = False
        st.session_state["has_run"] = True
        st.warning(f"⏹ Đã dừng theo yêu cầu — đã xử lý {idx}/{total} ảnh.")

    elif idx >= total:
        st.session_state["proc_running"] = False
        st.session_state["has_run"] = True
        elapsed = time.time() - (st.session_state.get("proc_start_time") or time.time())
        st.success(f"✅ Hoàn tất trong {elapsed:.0f}s")

    else:
        ref_file = ref_files[idx]
        st.write(f"🔄 Đang xử lý ({idx + 1}/{total}): **{ref_file.name}**")

        try:
            client = genai.Client(api_key=st.session_state["api_key"])
            output_dir = Path(output_path)

            base_pil = Image.open(base_file)
            ref_pil = Image.open(ref_file)

            response = None
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    config = None
                    if resolution_code:
                        try:
                            config = types.GenerateContentConfig(
                                response_modalities=["TEXT", "IMAGE"],
                                image_config=types.ImageConfig(image_size=resolution_code),
                            )
                        except Exception:
                            pass

                    response = client.models.generate_content(
                        model=model_id,
                        contents=[prompt, base_pil, ref_pil],
                        config=config,
                    )
                    break
                except Exception as e:
                    if attempt == MAX_RETRIES:
                        raise e
                    st.session_state["proc_log"].append(
                        f"⏳ {ref_file.name}: thử lại lần {attempt}/{MAX_RETRIES}..."
                    )
                    time.sleep(RETRY_BASE_DELAY * (2 ** (attempt - 1)))

            found = False
            for part in getattr(response, "parts", []):
                img = extract_pil_image(part)
                if img:
                    if custom_size:
                        img = img.resize(custom_size, Image.LANCZOS)

                    ext = ".png" if output_format == "PNG" else ".jpg"
                    base_name = Path(ref_file.name).stem + "-result"
                    unique_name = get_unique_name(
                        base_name, ext, st.session_state["used_names"],
                        output_dir if auto_save else None,
                    )

                    if auto_save:
                        saved_path = save_image(img, output_dir, unique_name, output_format, jpg_quality)
                        st.session_state["saved_paths"].append(saved_path)

                    buf = io.BytesIO()
                    img.save(buf, format=output_format)
                    st.session_state["results"].append({
                        "name": unique_name,
                        "bytes": buf.getvalue(),
                    })
                    found = True
                    break

            if found:
                st.session_state["proc_log"].append(f"✅ Xong: {ref_file.name}")
                log_status = "success"
            else:
                st.session_state["proc_log"].append(f"⚠️ Không nhận được ảnh kết quả cho: {ref_file.name}")
                st.session_state["errors"].append((ref_file.name, "Không nhận được ảnh kết quả từ model"))
                log_status = "no_image"

        except Exception as e:
            st.session_state["proc_log"].append(f"❌ Lỗi với {ref_file.name}: {e}")
            st.session_state["errors"].append((ref_file.name, str(e)))
            log_status = "error"

        # Ghi log thanh toán cho ảnh vừa xử lý
        tier_for_log = resolution_code or "1K"
        cost_usd_one = PRICE_TABLE.get(model_id, {}).get(tier_for_log, 0.05)
        log_usage(
            user=st.session_state.get("user_name"),
            model_label=model_label,
            res_label=res_label,
            fmt=output_format,
            ref_image=ref_file.name,
            status=log_status,
            cost_usd=cost_usd_one,
        )

        st.session_state["proc_idx"] = idx + 1

    if st.session_state.get("proc_log"):
        with st.expander("📜 Nhật ký xử lý", expanded=True):
            for line in st.session_state["proc_log"][-40:]:
                st.write(line)

    st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state.get("proc_running"):
        st.rerun()

# ==================== TỔNG KẾT (bền vững qua rerun) ====================
results = st.session_state.get("results", [])
saved_paths = st.session_state.get("saved_paths", [])
errors = st.session_state.get("errors", [])

if st.session_state.get("has_run"):
    st.markdown('<div class="ps-card">', unsafe_allow_html=True)
    st.markdown(
        '<div class="ps-section-title">📋 Tổng kết</div>',
        unsafe_allow_html=True,
    )

    ok_count = len(results)
    fail_count = len(errors)
    total = ok_count + fail_count

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            f'<span class="ps-status-ok">✅ Thành công: {ok_count}/{total}</span>',
            unsafe_allow_html=True,
        )
    with c2:
        if fail_count:
            st.markdown(
                f'<span class="ps-status-warn">⚠️ Lỗi: {fail_count}/{total}</span>',
                unsafe_allow_html=True,
            )

    if saved_paths:
        st.success(
            f"✅ Đã tự động lưu {len(saved_paths)} ảnh vào: `{st.session_state.get('last_run_output_dir', output_path)}`"
        )
    elif not auto_save and results:
        zip_buf = make_zip(results)
        st.download_button(
            "⬇️ Tải tất cả kết quả (.zip)",
            data=zip_buf,
            file_name="photo_swap_results.zip",
            mime="application/zip",
            use_container_width=True,
        )

    if errors:
        with st.expander(f"❌ Chi tiết {fail_count} ảnh lỗi"):
            for name, err_msg in errors:
                st.write(f"**{name}**: {err_msg}")

    st.markdown("</div>", unsafe_allow_html=True)

# ==================== LỊCH SỬ SỬ DỤNG & THANH TOÁN (chỉ admin) ====================
if st.session_state.get("is_admin"):
    st.markdown('<div class="ps-card">', unsafe_allow_html=True)
    st.markdown(
        '<div class="ps-section-title">💳 Lịch sử sử dụng & thanh toán</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "App dùng chung 1 API Key nên phần này ghi nhận theo **tên bạn tự nhập** ở thanh bên trái, "
        "không phải đăng nhập thật — mọi người cần tự giác nhập đúng tên để số liệu chính xác."
    )

    if REMOTE_LOG_WEBHOOK_URL:
        st.markdown(
            '<span class="ps-status-ok">☁️ Đang đồng bộ log lên Google Sheet trung tâm</span>',
            unsafe_allow_html=True,
        )
        if REMOTE_SHEET_VIEW_URL:
            st.link_button("📄 Mở Google Sheet tổng hợp (tất cả các máy)", REMOTE_SHEET_VIEW_URL,
                            use_container_width=True)
        st.caption("Bảng dưới đây chỉ đọc từ log **trên máy này**. Muốn xem gộp từ mọi máy, mở Google Sheet ở trên.")
    else:
        st.markdown(
            '<span class="ps-status-warn">⚠️ Chưa đồng bộ trung tâm — log chỉ lưu trên máy này</span>',
            unsafe_allow_html=True,
        )
        st.caption(
            "Nếu bạn bè chạy app trên máy khác, log của họ sẽ KHÔNG hiện ở đây. "
            "Xem hướng dẫn cấu hình `REMOTE_LOG_WEBHOOK_URL` ở đầu file `app_web.py` để gom log về 1 Google Sheet chung."
        )

    log_df = load_usage_log()

    if log_df.empty:
        st.info("Chưa có dữ liệu sử dụng nào được ghi nhận.")
    else:
        log_df["cost_usd"] = pd.to_numeric(log_df["cost_usd"], errors="coerce").fillna(0)
        log_df["cost_vnd"] = pd.to_numeric(log_df["cost_vnd"], errors="coerce").fillna(0)
        log_df["timestamp"] = pd.to_datetime(log_df["timestamp"], errors="coerce")

        # --- Tổng chi tiêu TOÀN BỘ từ trước tới giờ (không phụ thuộc bộ lọc) ---
        total_all_time_vnd = log_df["cost_vnd"].sum()
        total_all_time_images = len(log_df)
        tcol1, tcol2 = st.columns(2)
        with tcol1:
            st.markdown(
                f'<div class="ps-cost-box"><div>'
                f'<div class="ps-cost-label">💰 Tổng đã chi tiêu (từ trước đến giờ)</div>'
                f'<div class="ps-cost-num">{total_all_time_vnd:,.0f}₫</div>'
                f'</div></div>',
                unsafe_allow_html=True,
            )
        with tcol2:
            st.markdown(
                f'<div class="ps-cost-box"><div>'
                f'<div class="ps-cost-label">🖼️ Tổng số ảnh đã xử lý (từ trước đến giờ)</div>'
                f'<div class="ps-cost-num">{total_all_time_images} ảnh</div>'
                f'</div></div>',
                unsafe_allow_html=True,
            )
        st.caption(
            "File log được **cộng dồn mãi mãi**, không tự xoá hay reset qua ngày mới — "
            "hôm nay dùng bao nhiêu, mai mở lên vẫn còn nguyên và cộng thêm vào, cho đến khi bạn chủ động xoá file log."
        )
        st.write("")

        # --- Bộ lọc theo ngày ---
        min_date = log_df["timestamp"].min().date()
        max_date = log_df["timestamp"].max().date()

        qf1, qf2, qf3 = st.columns(3)
        with qf1:
            if st.button("📅 Hôm nay", use_container_width=True):
                st.session_state["log_from_date"] = datetime.date.today()
                st.session_state["log_to_date"] = datetime.date.today()
        with qf2:
            if st.button("📅 7 ngày qua", use_container_width=True):
                st.session_state["log_from_date"] = datetime.date.today() - datetime.timedelta(days=6)
                st.session_state["log_to_date"] = datetime.date.today()
        with qf3:
            if st.button("📅 Tất cả", use_container_width=True):
                st.session_state["log_from_date"] = min_date
                st.session_state["log_to_date"] = max_date

        if "log_from_date" not in st.session_state:
            st.session_state["log_from_date"] = min_date
        if "log_to_date" not in st.session_state:
            st.session_state["log_to_date"] = max_date

        dcol1, dcol2 = st.columns(2)
        with dcol1:
            from_date = st.date_input("Từ ngày", key="log_from_date")
        with dcol2:
            to_date = st.date_input("Đến ngày", key="log_to_date")

        mask = (log_df["timestamp"].dt.date >= from_date) & (log_df["timestamp"].dt.date <= to_date)
        filtered = log_df[mask]

        # --- Tổng theo người dùng (trong khoảng đã lọc) ---
        summary = (
            filtered.groupby("user")
            .agg(so_anh=("ref_image", "count"), tong_usd=("cost_usd", "sum"), tong_vnd=("cost_vnd", "sum"))
            .reset_index()
            .sort_values("tong_vnd", ascending=False)
        )
        summary.columns = ["Người dùng", "Số ảnh", "Tổng (USD)", "Tổng (VNĐ)"]
        summary["Tổng (USD)"] = summary["Tổng (USD)"].round(2)
        summary["Tổng (VNĐ)"] = summary["Tổng (VNĐ)"].round(0).astype(int)

        st.markdown("**📊 Chi phí theo từng người (trong khoảng đã chọn)**")
        st.dataframe(summary, use_container_width=True, hide_index=True)

        # --- Chi tiêu theo từng ngày (trong khoảng đã lọc) ---
        daily = (
            filtered.assign(ngay=filtered["timestamp"].dt.date)
            .groupby("ngay")
            .agg(so_anh=("ref_image", "count"), tong_vnd=("cost_vnd", "sum"))
            .reset_index()
            .sort_values("ngay", ascending=False)
        )
        daily.columns = ["Ngày", "Số ảnh", "Tổng (VNĐ)"]
        daily["Tổng (VNĐ)"] = daily["Tổng (VNĐ)"].round(0).astype(int)

        st.markdown("**📅 Chi tiêu theo từng ngày (trong khoảng đã chọn)**")
        st.dataframe(daily, use_container_width=True, hide_index=True)

        total_vnd_filtered = filtered["cost_vnd"].sum()
        st.markdown(
            f'<div class="ps-cost-box"><div class="ps-cost-label">Tổng trong khoảng đã chọn</div>'
            f'<div class="ps-cost-num">{total_vnd_filtered:,.0f}₫</div></div>',
            unsafe_allow_html=True,
        )

        with st.expander(f"📜 Xem chi tiết log ({len(filtered)} dòng)"):
            st.dataframe(
                filtered.sort_values("timestamp", ascending=False),
                use_container_width=True,
                hide_index=True,
            )

        with open(LOG_PATH, "rb") as f:
            st.download_button(
                "⬇️ Tải toàn bộ file log (.csv)",
                data=f.read(),
                file_name="billing_log.csv",
                mime="text/csv",
                use_container_width=True,
            )

    st.markdown("</div>", unsafe_allow_html=True)