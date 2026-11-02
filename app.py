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


def segmentasi_air(img_blur_bgr, p):
    hsv = cv2.cvtColor(img_blur_bgr, cv2.COLOR_BGR2HSV)

    bawah = np.array([
        p["h_min"], p["s_min"], p["v_min"]
    ], dtype=np.uint8)

    atas = np.array([
        p["h_max"], p["s_max"], p["v_max"]
    ], dtype=np.uint8)

    mask = cv2.inRange(hsv, bawah, atas)

    # Menghilangkan area bagian atas gambar (40%)
    h, w = mask.shape
    mask[0:int(h * 0.4), :] = 0

    k_open = max(1, min(31, int(p["k_open"])))
    k_close = max(1, min(31, int(p["k_close"])))

    if k_open % 2 == 0:
        k_open += 1

    if k_close % 2 == 0:
        k_close += 1

    kernel_open = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (k_open, k_open)
    )

    kernel_close = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (k_close, k_close)
    )

    mask = cv2.morphologyEx(
        mask, cv2.MORPH_OPEN, kernel_open
    )

    mask = cv2.morphologyEx(
        mask, cv2.MORPH_CLOSE, kernel_close
    )

    return mask


def ekstraksi_fitur(img, mask, p):
    air = cv2.bitwise_and(img, img, mask=mask)

    mean_b, mean_g, mean_r, _ = cv2.mean(img, mask=mask)

    gray = cv2.cvtColor(air, cv2.COLOR_BGR2GRAY)

    if p["normalisasi"] and cv2.countNonZero(mask) > 0:
        nilai = gray[mask > 0]

        if nilai.size > 0:
            lo, hi = np.percentile(
                nilai.astype(np.float32), [2, 98]
            )

            if hi > lo:
                gray = np.clip(
                    (gray.astype(np.float32) - lo) / (hi - lo) * 255,
                    0, 255
                ).astype(np.uint8)

    if p["balik"]:
        gray = 255 - gray

    false = cv2.applyColorMap(gray, COLORMAPS[p["cmap"]])
    false[mask == 0] = 0

    return air, false, (mean_r, mean_g, mean_b)

def deteksi_objek(img, mask):
    hasil = img.copy()

    kontur, _ = cv2.findContours(
        mask.copy(),
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    jumlah_objek = 0

    for c in kontur:
        if cv2.contourArea(c) > 20:

            # Kontur kuning
            cv2.drawContours(
                hasil, [c], -1, (0, 255, 255), 2
            )

            # Bounding box merah
            x, y, w, h = cv2.boundingRect(c)

            cv2.rectangle(
                hasil,
                (x, y),
                (x + w, y + h),
                (0, 0, 255),
                2
            )

            jumlah_objek += 1

    return hasil, jumlah_objek


def analisis_statistik(img, mask):
    total_pixel = mask.shape[0] * mask.shape[1]
    pixel_air = cv2.countNonZero(mask)

    persen = (pixel_air / total_pixel) * 100 if total_pixel else 0

    if pixel_air > 0:
        mean_b, mean_g, mean_r, _ = cv2.mean(img, mask=mask)

        brightness = (mean_r + mean_g + mean_b) / 3

        if brightness > 150:
            interpretasi = "Cenderung Jernih"
        elif brightness >= 80:
            interpretasi = "Cenderung Sedang"
        else:
            interpretasi = "Cenderung Keruh"
    else:
        mean_r = mean_g = mean_b = brightness = 0
        interpretasi = "Area air tidak terdeteksi"

    return {
        "persen": round(persen, 2),
        "pixel_air": pixel_air,
        "total": total_pixel,
        "r": round(mean_r, 2),
        "g": round(mean_g, 2),
        "b": round(mean_b, 2),
        "brightness": round(brightness, 2),
        "interpretasi": interpretasi
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
            image_path = (
                UPLOAD_DIR / rel.removeprefix("uploads/")
            ).resolve()

            if UPLOAD_DIR.resolve() not in image_path.parents or not image_path.is_file():
                return jsonify(error="File upload tidak ditemukan."), 404
        else:
            image_path = path_dataset_aman(rel)

        img, (w0, h0) = baca_gambar(image_path)

        def angka(k, mx):
            return max(0, min(mx, int(d.get(k, 0))))

        # Parameter segmentasi
        p = {
            "h_min": angka("h_min", 179),
            "h_max": angka("h_max", 179),

            "s_min": angka("s_min", 255),
            "s_max": angka("s_max", 255),

            "v_min": angka("v_min", 255),
            "v_max": angka("v_max", 255),

            "k_open": angka("k_open", 7),
            "k_close": angka("k_close", 9),

            "cmap": d.get("cmap", "COLORMAP_JET"),

            "normalisasi": bool(d.get("normalisasi", True)),
            "balik": bool(d.get("balik", True))
        }

        # Validasi parameter
        if p["cmap"] not in COLORMAPS:
            return jsonify(error="Colormap tidak dikenal."), 400

        if (
            p["h_min"] > p["h_max"]
            or p["s_min"] > p["s_max"]
            or p["v_min"] > p["v_max"]
        ):
            return jsonify(error="Nilai MIN tidak boleh lebih besar dari MAX."), 400

        # Preprocessing
        ukuran_filter = max(
            1, min(31, int(d.get("ukuran_filter", 5)))
        )

        blur = preprocessing(
            img,
            d.get("filter", "Gaussian Blur"),
            ukuran_filter
        )

        # Segmentasi HSV dan morfologi
        mask = segmentasi_air(blur, p)

        # Ekstraksi fitur
        air, false, rgb = ekstraksi_fitur(img, mask, p)

        # Deteksi objek
        hasil_deteksi, jumlah_objek = deteksi_objek(img, mask)

        # Analisis statistik
        stat = analisis_statistik(img, mask)

        h, w = img.shape[:2]

        # Mengirim hasil ke website
        return jsonify(
            asli=encode_image(img),
            mask=encode_image(mask, ".png"),
            air=encode_image(air),
            false=encode_image(false),
            deteksi=encode_image(hasil_deteksi),

            info={
                "nama": Path(rel).name,
                "lebar": w,
                "tinggi": h,
                "channel": 3,
                "asli": f"{w0} × {h0}"
            },

            stat=stat,
            jumlah_objek=jumlah_objek
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
