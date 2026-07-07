"""
Photo Swap Tool — Web Version (Streamlit)
Phiên bản nâng cấp giao diện & trải nghiệm người dùng
"""

import streamlit as st
from PIL import Image
import io
import time
import zipfile
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
    output_dir.mkdir(parents=True, exist_ok=True)
    ext = ".png" if fmt == "PNG" else ".jpg"
    path = output_dir / f"{filename}{ext}"

    if fmt == "JPG" and pil_image.mode in ("RGBA", "P"):
        pil_image = pil_image.convert("RGB")
    pil_image.save(path, quality=quality if fmt == "JPG" else None)
    return path


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
    output_path = st.text_input(
        "Đường dẫn folder",
        value=str(Path.home() / "PhotoSwap_Results"),
        disabled=not auto_save,
    )

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

run_clicked = st.button(
    "🚀 Bắt đầu xử lý",
    type="primary",
    use_container_width=True,
)
if not (base_file and ref_files):
    st.caption("⚠️ Vui lòng tải lên ảnh gốc và ít nhất một ảnh tham chiếu để bắt đầu.")

st.markdown("</div>", unsafe_allow_html=True)

# ==================== KIỂM TRA ĐIỀU KIỆN ====================
if run_clicked:
    missing = []
    if not base_file:
        missing.append("ảnh gốc (người mẫu)")
    if not ref_files:
        missing.append("ảnh tham chiếu (trang phục)")
    if not st.session_state.get("api_key"):
        missing.append("API Key (nhập ở thanh bên trái rồi bấm 'Lưu key')")

    if missing:
        st.error("❌ Chưa thể bắt đầu, còn thiếu: " + ", ".join(missing))
        run_clicked = False

# ==================== XỬ LÝ ====================
if run_clicked:
    client = genai.Client(api_key=st.session_state["api_key"])
    results = []
    saved_paths = []
    errors = []

    progress = st.progress(0, text="Đang xử lý...")
    status = st.status("Đang chạy Gemini...", expanded=True)

    output_dir = Path(output_path)
    start_time = time.time()

    for i, ref_file in enumerate(ref_files, 1):
        elapsed = time.time() - start_time
        avg = elapsed / max(i - 1, 1)
        remaining = avg * (len(ref_files) - i + 1) if i > 1 else 0
        eta_txt = f" · còn ~{int(remaining)}s" if remaining > 1 else ""
        status.write(f"🔄 Đang xử lý ({i}/{len(ref_files)}): **{ref_file.name}**{eta_txt}")

        try:
            base_pil = Image.open(base_file)
            ref_pil = Image.open(ref_file)

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
                    status.write(f"   ⏳ Thử lại lần {attempt}/{MAX_RETRIES}...")
                    time.sleep(RETRY_BASE_DELAY * (2 ** (attempt - 1)))

            found = False
            for part in getattr(response, "parts", []):
                img = extract_pil_image(part)
                if img:
                    if custom_size:
                        img = img.resize(custom_size, Image.LANCZOS)

                    if auto_save:
                        saved_path = save_image(
                            img, output_dir,
                            Path(ref_file.name).stem + "-result",
                            output_format, jpg_quality,
                        )
                        saved_paths.append(saved_path)

                    buf = io.BytesIO()
                    img.save(buf, format=output_format)
                    results.append({
                        "name": f"{Path(ref_file.name).stem}-result.{output_format.lower()}",
                        "image": img,
                        "bytes": buf.getvalue(),
                    })
                    found = True
                    break

            if found:
                status.write(f"   ✅ Xong: {ref_file.name}")
            else:
                status.write(f"   ⚠️ Không nhận được ảnh kết quả cho: {ref_file.name}")
                errors.append((ref_file.name, "Không nhận được ảnh kết quả từ model"))

        except Exception as e:
            status.write(f"   ❌ Lỗi với {ref_file.name}: {e}")
            errors.append((ref_file.name, str(e)))

        progress.progress(i / len(ref_files))

    total_elapsed = time.time() - start_time
    status.update(
        label=f"✅ Hoàn tất trong {total_elapsed:.0f}s — {len(results)}/{len(ref_files)} ảnh thành công",
        state="complete",
    )

    st.session_state["results"] = results
    st.session_state["saved_paths"] = saved_paths
    st.session_state["errors"] = errors
    st.session_state["has_run"] = True
    st.session_state["last_run_output_dir"] = str(output_path)

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