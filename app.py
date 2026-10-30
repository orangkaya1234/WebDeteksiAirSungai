# ============================================================
# WebDeteksiAirSungai
# Flask + OpenCV: preprocessing, segmentasi HSV, morfologi,
# ekstraksi area air, false color, dan statistik visual.
# ============================================================
import base64
import os
from pathlib import Path
from werkzeug.utils import secure_filename

import cv2
import numpy as np
from flask import Flask, jsonify, render_template, request, send_from_directory

BASE_DIR = Path(__file__).resolve().parent
DATASET_DIR = BASE_DIR / "dataset"
UPLOAD_DIR = BASE_DIR / "uploads"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
MAX_DIM = 900

DATASET_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

COLORMAPS = {
    "COLORMAP_JET": cv2.COLORMAP_JET,
    "COLORMAP_TURBO": cv2.COLORMAP_TURBO,
    "COLORMAP_RAINBOW": cv2.COLORMAP_RAINBOW,
}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # maksimum upload 16 MB


def daftar_gambar():
    """Daftar gambar di dataset secara rekursif; folder masks ikut terbaca bila berisi gambar."""
    hasil = []
    for p in DATASET_DIR.rglob("*"):
        if p.is_file() and p.suffix.lower() in ALLOWED_EXTENSIONS:
            hasil.append(p.relative_to(DATASET_DIR).as_posix())
    return sorted(hasil)


def path_dataset_aman(rel):
    p = (DATASET_DIR / rel).resolve()
    if DATASET_DIR.resolve() not in p.parents or not p.is_file() or p.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise FileNotFoundError("Gambar tidak ditemukan di folder dataset.")
    return p


def baca_gambar(path):
    data = np.fromfile(str(path), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("File tidak dapat dibaca sebagai gambar.")
    h0, w0 = img.shape[:2]
    skala = MAX_DIM / max(h0, w0)
    if skala < 1:
        img = cv2.resize(img, (max(1, int(w0 * skala)), max(1, int(h0 * skala))),
                         interpolation=cv2.INTER_AREA)
    return img, (w0, h0)


def preprocessing(img, jenis="Gaussian Blur", ukuran=5):
    ukuran = max(1, min(31, int(ukuran)))
    if ukuran % 2 == 0:
        ukuran += 1
    if jenis == "Median Filter":
        return cv2.medianBlur(img, ukuran)
    return cv2.GaussianBlur(img, (ukuran, ukuran), 0)


def segmentasi_air(img_blur, p):
    hsv = cv2.cvtColor(img_blur, cv2.COLOR_BGR2HSV)
    bawah = np.array([p["h_min"], p["s_min"], p["v_min"]], dtype=np.uint8)
    atas = np.array([p["h_max"], p["s_max"], p["v_max"]], dtype=np.uint8)
    mask = cv2.inRange(hsv, bawah, atas)
    k = max(1, min(31, int(p["kernel"])))
    if k % 2 == 0:
        k += 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    return mask


def ekstraksi_fitur(img, mask, p):
    air = cv2.bitwise_and(img, img, mask=mask)
    mean_b, mean_g, mean_r, _ = cv2.mean(img, mask=mask)
    gray = cv2.cvtColor(air, cv2.COLOR_BGR2GRAY)

    if p["normalisasi"] and cv2.countNonZero(mask) > 0:
        nilai = gray[mask > 0]
        lo, hi = float(nilai.min()), float(nilai.max())
        if hi > lo:
            gray = np.clip((gray.astype(np.float32) - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8)

    if p["balik"]:
        gray = 255 - gray

    false = cv2.applyColorMap(gray, COLORMAPS[p["cmap"]])
    false[mask == 0] = 0
    return air, false, (mean_r, mean_g, mean_b)


def analisis_statistik(mask, rgb):
    total = int(mask.shape[0] * mask.shape[1])
    pixel_air = int(cv2.countNonZero(mask))
    r, g, b = rgb
    if pixel_air == 0:
        return {
            "persen": 0.0, "pixel_air": 0, "total": total,
            "r": 0.0, "g": 0.0, "b": 0.0, "brightness": 0.0,
            "interpretasi": "Area air tidak terdeteksi — sesuaikan rentang HSV.",
            "warna": "#64748b"
        }

    brightness = (r + g + b) / 3
    if brightness > 150:
        interpretasi, warna = "Cenderung Jernih secara visual", "#16845b"
    elif brightness >= 80:
        interpretasi, warna = "Indikasi visual Bagus", "#b7791f"
    else:
        interpretasi, warna = "Cenderung Gelap/Keruh secara visual", "#c2413b"

    return {
        "persen": pixel_air / total * 100, "pixel_air": pixel_air, "total": total,
        "r": r, "g": g, "b": b, "brightness": brightness,
        "interpretasi": interpretasi, "warna": warna
    }


def encode_image(img, ext=".jpg"):
    if ext == ".png":
        ok, buf = cv2.imencode(".png", img)
        mime = "image/png"
    else:
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        mime = "image/jpeg"
    if not ok:
        raise ValueError("Gagal mengubah hasil gambar.")
    return f"data:{mime};base64," + base64.b64encode(buf).decode("ascii")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/images")
def api_images():
    return jsonify(daftar_gambar())


@app.route("/api/upload", methods=["POST"])
def api_upload():
    f = request.files.get("file")
    if not f or Path(f.filename or "").suffix.lower() not in ALLOWED_EXTENSIONS:
        return jsonify(error="File tidak valid. Gunakan JPG, JPEG, PNG, BMP, TIFF, atau WEBP."), 400
    safe_name = secure_filename(f.filename)
    if not safe_name:
        return jsonify(error="Nama file tidak valid."), 400
    # Hindari menimpa file yang sudah ada.
    target = UPLOAD_DIR / safe_name
    stem, suffix = target.stem, target.suffix
    counter = 1
    while target.exists():
        target = UPLOAD_DIR / f"{stem}_{counter}{suffix}"
        counter += 1
    f.save(target)
    return jsonify(path=f"uploads/{target.name}", name=target.name)


@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/api/process", methods=["POST"])
def api_process():
    d = request.get_json(silent=True) or {}
    try:
        rel = d.get("image", "")
        if rel.startswith("uploads/"):
            image_path = (UPLOAD_DIR / rel.removeprefix("uploads/")).resolve()
            if UPLOAD_DIR.resolve() not in image_path.parents or not image_path.is_file():
                return jsonify(error="File upload tidak ditemukan."), 404
        else:
            image_path = path_dataset_aman(rel)

        img, (w0, h0) = baca_gambar(image_path)

        def angka(k, mx):
            return max(0, min(mx, int(d.get(k, 0))))

        p = {
            "h_min": angka("h_min", 179), "h_max": angka("h_max", 179),
            "s_min": angka("s_min", 255), "s_max": angka("s_max", 255),
            "v_min": angka("v_min", 255), "v_max": angka("v_max", 255),
            "kernel": angka("kernel", 15),
            "cmap": d.get("cmap", "COLORMAP_JET"),
            "normalisasi": bool(d.get("normalisasi", True)),
            "balik": bool(d.get("balik", True)),
        }
        if p["cmap"] not in COLORMAPS:
            return jsonify(error="Colormap tidak dikenal."), 400
        if p["h_min"] > p["h_max"] or p["s_min"] > p["s_max"] or p["v_min"] > p["v_max"]:
            return jsonify(error="Nilai MIN tidak boleh lebih besar dari MAX."), 400

        ukuran_filter = max(1, min(31, int(d.get("ukuran_filter", 5))))
        blur = preprocessing(img, d.get("filter", "Gaussian Blur"), ukuran_filter)
        mask = segmentasi_air(blur, p)
        air, false, rgb = ekstraksi_fitur(img, mask, p)
        h, w = img.shape[:2]
        stat = analisis_statistik(mask, rgb)

        return jsonify(
            asli=encode_image(img), mask=encode_image(mask, ".png"),
            air=encode_image(air), false=encode_image(false),
            info={"nama": Path(rel).name, "lebar": w, "tinggi": h,
                  "channel": 3, "asli": f"{w0} × {h0}"},
            stat=stat
        )
    except FileNotFoundError as e:
        return jsonify(error=str(e)), 404
    except Exception as e:
        app.logger.exception("Gagal memproses gambar")
        return jsonify(error=f"Gagal memproses gambar: {e}"), 500


@app.errorhandler(413)
def too_large(_):
    return jsonify(error="Ukuran file terlalu besar. Maksimum 16 MB."), 413


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
