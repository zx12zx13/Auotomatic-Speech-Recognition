import gradio as gr
from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# Impor fungsi untuk membuat aplikasi Gradio dari app.py
from app import create_unified_app

# --- Konfigurasi ---
app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Basis data pengguna "palsu" untuk menyimpan pengguna terdaftar
# Dalam aplikasi nyata, ini akan menjadi database (misalnya, SQL, MongoDB)
fake_user_db = {
    "admin": "password"  # Tambahkan pengguna admin default
}


# --- Model untuk data login ---
class User(BaseModel):
    username: str

# --- "Session" sangat sederhana ---
fake_session_db = {}

def get_current_user(request: Request):
    """Dependensi untuk memeriksa apakah pengguna sudah 'login'."""
    username = request.cookies.get("session-id")
    if username not in fake_session_db:
        return None
    return User(username=username)

# --- Mounting Aplikasi Gradio (di path baru) ---
unified_app_gradio = create_unified_app()
app = gr.mount_gradio_app(app, unified_app_gradio, path="/gradio/analisis")


# --- Rute FastAPI ---
@app.get("/", response_class=HTMLResponse)
async def root(request: Request, user: User = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user, "active_page": "dashboard"})

@app.get("/app/{app_name}", response_class=HTMLResponse)
async def show_app(request: Request, app_name: str, user: User = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    app_map = {
        "analisis": {"title": "Modul Analisis Audio", "iframe_src": "/gradio/analisis"},
        "histori": {"title": "Histori & Arsip", "iframe_src": "/histori-content"},
        "nilai": {"title": "Penilaian & Umpan Balik", "iframe_src": "/nilai-content"},
    }

    app_info = app_map.get(app_name)
    if not app_info:
        return HTMLResponse("Aplikasi tidak ditemukan.", status_code=404)

    return templates.TemplateResponse("app_view.html", {
        "request": request,
        "user": user,
        "title": app_info["title"],
        "iframe_src": app_info["iframe_src"],
        "active_page": app_name
    })

# --- Rute Konten (untuk di-embed di iframe) ---
@app.get("/histori-content", response_class=HTMLResponse)
async def history_page_content(request: Request, user: User = Depends(get_current_user)):
    if not user: return HTMLResponse("Akses ditolak.", status_code=403)
    
    # The HTML content from the previous step, but now it's served as a standalone page for the iframe
    content = """
    <!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Histori</title>
    <style>
        body { font-family: 'Roboto', sans-serif; background-color: #f4f7fc; margin: 0; padding: 2rem; }
        .container { background-color: #fff; padding: 2rem; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.07); }
        h1 { color: #102a43; margin-top: 0; margin-bottom: 1.5rem; }
        table { width: 100%; border-collapse: collapse; margin-top: 1rem; }
        th, td { border: 1px solid #e2e8f0; padding: 0.8rem 1rem; text-align: left; }
        th { background-color: #f8fafc; font-weight: 600; }
        tbody tr:nth-child(even) { background-color: #f8fafc; }
        a { color: #2a6fdb; text-decoration: none; }
        a:hover { text-decoration: underline; }
    </style></head>
    <body>
        <div class="container">
            <h1>Riwayat Pemrosesan Audio</h1>
            <table>
                <thead>
                    <tr><th>Tanggal</th><th>Nama File</th><th>Jenis Proses</th><th>Durasi</th><th>Status</th><th>Aksi</th></tr>
                </thead>
                <tbody>
                    <tr><td>2023-10-26 10:00</td><td>rapat_q3_2023.mp3</td><td>Transkripsi</td><td>45 menit</td><td>Selesai</td><td><a href="#">Lihat</a></td></tr>
                    <tr><td>2023-10-25 14:30</td><td>interview_andi.wav</td><td>Diarisasi</td><td>12 menit</td><td>Selesai</td><td><a href="#">Lihat</a></td></tr>
                    <tr><td>2023-10-24 09:15</td><td>presentasi_produk.m4a</td><td>Transkripsi</td><td>30 menit</td><td>Selesai</td><td><a href="#">Lihat</a></td></tr>
                    <tr><td>2023-10-23 11:00</td><td>diskusi_tim.ogg</td><td>Diarisasi</td><td>20 menit</td><td>Selesai</td><td><a href="#">Lihat</a></td></tr>
                </tbody>
            </table>
        </div>
    </body></html>
    """
    return HTMLResponse(content=content)

@app.get("/nilai-content", response_class=HTMLResponse)
async def nilai_page_content(request: Request, user: User = Depends(get_current_user)):
    if not user: return HTMLResponse("Akses ditolak.", status_code=403)

    content = """
    <!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Penilaian</title>
    <style>
        body { font-family: 'Roboto', sans-serif; background-color: #f4f7fc; margin: 0; padding: 2rem; }
        .container { background-color: #fff; padding: 2rem; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.07); }
        h1 { color: #102a43; margin-top: 0; margin-bottom: 1.5rem; }
        table { width: 100%; border-collapse: collapse; margin-top: 1rem; }
        th, td { border: 1px solid #e2e8f0; padding: 0.8rem 1rem; text-align: left; }
        th { background-color: #f8fafc; font-weight: 600; }
        tbody tr:nth-child(even) { background-color: #f8fafc; }
        a { color: #2a6fdb; text-decoration: none; }
        a:hover { text-decoration: underline; }
    </style></head>
    <body>
        <div class="container">
            <h1>Riwayat Penilaian Transkrip</h1>
            <table>
                <thead>
                    <tr><th>Tanggal</th><th>File Audio</th><th>Skor Akurasi</th><th>Umpan Balik</th><th>Aksi</th></tr>
                </thead>
                <tbody>
                    <tr><td>2023-10-26 11:30</td><td>rapat_q3_2023.mp3</td><td>92%</td><td>"Transkrip sangat akurat..."</td><td><a href="#">Detail</a></td></tr>
                    <tr><td>2023-10-25 15:00</td><td>interview_andi.wav</td><td>88%</td><td>"Perlu perbaikan pada..."</td><td><a href="#">Detail</a></td></tr>
                    <tr><td>2023-10-24 10:00</td><td>presentasi_produk.m4a</td><td>95%</td><td>"Hasil luar biasa..."</td><td><a href="#">Detail</a></td></tr>
                </tbody>
            </table>
        </div>
    </body></html>
    """
    return HTMLResponse(content=content)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None, success: str = None):
    return templates.TemplateResponse("login.html", {"request": request, "error": error, "success": success})

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, error: str = None):
    return templates.TemplateResponse("register.html", {"request": request, "error": error})

@app.post("/register")
async def handle_registration(request: Request, username: str = Form(...), password: str = Form(...), confirm_password: str = Form(...)):
    if password != confirm_password:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Password tidak cocok."
        })
    if username in fake_user_db:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Username sudah digunakan."
        })
    
    # Simpan pengguna baru
    fake_user_db[username] = password
    
    # Redirect ke halaman login dengan pesan sukses
    return RedirectResponse(url="/login?success=Registrasi+berhasil!+Silakan+login.", status_code=303)

@app.post("/login")
async def handle_login(request: Request, username: str = Form(...), password: str = Form(...)):
    # Periksa apakah pengguna ada di DB dan passwordnya cocok
    if username in fake_user_db and fake_user_db[username] == password:
        response = RedirectResponse(url="/", status_code=303)
        # "Session" dibuat dengan menyimpan nama pengguna di cookie
        fake_session_db[username] = True
        response.set_cookie(key="session-id", value=username, httponly=True)
        return response
    else:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Username atau password salah."
        })

@app.post("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(key="session-id")
    return response

# Anda dapat menjalankan aplikasi ini dengan `uvicorn main:app --reload`
# Pastikan Anda telah menginstal uvicorn dan python-multipart:
# pip install uvicorn python-multipart
