# WebDeteksiAirSungai

Aplikasi web Flask + OpenCV untuk menjalankan pipeline dari kode Google Colab:
1. Membaca dan resize citra (maksimum sisi 900 px).
2. Preprocessing Gaussian Blur atau Median Filter.
3. Segmentasi HSV dengan `cv2.inRange`.
4. Morfologi Opening dan Closing.
5. Ekstraksi area air menggunakan `bitwise_and`.
6. Rata-rata kanal RGB pada area mask.
7. Grayscale, normalisasi opsional, inversi opsional, dan false color.
8. Statistik area terdeteksi dan interpretasi brightness.

## Menjalankan di Windows (VS Code)

Buka terminal di folder `WebDeteksiAirSungai`, lalu:

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Buka browser: http://127.0.0.1:5000

Jika perintah `python` tidak dikenali, coba gunakan `py` sebagai pengganti `python`.

## Menambahkan dataset

Salin gambar ke folder `dataset/` atau subfoldernya. Contoh:

```text
dataset/
  images/
  masks/
  test/
  validation/
```

Aplikasi mencari file gambar secara rekursif di seluruh folder `dataset/`. Jika folder `masks` berisi file gambar mask, file tersebut juga akan muncul di daftar; untuk analisis foto sungai, pilih gambar dari folder `images`, `test`, atau `validation` yang sesuai.

Alternatif: unggah foto melalui area Unggah Gambar di halaman web. File disimpan di folder `uploads/`.

## Catatan ilmiah

Label "Cenderung jernih / sedang / keruh" pada aplikasi merupakan interpretasi visual sederhana dari rata-rata brightness RGB dengan ambang yang ada di kode sumber. Ini **bukan** pengukuran kekeruhan/Turbidity (NTU), TSS, pH, BOD, COD, atau penentuan baku mutu air. Untuk menyimpulkan kualitas air sungai diperlukan kalibrasi dan validasi terhadap pengukuran lapangan/laboratorium.

## Catatan implementasi

Kode Colab memiliki typo `dataset_Sungai` pada pengecekan folder, padahal variabel yang didefinisikan adalah `DATASET_DIR`. Aplikasi web ini mengganti path Colab `/content/drive/...` menjadi folder lokal `dataset/`, dan mengganti `ipywidgets`/`files.upload()` dengan UI HTML dan endpoint Flask.
