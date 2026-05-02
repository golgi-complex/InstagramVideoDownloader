import yt_dlp
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
from datetime import datetime
import threading
import cv2
import numpy as np
import os
import sys
import re

# ---------------- STATE ----------------
download_folder = "/home"
current_lang = "ru"

blur_strength = 50
darkness_strength = 50

timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

APP_VERSION = "2.0"
APP_YEAR = "2026"

# ---------------- TRANSLATIONS ----------------
T = {
    "ru": {
        "title": "Instagram Video Downloader",
        "input_label": "Вставьте ссылки (по одной на строку):",
        "choose_folder": "Выбрать папку",
        "download": "Скачать",
        "folder": "Папка",
        "done": "Готово",
        "success": "Все видео обработаны!",
        "warning": "Нет ссылок",
        "blur": "Размытие",
        "darkness": "Затемнение",
        "footer": "Автор: Илья Ковалёв   Минск {year}    © Все права защищены | Версия: {version}"
    },
    "en": {
        "title": "Instagram Video Downloader",
        "input_label": "Paste URLs (one per line):",
        "choose_folder": "Choose Folder",
        "download": "Download",
        "folder": "Folder",
        "done": "Done",
        "success": "All videos processed!",
        "warning": "No URLs provided",
        "blur": "Blur",
        "darkness": "Darkness",
        "footer": "Author: Illia Kavaliou   Minsk {year}    © All rights reserved | Version: {version}"
    }
}

def resource_path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

def tr(key):
    return T[current_lang][key]

# ---------------- HELPERS ----------------
def get_blur_kernel(v):
    k = int(1 + v * 0.6)
    if k % 2 == 0:
        k += 1
    return max(k, 3)

def get_dark_factor(v):
    return 1.0 - (v / 100.0) * 0.7

# ---------------- SAFE ERROR HANDLING ----------------
def fail_video(log_path, message, index, total):
    write_log(log_path, message)
    update_progress_ui((index + 1) * (100 / total))

# ---------------- CLEAN LOGS ----------------
def clean_log_text(text):
    ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
    return ansi_escape.sub('', str(text))

# ---------------- PROGRESS UI ----------------
def update_progress_ui(value):
    value = max(0, min(100, value))
    progress_var.set(value)
    progress_label.config(text=f"{int(value)}%")
    root.update_idletasks()

# ---------------- LOGGING ----------------
def write_log(log_path, message):
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(message + "\n")

# ---------------- PASTE CLIPBOARD ----------------
def paste(event=None):
    try:
        text_box.insert(tk.INSERT, root.clipboard_get())
    except tk.TclError:
        pass
    return "break"

def show_context_menu(event):
    menu = tk.Menu(root, tearoff=0)
    menu.add_command(label="Вставить", command=paste)
    menu.tk_popup(event.x_root, event.y_root)

# ---------------- VIDEO PROCESSING ----------------
def process_video(input_path, output_path, progress_cb=None):
    OUT_W, OUT_H = 1920, 1080

    cap = cv2.VideoCapture(input_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output_path, fourcc, fps, (OUT_W, OUT_H))

    i = 0

    blur_val = blur_slider.get()
    dark_val = dark_slider.get()

    blur_k = get_blur_kernel(blur_val)
    dark_f = get_dark_factor(dark_val)

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        h, w = frame.shape[:2]

        scale = OUT_W / w
        bg_w = int(w * scale)
        bg_h = int(h * scale)

        bg = cv2.resize(frame, (bg_w, bg_h))
        y1 = (bg_h - OUT_H) // 2
        bg = bg[y1:y1 + OUT_H, 0:OUT_W]

        bg = cv2.GaussianBlur(bg, (blur_k, blur_k), 0)
        bg = (bg * dark_f).astype(np.uint8)

        scale_fg = min(OUT_W / w, OUT_H / h)
        fg_w = int(w * scale_fg)
        fg_h = int(h * scale_fg)

        fg = cv2.resize(frame, (fg_w, fg_h))

        x = (OUT_W - fg_w) // 2
        y = (OUT_H - fg_h) // 2

        bg[y:y+fg_h, x:x+fg_w] = fg
        out.write(bg)

        i += 1
        if progress_cb:
            progress_cb(i / total_frames * 50 + 50)

    cap.release()
    out.release()

# ---------------- VIDEO DOWNLOAD ----------------
def download_with_fallback(url):
    def hook(d):
        if d['status'] == 'downloading':
            if d.get('total_bytes'):
                p = d['downloaded_bytes'] / d['total_bytes'] * 50
            elif d.get('total_bytes_estimate'):
                p = d['downloaded_bytes'] / d['total_bytes_estimate'] * 50
            else:
                p = 0
            update_progress_ui(p)

        if d['status'] == 'finished':
            update_progress_ui(50)

    opts = {
        "format": "best",
        "outtmpl": f"{download_folder}/%(title)s.%(ext)s",
        "progress_hooks": [hook],
        "cookiesfrombrowser": ("chrome",),
        "retries": 5,
        "sleep_interval": 2,
    }

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)

# ---------------- MAIN PIPELINE ----------------
def download_video(url, index, total):
    try:
        safe_name = url.split("/")[-1].split("?")[0]
        log_path = os.path.join(download_folder, f"{safe_name}-log_{timestamp}.txt")

        write_log(log_path, f"URL: {url}")
        write_log(log_path, "START PROCESS")

        update_progress_ui(index * (100 / total))

        file_path = download_with_fallback(url)

        if not file_path or not os.path.exists(file_path):
            fail_video(log_path, "ERROR: file not downloaded", index, total)
            return
        
        write_log(log_path, "Download OK")
        
        name, ext = os.path.splitext(os.path.basename(file_path))
        output_path = os.path.join(download_folder, f"{name}_horizontal_{timestamp}{ext}")

        def cb(p):
            global_percent = index * (100 / total) + (p * (100 / total) / 100)
            update_progress_ui(global_percent)

        process_video(file_path, output_path, cb)
        
        write_log(log_path, "Processing OK")

        try:
            os.remove(file_path)
        except:
            pass

        update_progress_ui((index + 1) * (100 / total))

        write_log(log_path, "SUCCESS")

        try:
            os.remove(log_path)
        except:
            pass

    except Exception as e:
        fail_video(log_path, f"DOWNLOAD ERROR: {clean_log_text(e)}", index, total)
        return
    
    finally:
        update_progress_ui((index + 1) * (100 / total))

# ---------------- START ----------------
def start_download():
    urls = [u for u in text_box.get("1.0", tk.END).splitlines() if u.strip()]

    if not urls:
        messagebox.showwarning("Warning", tr("warning"))
        return

    def run():
        total = len(urls)
        update_progress_ui(0)

        for i, url in enumerate(urls):
            download_video(url, i, total)

        update_progress_ui(100)
        messagebox.showinfo(tr("done"), tr("success"))

    threading.Thread(target=run, daemon=True).start()

# ---------------- FOLDER ----------------
def select_folder():
    global download_folder
    folder = filedialog.askdirectory()
    if folder:
        download_folder = folder
        folder_label.config(text=f"{tr('folder')}: {download_folder}")

# ---------------- LANGUAGE ----------------
def switch_language():
    global current_lang
    current_lang = "en" if current_lang == "ru" else "ru"
    update_ui()

# ---------------- UI ----------------
root = tk.Tk()
root.geometry("640x480")
root.minsize(640, 480)

# --- MAIN LAYOUT ---
root.grid_columnconfigure(0, weight=1)

root.grid_rowconfigure(0, weight=0)  # header top
root.grid_rowconfigure(1, weight=0)  # header mid
root.grid_rowconfigure(2, weight=1)  # text box
root.grid_rowconfigure(3, weight=0)  # folder btn
root.grid_rowconfigure(4, weight=0)  # folder label
root.grid_rowconfigure(5, weight=0)  # progress
root.grid_rowconfigure(6, weight=0)  # download btn
root.grid_rowconfigure(7, weight=0)  # sliders

style = ttk.Style(root)
style.theme_use("clam")

style.configure(
    "green.Horizontal.TProgressbar",
    troughcolor="#b8b8b8",
    background="#7CFC00",
    lightcolor="#7CFC00",
    darkcolor="#7CFC00"
)

# ---------------- SLIDERS FRAME ----------------
sliders_frame = tk.Frame(root)
sliders_frame.grid(row=5, column=0, sticky="ew", padx=10, pady=20)

sliders_frame.grid_columnconfigure(0, weight=1)
sliders_frame.grid_columnconfigure(1, weight=1)

# ---------------- LABELS ----------------
blur_label = tk.Label(sliders_frame, anchor="center")
blur_label.grid(row=0, column=0, pady=(0, 2))

dark_label = tk.Label(sliders_frame, anchor="center")
dark_label.grid(row=0, column=1, pady=(0, 2))

# ---------------- BLUR ----------------
blur_slider = tk.Scale(
    sliders_frame,
    from_=0,
    to=100,
    orient="horizontal"
)
blur_slider.set(50)
blur_slider.grid(row=1, column=0, sticky="ew", padx=10)

# ---------------- DARKNESS ----------------
dark_slider = tk.Scale(
    sliders_frame,
    from_=0,
    to=100,
    orient="horizontal"
)
dark_slider.set(50)
dark_slider.grid(row=1, column=1, sticky="ew", padx=10)


# ---------------- PROGRESSBAR ----------------
progress_var = tk.DoubleVar()

progress_frame = tk.Frame(root)
progress_frame.grid(row=7, column=0, sticky="ew", padx=20, pady=10)
progress_frame.grid_columnconfigure(0, weight=1)

progress = ttk.Progressbar(progress_frame, variable=progress_var, maximum=100, style="green.Horizontal.TProgressbar")
progress.grid(row=0, column=0, sticky="ew")


progress_label = tk.Label(progress_frame, text="0%")
progress_label.place(relx=0.5, rely=0.5, anchor="center")

#-------------FOOTER FRAME----------------
footer_frame = tk.Frame(root)
footer_frame.grid(row=8, column=0, sticky="ew")

footer_label = tk.Label(
    footer_frame,
    font=("Arial", 8),
    fg="gray"
)
footer_label.pack()

# ---------------- UI CONTINUES ----------------
app_icon = tk.PhotoImage(file=resource_path("icon.png")).subsample(3, 3)
ru_img = tk.PhotoImage(file=resource_path("russia-flag-icon.png")).subsample(3, 3)
en_img = tk.PhotoImage(file=resource_path("united-kingdom-flag-icon.png")).subsample(3, 3)

header_top = tk.Frame(root)
header_top.grid(row=0, column=0, sticky="ew", padx=10, pady=(5, 0))
header_top.grid_columnconfigure(1, weight=1)

tk.Label(header_top, image=app_icon).grid(row=0, column=0, sticky="w")

lang_btn = tk.Button(header_top, command=switch_language, borderwidth=0)
lang_btn.grid(row=0, column=1, sticky="e")

header_mid = tk.Frame(root)
header_mid.grid(row=1, column=0, sticky="ew")
header_mid.grid_columnconfigure(0, weight=1)

label = tk.Label(header_mid, anchor="center")
label.grid(row=0, column=0, sticky="ew")

text_box = tk.Text(root, height=8)
text_box.grid(row=2, column=0, sticky="nsew", padx=10)
text_box.bind("<Button-3>", show_context_menu)   # Linux / Windows
text_box.bind("<Button-2>", show_context_menu)   # macOS / something Linux

btn_folder = tk.Button(root, command=select_folder)
btn_folder.grid(row=3, column=0, pady=5)

folder_label = tk.Label(root)
folder_label.grid(row=4, column=0)

btn_download = tk.Button(
    root,
    command=start_download,
    bg="#e53935",
    fg="white",
    font=("Arial", 11, "bold")
)
btn_download.grid(row=6, column=0, pady=5, ipady=3)

def update_ui():
    root.title(tr("title"))
    label.config(text=tr("input_label"))
    btn_folder.config(text=tr("choose_folder"))
    btn_download.config(text=tr("download").upper())
    folder_label.config(text=f"{tr('folder')}: {download_folder}")
    lang_btn.config(image=en_img if current_lang == "ru" else ru_img)
    blur_label.config(text=tr("blur"))
    dark_label.config(text=tr("darkness"))
    text_box.config(undo=True)

    footer_label.config(
    text=tr("footer").format(
        year=APP_YEAR,
        version=APP_VERSION)    
    )

update_ui()

root.mainloop()
