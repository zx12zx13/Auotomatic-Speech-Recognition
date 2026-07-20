import secrets

import gradio as gr
from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# Impor fungsi untuk membuat aplikasi Gradio dari app.py
from app import create_unified_app, tema_modul, CSS_SELARAS
import database as db
from session import sesi_aktif

# --- Konfigurasi ---
app = FastAPI()
templates = Jinja2Templates(directory="templates")


def _filter_ganti_t(nilai):
    """Format waktu ISO ('2026-07-17T10:03:05') menjadi '2026-07-17 10:03'."""
    if not nilai:
        return "-"
    return str(nilai).replace("T", " ")[:16]


def _filter_durasi(detik):
    """Format durasi detik menjadi teks, mis. 125.3 -> '2 mnt 5 dtk'."""
    if detik is None:
        return "-"
    detik = int(detik)
    if detik < 60:
        return f"{detik} dtk"
    return f"{detik // 60} mnt {detik % 60} dtk"


templates.env.filters["ganti_t"] = _filter_ganti_t
templates.env.filters["durasi"] = _filter_durasi

# Menyiapkan tabel basis data saat aplikasi dimuat.
db.init_db()


# --- Model untuk data login ---
class User(BaseModel):
    id_user: int
    username: str


def get_current_user(request: Request):
    """Dependensi untuk memeriksa apakah pengguna sudah login."""
    token = request.cookies.get("session-id")
    if not token:
        return None
    id_user = sesi_aktif.get(token)
    if id_user is None:
        return None
    row = db.ambil_user(id_user)
    if not row:
        return None
    return User(id_user=row["id_user"], username=row["username"])

# --- Mounting Aplikasi Gradio (di path baru) ---
# Pada Gradio 6, tema dan CSS kustom diberikan di sini, bukan di gr.Blocks.
unified_app_gradio = create_unified_app()
app = gr.mount_gradio_app(
    app,
    unified_app_gradio,
    path="/gradio/analisis",
    theme=tema_modul(),
    css=CSS_SELARAS,
)


# --- Rute FastAPI ---
@app.get("/", response_class=HTMLResponse)
async def root(request: Request, user: User = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(request, "dashboard.html", {
        "user": user,
        "active_page": "dashboard",
        # Statistik dihitung dari basis data, bukan angka tempelan.
        "stat": db.statistik_user(user.id_user),
    })

@app.get("/app/{app_name}", response_class=HTMLResponse)
async def show_app(request: Request, app_name: str, user: User = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    app_map = {
        # __theme=light memaksa Gradio tampil terang. Tanpa ini Gradio
        # mengikuti preferensi sistem; pada mode gelap modul menjadi hitam
        # dan bertabrakan dengan shell aplikasi yang terang.
        "analisis": {"title": "Modul Analisis Audio", "iframe_src": "/gradio/analisis?__theme=light"},
        "histori": {"title": "Histori & Arsip", "iframe_src": "/histori-content"},
        "nilai": {"title": "Penilaian & Umpan Balik", "iframe_src": "/nilai-content"},
    }

    app_info = app_map.get(app_name)
    if not app_info:
        return HTMLResponse("Aplikasi tidak ditemukan.", status_code=404)

    return templates.TemplateResponse(request, "app_view.html", {
        "user": user,
        "title": app_info["title"],
        "iframe_src": app_info["iframe_src"],
        "active_page": app_name,
    })

# --- Rute Konten (untuk di-embed di iframe) ---
@app.get("/histori-content", response_class=HTMLResponse)
async def history_page_content(request: Request, user: User = Depends(get_current_user)):
    if not user:
        return HTMLResponse("Akses ditolak.", status_code=403)
    histori = db.ambil_histori(user.id_user)
    return templates.TemplateResponse(request, "histori.html", {"histori": histori})


@app.get("/histori-content/{id_audio}", response_class=HTMLResponse)
async def history_detail_content(request: Request, id_audio: int, user: User = Depends(get_current_user)):
    if not user:
        return HTMLResponse("Akses ditolak.", status_code=403)
    # ambil_detail_audio menyaring berdasarkan id_user, sehingga guru tidak
    # dapat membuka data guru lain dengan menebak id_audio.
    detail = db.ambil_detail_audio(id_audio, user.id_user)
    if detail is None:
        return HTMLResponse("Data tidak ditemukan.", status_code=404)
    return templates.TemplateResponse(request, "histori_detail.html", {"detail": detail})


@app.get("/nilai-content", response_class=HTMLResponse)
async def nilai_page_content(request: Request, user: User = Depends(get_current_user)):
    if not user:
        return HTMLResponse("Akses ditolak.", status_code=403)
    penilaian = db.ambil_penilaian(user.id_user)
    return templates.TemplateResponse(request, "penilaian.html", {"penilaian": penilaian})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None, success: str = None):
    return templates.TemplateResponse(request, "login.html", {"error": error, "success": success})

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, error: str = None):
    return templates.TemplateResponse(request, "register.html", {"error": error})

@app.post("/register")
async def handle_registration(request: Request, username: str = Form(""), password: str = Form(""), confirm_password: str = Form("")):
    # Nilai bawaan "" membuat form kosong sampai ke sini dan mendapat pesan
    # yang ramah, bukan galat validasi 422 berbentuk JSON mentah.
    if not username.strip() or not password:
        return templates.TemplateResponse(request, "register.html", {"error": "Username dan password wajib diisi."})

    if password != confirm_password:
        return templates.TemplateResponse(request, "register.html", {"error": "Password tidak cocok."})

    try:
        db.buat_user(username, password)
    except ValueError as e:
        return templates.TemplateResponse(request, "register.html", {"error": str(e)})

    # Redirect ke halaman login dengan pesan sukses
    return RedirectResponse(url="/login?success=Registrasi+berhasil!+Silakan+login.", status_code=303)

@app.post("/login")
async def handle_login(request: Request, username: str = Form(""), password: str = Form("")):
    if not username.strip() or not password:
        return templates.TemplateResponse(request, "login.html", {"error": "Username dan password wajib diisi."})

    id_user = db.verifikasi_user(username, password)
    if id_user is None:
        return templates.TemplateResponse(request, "login.html", {"error": "Username atau password salah."})

    # Token sesi dibuat acak. Nilai cookie tidak boleh dapat ditebak: bila
    # cookie berisi username, siapa pun dapat memalsukannya dan masuk tanpa
    # kata sandi.
    token = secrets.token_urlsafe(32)
    sesi_aktif[token] = id_user

    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(key="session-id", value=token, httponly=True, samesite="lax")
    return response

@app.post("/logout")
async def logout(request: Request):
    token = request.cookies.get("session-id")
    # Sesi dihapus dari sisi server, bukan sekadar menghapus cookie di peramban.
    sesi_aktif.pop(token, None)
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="session-id")
    return response

# Anda dapat menjalankan aplikasi ini dengan `uvicorn main:app --reload`
# Pastikan Anda telah menginstal uvicorn dan python-multipart:
# pip install uvicorn python-multipart
