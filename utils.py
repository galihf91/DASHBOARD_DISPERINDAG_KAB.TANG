# utils.py
"""
Kumpulan fungsi utilitas untuk proyek:
- Dashboard Harga Barang & Prediksi
- Data: harga komoditas per pasar (tanggal, komoditas, pasar, harga)

Dipakai di app.py dengan:
    from utils import (
        clean_commodity_name,
        normalize_market_name,
        prepare_price_dataframe,
        format_rupiah,
        categorize_commodity,
        get_category_color,
    )
"""

from typing import Optional
import pandas as pd


# ---------------------------------------------------------
# 1. Pembersihan & standarisasi komoditas / pasar
# ---------------------------------------------------------

def clean_commodity_name(name: str) -> str:
    """
    Standarisasi nama komoditas berdasarkan mapping yang sudah disepakati.
    Contoh:
        CURAH -> MINYAK GORENG CURAH
        KEMASAN -> MINYAK GORENG KEMASAN
        MERAH BESAR -> CABE MERAH BESAR
        MERAH KERITING -> CABE MERAH KERITING
        MINYAK KITA -> MINYAK GORENG MINYAK KITA
        RAWIT HIJAU -> CABE RAWIT HIJAU
        RAWIT MERAH -> CABE RAWIT MERAH
        SEGITIGA BIRU (KW MEDIUM) -> TEPUNG SEGITIGA BIRU (KW MEDIUM)
    """
    if name is None:
        return ""

    raw = str(name).strip().upper()

    mapping = {
        "CURAH": "MINYAK GORENG CURAH",
        "KEMASAN": "MINYAK GORENG KEMASAN",
        "MERAH BESAR": "CABE MERAH BESAR",
        "MERAH KERITING": "CABE MERAH KERITING",
        "MINYAK KITA": "MINYAK GORENG MINYAK KITA",
        "RAWIT HIJAU": "CABE RAWIT HIJAU",
        "RAWIT MERAH": "CABE RAWIT MERAH",
        "SEGITIGA BIRU (KW MEDIUM)": "TEPUNG SEGITIGA BIRU (KW MEDIUM)",
    }

    return mapping.get(raw, raw)


def normalize_market_name(pasar: str) -> str:
    """
    Standarisasi nama pasar.
    Misal variasi:
        'PASAR CISOKA', 'CISOKA ' -> 'CISOKA'
        'PASAR SEPATAN', 'SEPATAN ' -> 'SEPATAN'
    Kalau tidak dikenali, dikembalikan dalam bentuk uppercase strip.
    """
    if pasar is None:
        return ""

    raw = str(pasar).strip().upper()

    mapping = {
        "PASAR CISOKA": "CISOKA",
        "CISOKA": "CISOKA",
        "PASAR SEPATAN": "SEPATAN",
        "SEPATAN": "SEPATAN",
    }

    return mapping.get(raw, raw)


def prepare_price_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Membersihkan dan menyiapkan dataframe harga.
    Diasumsikan struktur long:
        kolom minimal: ['tanggal', 'komoditas', 'pasar', 'harga']
    Fungsi ini akan:
    - Menormalkan nama kolom (lowercase)
    - Konversi tanggal ke datetime
    - Uppercase & standarisasi nama komoditas & pasar
    - Drop baris tanpa tanggal / harga
    - Sort berdasarkan tanggal, komoditas, pasar
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=["tanggal", "komoditas", "pasar", "harga"])

    # Normalisasi nama kolom ke lowercase
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]

    # Coba mapping beberapa kemungkinan nama kolom
    col_map = {}
    if "tanggal" in df.columns:
        col_map["tanggal"] = "tanggal"
    elif "tgl" in df.columns:
        col_map["tgl"] = "tanggal"

    if "komoditas" in df.columns:
        col_map["komoditas"] = "komoditas"
    elif "komoditi" in df.columns:
        col_map["komoditi"] = "komoditas"

    if "pasar" in df.columns:
        col_map["pasar"] = "pasar"

    if "harga" in df.columns:
        col_map["harga"] = "harga"

    df = df.rename(columns=col_map)

    required = {"tanggal", "komoditas", "pasar", "harga"}
    missing = required - set(df.columns)
    if missing:
        # Kalau ada kolom wajib yang hilang, kembalikan df kosong
        return pd.DataFrame(columns=["tanggal", "komoditas", "pasar", "harga"])

    # Konversi tanggal
    df["tanggal"] = pd.to_datetime(df["tanggal"], errors="coerce")

    # Standarisasi komoditas & pasar
    df["komoditas"] = (
        df["komoditas"]
        .astype(str)
        .str.strip()
        .str.upper()
        .apply(clean_commodity_name)
    )
    df["pasar"] = (
        df["pasar"]
        .astype(str)
        .str.strip()
        .str.upper()
        .apply(normalize_market_name)
    )

    # Harga numeric
    df["harga"] = pd.to_numeric(df["harga"], errors="coerce")

    # Drop baris tidak valid
    df = df.dropna(subset=["tanggal", "harga"])

    # Sort
    df = df.sort_values(["tanggal", "komoditas", "pasar"]).reset_index(drop=True)

    return df[["tanggal", "komoditas", "pasar", "harga"]]


# ---------------------------------------------------------
# 2. Format tampilan (Rupiah, kategori, warna)
# ---------------------------------------------------------

def format_rupiah(value: Optional[float]) -> str:
    """
    Format angka menjadi teks Rupiah:
        29625 -> 'Rp 29.625'
    Jika None atau NaN, dikembalikan '-'.
    """
    if value is None:
        return "-"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"Rp {v:,.0f}"


def categorize_commodity(komoditas: str) -> str:
    """
    Mengelompokkan komoditas ke kategori besar untuk keperluan warna / badge.
    Contoh kategori:
      - 'BERAS'
      - 'MINYAK GORENG'
      - 'CABAI'
      - 'BAWANG'
      - 'GULA'
      - 'TELUR'
      - 'LAINNYA'
    """
    if komoditas is None:
        return "LAINNYA"

    name = str(komoditas).upper()

    if "BERAS" in name:
        return "BERAS"
    if "MINYAK" in name:
        return "MINYAK GORENG"
    if "CABAI" in name or "CABE" in name or "RAWIT" in name:
        return "CABAI"
    if "BAWANG" in name:
        return "BAWANG"
    if "GULA" in name:
        return "GULA"
    if "TELUR" in name:
        return "TELUR"
    if "AYAM" in name or "DAGING" in name:
        return "PROTEIN HEWANI"
    if "TEPUNG" in name:
        return "TEPUNG"
    return "LAINNYA"


def get_category_color(category_or_komoditas: str) -> str:
    """
    Mengembalikan kode warna (hex) untuk kategori tertentu.
    Bisa diberi input kategori langsung ('BERAS', 'CABAI', ...) atau langsung nama komoditas.
    """
    if category_or_komoditas is None:
        return "#3949AB"

    # Jika yang masuk ternyata nama komoditas, kategorikan dulu
    cat = categorize_commodity(category_or_komoditas)

    color_map = {
        "BERAS": "#1E88E5",
        "MINYAK GORENG": "#F9A825",
        "CABAI": "#E53935",
        "BAWANG": "#8E24AA",
        "GULA": "#6D4C41",
        "TELUR": "#FB8C00",
        "PROTEIN HEWANI": "#5E35B1",
        "TEPUNG": "#00897B",
        "LAINNYA": "#3949AB",
    }

    return color_map.get(cat, "#3949AB")

def kebijakan_saran(df_hist, df_pred, horizon_analisis: int = 7) -> str:
    import numpy as np

    if df_hist is None or df_hist.empty or df_pred is None or df_pred.empty:
        return (
            "Data historis atau data prediksi belum tersedia sehingga "
            "belum dapat disusun saran kebijakan yang spesifik."
        )

    df_hist = df_hist.sort_values("tanggal").copy()
    df_pred = df_pred.sort_values("tanggal").copy()

    komoditas = df_hist["komoditas"].iloc[-1] if "komoditas" in df_hist.columns else "-"
    pasar = df_hist["pasar"].iloc[-1] if "pasar" in df_hist.columns else "-"

    last_actual = float(df_hist["harga"].iloc[-1])
    if last_actual <= 0:
        last_actual = max(float(df_hist["harga"].tail(7).mean()), 1.0)

    h = min(horizon_analisis, len(df_pred))
    next_pred = df_pred["prediksi"].head(h).astype(float).values
    mean_pred = float(np.mean(next_pred))
    last_pred_h = float(next_pred[-1])

    change_mean = (mean_pred - last_actual) / last_actual * 100.0
    change_last = (last_pred_h - last_actual) / last_actual * 100.0

    # slope: tren naik/turun dalam horizon (lebih robust dari cuma mean)
    x = np.arange(len(next_pred), dtype=float)
    slope = float(np.polyfit(x, next_pred, 1)[0]) if len(next_pred) >= 2 else 0.0
    slope_pct_per_day = (slope / last_actual * 100.0) if last_actual > 0 else 0.0

    # volatilitas prediksi: std perubahan % harian
    if len(next_pred) >= 2:
        pct_changes = np.diff(next_pred) / np.maximum(next_pred[:-1], 1.0) * 100.0
        volatility = float(np.std(pct_changes))
    else:
        volatility = 0.0

    # ===== KLASIFIKASI TREN (lebih halus) =====
    # gunakan gabungan mean + last + slope
    score = 0.0
    score += change_mean * 0.5
    score += change_last * 0.3
    score += slope_pct_per_day * 0.2

    if score >= 12:
        tren = "naik tajam"
    elif score >= 6:
        tren = "cenderung naik"
    elif score >= 2:
        tren = "naik ringan"
    elif score <= -12:
        tren = "turun tajam"
    elif score <= -6:
        tren = "cenderung turun"
    elif score <= -2:
        tren = "turun ringan"
    else:
        tren = "relatif stabil"

    # ===== KLASIFIKASI VOLATILITAS =====
    if volatility >= 8:
        vol_text = "sangat bergejolak"
    elif volatility >= 4:
        vol_text = "cukup bergejolak"
    else:
        vol_text = "relatif stabil"

    def fmt_rp(x: float) -> str:
        return f"Rp {x:,.0f}"

    teks = []
    teks.append(f"**Ringkasan Prediksi Harga {komoditas} – Pasar {pasar}**")
    teks.append(f"- Harga aktual terakhir: **{fmt_rp(last_actual)}**")
    teks.append(f"- Rata-rata prediksi {h} hari: **{fmt_rp(mean_pred)}** ({change_mean:+.1f}%)")
    teks.append(f"- Prediksi hari ke-{h}: **{fmt_rp(last_pred_h)}** ({change_last:+.1f}%)")
    teks.append(f"- Tren: **{tren}** | Volatilitas: **{vol_text}** (±{volatility:.1f}%/hari)")
    teks.append("")

    teks.append("**Implikasi Kebijakan yang Disarankan:**")

    # ===== REKOMENDASI (lebih nyambung dengan tren naik ringan) =====
    if tren in ["naik tajam", "cenderung naik"]:
        teks.append("- **Penguatan pasokan cepat:** koordinasi pemasok/gapoktan untuk menambah suplai 3–7 hari ke depan.")
        teks.append("- **Pantau potensi spekulasi:** cek stok pedagang besar, pastikan tidak ada penahanan barang.")
        teks.append("- **Publikasi harga referensi:** perkuat informasi harga agar kenaikan tidak berlebihan.")
        if vol_text != "relatif stabil":
            teks.append("- **Pantau harian:** karena harga bergejolak, lakukan monitoring lebih sering & siapkan opsi intervensi.")
    elif tren == "naik ringan":
        # ini yang memperbaiki kasus kamu
        teks.append("- **Antisipasi dini:** kenaikan masih ringan, namun disarankan memastikan pasokan lancar (hindari kekosongan stok).")
        teks.append("- **Monitoring lebih rapat:** cek konsistensi kenaikan 3–7 hari ke depan sebelum intervensi besar.")
        teks.append("- **Komunikasi ke pedagang:** ingatkan harga wajar & transparansi informasi agar kenaikan tidak berkembang jadi lonjakan.")
        if vol_text != "relatif stabil":
            teks.append("- **Waspadai lonjakan mendadak:** karena prediksi bergejolak, siapkan skenario operasi pasar bila diperlukan.")
    elif tren in ["turun tajam", "cenderung turun"]:
        teks.append("- **Evaluasi kualitas & serapan:** pastikan penurunan bukan karena kualitas menurun atau pasokan tidak terserap.")
        teks.append("- **Stabilisasi pelaku usaha:** bila jatuh tajam, pertimbangkan promosi pasar / kerja sama penyaluran / penguatan permintaan.")
        if vol_text != "relatif stabil":
            teks.append("- **Pantau harian:** fluktuasi tinggi bisa memicu harga kembali naik mendadak.")
    elif tren == "turun ringan":
        teks.append("- **Normalisasi ringan:** penurunan masih wajar, fokus pada menjaga kualitas & kelancaran distribusi.")
        teks.append("- **Monitoring rutin:** pastikan penurunan tidak berlanjut menjadi anjlok tajam.")
    else:  # stabil
        teks.append("- **Pertahankan pola distribusi:** harga relatif stabil, cukup monitoring rutin.")
        teks.append("- **Jaga kualitas & kontinuitas pasokan** agar stabilitas terjaga.")
        if vol_text != "relatif stabil":
            teks.append("- **Meski rata-rata stabil, fluktuasi tinggi:** lakukan pemantauan lebih sering untuk antisipasi lonjakan.")

    return "\n".join(teks)

