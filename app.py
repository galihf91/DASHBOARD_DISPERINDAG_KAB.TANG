# ===============================================
# APLIKASI TERPADU DINAS PERINDUSTRIAN & PERDAGANGAN
# Kabupaten Tangerang – Bidang Kemetrologian & Perdagangan
# ===============================================

import streamlit as st
import pandas as pd
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
import re
import numpy as np
import json
import glob
import base64
import os
from io import StringIO
from datetime import datetime
from pathlib import Path

# --- MODUL PERDAGANGAN (impor dari file terpisah) ---
from utils import prepare_price_dataframe, kebijakan_saran
from models_lstm import load_artifacts, forecast_lstm

# ===============================================
# KONFIGURASI HALAMAN (WAJIB PALING ATAS)
# ===============================================
st.set_page_config(
    page_title="Dinas Perindustrian & Perdagangan Kab. Tangerang",
    page_icon="🏛️",
    layout="wide"
)

# ===============================================
# KONSTANTA GLOBAL
# ===============================================
# Metrologi
FILE_EXCEL = "DATA_DASHBOARD_PASAR.xlsx"
FILE_GEOJSON = "batas_kecamatan_tangerang.geojson"
FILE_SPBU = "Data SPBU Kab. Tangerang.csv"

# Perdagangan
ARTIFACT_WINDOW_SIZE = 30
FORECAST_DAYS_DEFAULT = 30

# ===============================================
# FUNGSI UTILITAS UMUM
# ===============================================

def get_base64_of_image(image_path: str) -> str:
    """Konversi gambar lokal ke base64 untuk CSS background."""
    img_path = Path(image_path)
    if not img_path.exists():
        return ""
    with open(img_path, "rb") as f:
        data = f.read()
    return base64.b64encode(data).decode("utf-8")

def render_page_header(title: str, subtitle: str, image_path="assets/background_header.jpeg"):
    """Header seragam untuk semua halaman (gradient + background foto)."""
    img_b64 = get_base64_of_image(image_path)
    mime = "image/png" if image_path.lower().endswith(".png") else "image/jpeg"

    if img_b64:
        st.markdown(f"""
        <style>
        .main-header {{
            width: 100%; height: 260px;
            background-image: linear-gradient(rgba(0,0,0,0.5), rgba(0,0,0,0.5)), url("data:{mime};base64,{img_b64}");
            background-size: cover; background-position: center 30%; background-repeat: no-repeat;
            border-radius: 16px; margin-bottom: 30px; display: flex; flex-direction: column;
            justify-content: center; align-items: center; text-align: center;
            box-shadow: 0 8px 20px rgba(0,0,0,0.2);
        }}
        .main-header h1 {{ color: white; font-size: 38px; font-weight: 700; text-shadow: 2px 2px 8px black; padding: 0 20px; }}
        .main-header p {{ color: rgba(255,255,255,0.95); font-size: 18px; text-shadow: 1px 1px 4px black; padding: 0 20px; }}
        </style>
        <div class="main-header"><h1>{title}</h1><p>{subtitle}</p></div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="background: linear-gradient(90deg, #4B0082, #8000FF); padding: 30px 25px; border-radius: 16px;
                    margin-bottom: 30px; text-align: center; box-shadow: 0 8px 16px rgba(0,0,0,0.15);">
            <h1 style="color: white; font-size: 32px;">{title}</h1>
            <p style="color: rgba(255,255,255,0.9); font-size: 18px;">{subtitle}</p>
        </div>
        """, unsafe_allow_html=True)

# Sembunyikan menu dan footer default Streamlit
hide_streamlit_style = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# ----- Fungsi bantu metrologi -----
def _norm(s):
    return re.sub(r"[^a-z0-9]+", "", str(s).strip().lower())

def parse_coord(val):
    try:
        if pd.isna(val) or val == "":
            return np.nan, np.nan
        s = str(val).strip()
        if ',' in s:
            lat, lon = map(float, s.split(',')[:2])
            if abs(lat) > 90:
                lat, lon = lon, lat
            return lat, lon
        nums = re.findall(r"-?\d+(?:\.\d+)?", s)
        if len(nums) >= 2:
            lat, lon = map(float, nums[:2])
            if abs(lat) > 90:
                lat, lon = lon, lat
            return lat, lon
    except:
        pass
    return np.nan, np.nan

def uniq(series, clean=False):
    s = series.dropna().astype(str).str.strip()
    if clean:
        s = s.str.title()
    s = s[~s.str.lower().isin(["", "nan", "none", "null", "na", "n/a", "-", "--"])]
    return sorted(s.unique())

def marker_color(year, selected_year):
    if year is None or year == 0:
        return "gray"
    if year == selected_year:
        return "green"
    if year == selected_year - 1:
        return "orange"
    return "red"

# ----- Fungsi load data metrologi (cache) -----
@st.cache_data
def load_excel(path_like):
    """
    Membaca file Excel data pasar.
    Mengembalikan pandas DataFrame (tidak pernah mengembalikan tuple).
    Jika gagal, mengembalikan DataFrame contoh.
    """
    # Cek keberadaan file
    if not os.path.exists(path_like):
        st.warning(f"⚠️ File {path_like} tidak ditemukan. Menggunakan data sampel.")
        return _get_sample_pasar_data()

    try:
        # Coba baca dengan engine yang umum
        df = pd.read_excel(path_like, engine="openpyxl")
    except ImportError:
        # openpyxl belum terinstal
        st.error("❌ Modul 'openpyxl' tidak ditemukan. Instal dengan: pip install openpyxl")
        return _get_sample_pasar_data()
    except Exception as e:
        st.warning(f"⚠️ Gagal membaca file Excel: {e}. Menggunakan data sampel.")
        return _get_sample_pasar_data()

    # Proses normal
    df.columns = [c.strip() for c in df.columns]

    rename = {
        'Nama Pasar': 'nama_pasar',
        'Alamat': 'alamat',
        'Kecamatan': 'kecamatan',
        'Koordinat': 'koordinat',
        'Tahun Tera Ulang': 'tera_ulang_tahun',
        'Total UTTP': 'jumlah_timbangan_tera_ulang',
        'Total Pedagang': 'total_pedagang'
    }
    df.rename(columns={k: v for k, v in rename.items() if k in df.columns}, inplace=True)

    if 'koordinat' in df.columns:
        coords = df['koordinat'].apply(parse_coord)
        df['lat'] = pd.to_numeric(coords.apply(lambda x: x[0]), errors='coerce')
        df['lon'] = pd.to_numeric(coords.apply(lambda x: x[1]), errors='coerce')

    for col in ['nama_pasar', 'alamat', 'kecamatan']:
        if col in df.columns:
            df[col] = df[col].fillna('').astype(str).str.strip()

    if 'kecamatan' in df.columns:
        df['kec_norm'] = df['kecamatan'].apply(_norm)
    if 'nama_pasar' in df.columns:
        df['pasar_norm'] = df['nama_pasar'].apply(_norm)

    return df

def _get_sample_pasar_data():
    """Mengembalikan DataFrame contoh untuk pasar (hanya untuk fallback)."""
    return pd.DataFrame({
        'nama_pasar': ['Cisoka', 'Curug', 'Mauk', 'Cikupa', 'Pasar Kemis'],
        'kecamatan': ['Cisoka', 'Curug', 'Mauk', 'Cikupa', 'Pasar Kemis'],
        'alamat': ['Jl. Ps. Cisoka', 'Jl. Raya Curug', 'East Mauk', 'Jl. Raya Serang', 'RGPJ+FJX'],
        'lat': [-6.26435, -6.26100, -6.06044, -6.22907, -6.16365],
        'lon': [106.42592, 106.55858, 106.51129, 106.51981, 106.53155],
        'tera_ulang_tahun': [2025, 2025, 2025, 2025, 2025],
        'jumlah_timbangan_tera_ulang': [195, 251, 161, 257, 174],
        'jenis_timbangan': ['Pegas:77;Meja:30;Elektronik:87'] * 5
    })

@st.cache_data
def load_geojson(path):
    with open(path, 'r', encoding='utf-8') as f:
        gj = json.load(f)
    for ft in gj['features']:
        props = ft['properties']
        wadmkc = props.get('wadmkc','')
        props['kec_norm'] = _norm(wadmkc)
        props['kec_label'] = wadmkc
    return gj

@st.cache_data
def load_spbu_csv(path):
    import csv
    with open(path, 'rb') as f:
        text = f.read().decode('utf-8-sig', errors='ignore')
    if not text.strip():
        return pd.DataFrame()

    first_line = text.splitlines()[0] if text.splitlines() else ''
    count_semi = first_line.count(';')
    count_comma = first_line.count(',')
    sep = ';' if count_semi >= count_comma else ','

    df = pd.read_csv(StringIO(text), sep=sep)
    df.columns = [c.strip() for c in df.columns]

    rename = {
        'No. SPBU':'nama_spbu','Nama SPBU':'nama_spbu','Alamat':'alamat',
        'Kecamatan':'kecamatan','Koordinat':'koordinat',
        'Media BBM':'media_bbm','Produk BBM':'media_bbm'
    }
    df.rename(columns={k:v for k,v in rename.items() if k in df.columns}, inplace=True)

    for col in ['nama_spbu','alamat','kecamatan','koordinat','media_bbm']:
        if col not in df.columns:
            df[col] = ''

    df['nama_spbu'] = df['nama_spbu'].astype(str).str.strip()
    df['kecamatan'] = df['kecamatan'].astype(str).str.strip().str.title()
    df['media_bbm'] = df['media_bbm'].astype(str).str.strip()

    coords = df['koordinat'].apply(parse_coord)
    df['lat'] = pd.to_numeric(coords.apply(lambda x: x[0]), errors='coerce')
    df['lon'] = pd.to_numeric(coords.apply(lambda x: x[1]), errors='coerce')

    def split_media(x):
        return [m.strip() for m in re.split(r'[;,]', str(x)) if m.strip()] if pd.notna(x) else []
    df['media_list'] = df['media_bbm'].apply(split_media)
    return df

# ----- Fungsi klik marker (metrologi) -----
def pick_from_click(map_state, df_context, name_col, kec_col, state_prefix):
    if not map_state:
        return False
    clicked = map_state.get('last_object_clicked')
    if not clicked:
        return False
    latc, lonc = clicked.get('lat'), clicked.get('lng')
    if None in (latc, lonc):
        return False
    if not {'lat','lon',name_col,kec_col}.issubset(df_context.columns):
        return False

    tmp = df_context[['lat','lon',name_col,kec_col]].dropna().copy()
    if tmp.empty:
        return False
    dist = ((tmp['lat'] - latc)**2 + (tmp['lon'] - lonc)**2).idxmin()
    st.session_state[f"{state_prefix}_pending_pick"] = {
        'name': str(df_context.loc[dist, name_col]),
        'kec': str(df_context.loc[dist, kec_col])
    }
    return True

# ----- Fungsi render masing‑masing dashboard -----

def render_dashboard_pasar():
    df = load_excel(FILE_EXCEL)
    geo = load_geojson(FILE_GEOJSON) if os.path.exists(FILE_GEOJSON) else None

    render_page_header("🏪 Dashboard Pasar - Kabupaten Tangerang",
                       "Dinas Perindustrian dan Perdagangan - Bidang Kemetrologian | Status Tera Ulang")

    # --- pending click ---
    pending = st.session_state.pop("pasar_pending_pick", None)
    if pending:
        st.session_state['pasar_kec_sel'] = pending['kec']
        st.session_state['pasar_name_sel'] = pending['name']
        st.rerun()

    # --- sidebar filter ---
    st.sidebar.markdown("---")
    st.sidebar.subheader("Filter Pasar")
    years = sorted(pd.to_numeric(df['tera_ulang_tahun'], errors='coerce').dropna().astype(int).unique())
    year_pick = st.sidebar.selectbox("Tahun Tera Ulang", years[::-1], key='pasar_year_pick')

    df_year = df[df['tera_ulang_tahun'] == year_pick].copy()
    all_kec = uniq(df_year['kecamatan'], clean=True) if not df_year.empty else []
    all_pasar = uniq(df_year['nama_pasar'], clean=False) if not df_year.empty else []

    kec_pick = st.sidebar.selectbox("Kecamatan", ['(Semua)'] + all_kec, key='pasar_kec_filter')
    if kec_pick == '(Semua)':
        pasar_ops = ['(Semua)'] + all_pasar
    else:
        pasar_ops = ['(Semua)'] + uniq(df_year[df_year['kecamatan']==kec_pick]['nama_pasar'], clean=False)
    nama_pick = st.sidebar.selectbox("Nama Pasar", pasar_ops, key='pasar_name_filter')

    st.session_state['pasar_kec_sel'] = kec_pick
    st.session_state['pasar_name_sel'] = nama_pick

    # --- filter dataframe ---
    fdf = df_year.copy()
    if kec_pick != '(Semua)':
        fdf = fdf[fdf['kecamatan'] == kec_pick]
    if nama_pick != '(Semua)':
        fdf = fdf[fdf['nama_pasar'] == nama_pick]

    # --- informasi pasar jika spesifik ---
    if nama_pick != '(Semua)' and not fdf.empty:
        r = fdf.iloc[0]
        st.markdown("---")
        st.markdown(f"""
        <div style="background:#f3e8ff; padding:14px 16px; border-radius:12px; border-left:5px solid #8000FF;">
            <h4 style="color:#4B0082;">🏪 {r['nama_pasar']}</h4>
            <p style="font-size:13px;"><b>Kecamatan:</b> {r['kecamatan']}<br>
            <b>Alamat:</b> {r['alamat']}<br><b>Tahun:</b> {year_pick}</p>
        </div>
        """, unsafe_allow_html=True)

    # --- KPI ---
    if nama_pick != '(Semua)':
        cols = st.columns(4)
        cols[0].metric("Nama Pasar", nama_pick)
        cols[1].metric("Kecamatan", fdf['kecamatan'].iloc[0] if not fdf.empty else '-')
        cols[2].metric("Tahun", year_pick)
        cols[3].metric("Total Timbangan", int(fdf['jumlah_timbangan_tera_ulang'].sum()) if not fdf.empty else 0)
    elif kec_pick != '(Semua)':
        cols = st.columns(4)
        cols[0].metric("Kecamatan", kec_pick)
        cols[1].metric("Total Pasar", fdf['nama_pasar'].nunique())
        cols[2].metric("Tahun", year_pick)
        cols[3].metric("Total Timbangan", int(fdf['jumlah_timbangan_tera_ulang'].sum()))
    else:
        cols = st.columns(4)
        cols[0].metric("Total Kecamatan", fdf['kecamatan'].nunique() if not fdf.empty else 0)
        cols[1].metric("Total Seluruh Pasar", fdf['nama_pasar'].nunique() if not fdf.empty else 0)
        cols[2].metric("Tahun", year_pick)
        cols[3].metric("Total Timbangan", int(fdf['jumlah_timbangan_tera_ulang'].sum()))

    # --- PETA ---
    st.subheader("🗺️ Peta Lokasi Pasar")
    center, zoom = [-6.2, 106.55], 10
    coords = fdf[['lat','lon']].dropna() if {'lat','lon'}.issubset(fdf.columns) else pd.DataFrame()

    if not coords.empty:
        if nama_pick != '(Semua)':
            r = fdf[fdf['nama_pasar']==nama_pick].iloc[0]
            center = [float(r['lat']), float(r['lon'])]
            zoom = 16
        elif len(coords) == 1:
            center = [coords.iloc[0]['lat'], coords.iloc[0]['lon']]
            zoom = 14

    m = folium.Map(location=center, zoom_start=zoom, control_scale=True, tiles=None)
    folium.TileLayer("OpenStreetMap", control=False).add_to(m)

    if geo:
        folium.GeoJson(geo, name="Batas Kecamatan",
                       style_function=lambda x: {"color":"#8000FF","weight":2,"fillOpacity":0},
                       tooltip=folium.GeoJsonTooltip(fields=["kec_label"], aliases=["Kecamatan:"])).add_to(m)

    if not coords.empty:
        cluster = MarkerCluster(name="Pasar").add_to(m)
        for _, r in fdf.iterrows():
            if pd.isna(r['lat']) or pd.isna(r['lon']):
                continue
            tahun = r.get('tera_ulang_tahun')
            folium.CircleMarker(
                location=[float(r['lat']), float(r['lon'])],
                radius=10,
                color=marker_color(tahun, year_pick),
                fill=True,
                fill_opacity=0.7,
                weight=2,
                tooltip=r['nama_pasar'],
                popup=folium.Popup(f"<b>{r['nama_pasar']}</b><br>{r['alamat']}<br>Tahun: {tahun}", max_width=280)
            ).add_to(cluster)
        if nama_pick == '(Semua)' and len(coords) > 1:
            m.fit_bounds([[coords['lat'].min(), coords['lon'].min()],
                          [coords['lat'].max(), coords['lon'].max()]], padding=(30,30))

    folium.LayerControl(collapsed=False).add_to(m)
    map_state = st_folium(m, height=500, use_container_width=True, key="pasar_map")
    if pick_from_click(map_state, fdf, "nama_pasar", "kecamatan", "pasar"):
        st.rerun()

    # --- GRAFIK TREN ---
    st.subheader("📈 Grafik (Tahun ke Tahun)")
    gdf = df.copy()
    if nama_pick != '(Semua)':
        gdf = gdf[gdf['nama_pasar'].str.strip() == nama_pick.strip()]
    elif kec_pick != '(Semua)':
        gdf = gdf[gdf['kecamatan'] == kec_pick]
    gdf = gdf[pd.to_numeric(gdf['tera_ulang_tahun'], errors='coerce').notna()]
    gdf['tera_ulang_tahun'] = gdf['tera_ulang_tahun'].astype(int)

    agg = gdf.groupby('tera_ulang_tahun').agg(
        jumlah_pasar=('nama_pasar','nunique'),
        total_uttp=('jumlah_timbangan_tera_ulang','sum'),
        total_pedagang=('total_pedagang','sum') if 'total_pedagang' in gdf else ('tera_ulang_tahun','size')
    ).reset_index().sort_values('tera_ulang_tahun')
    agg['Tahun'] = agg['tera_ulang_tahun'].astype(str)

    if not agg.empty:
        import altair as alt
        if kec_pick == '(Semua)' and nama_pick == '(Semua)':
            c1, c2, c3 = st.columns(3)
            with c1:
                st.altair_chart(alt.Chart(agg).mark_line(point=True).encode(x='Tahun:O', y='jumlah_pasar:Q').properties(height=250), use_container_width=True)
            with c2:
                st.altair_chart(alt.Chart(agg).mark_line(point=True).encode(x='Tahun:O', y='total_uttp:Q'), use_container_width=True)
            with c3:
                st.altair_chart(alt.Chart(agg).mark_line(point=True).encode(x='Tahun:O', y='total_pedagang:Q'), use_container_width=True)
        else:
            c1, c2 = st.columns(2)
            with c1:
                st.altair_chart(alt.Chart(agg).mark_line(point=True).encode(x='Tahun:O', y='jumlah_pasar:Q'), use_container_width=True)
            with c2:
                st.altair_chart(alt.Chart(agg).mark_line(point=True).encode(x='Tahun:O', y='total_uttp:Q'), use_container_width=True)
    else:
        st.info("Tidak ada data untuk grafik.")

    # --- TOTAL TIMBANGAN TERA ULANG ---
    if not fdf.empty and 'jumlah_timbangan_tera_ulang' in fdf.columns:
        st.markdown("---")
        st.subheader("⚖️ Total Timbangan Tera Ulang")
        total_uttp = int(fdf['jumlah_timbangan_tera_ulang'].sum())
        st.markdown(f"""
        <div style="display:flex; justify-content:center;">
            <div style="background:linear-gradient(135deg,#7c3aed,#4c1d95); color:white; 
                        border-radius:16px; padding:20px 40px; box-shadow:0 6px 12px rgba(0,0,0,0.2); 
                        text-align:center; margin-bottom:20px;">
                <div style="font-size:16px; font-weight:600; opacity:0.9;">Total Timbangan Tera Ulang</div>
                <div style="font-size:42px; font-weight:900;">{total_uttp:,}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Mini card per jenis timbangan
        timb_cols = ['Timb. Pegas', 'Timb. Meja', 'Timb. Elektronik',
                     'Timb. Sentisimal', 'Timb. Bobot Ingsut', 'Neraca', 'Dacin']
        available = [c for c in timb_cols if c in fdf.columns]
        if available:
            st.markdown("""
            <style>
            .mini-card {
                background:white; border-radius:14px; padding:12px; box-shadow:0 3px 6px rgba(0,0,0,0.12);
                border-left:5px solid #7c3aed; margin-bottom:10px;
            }
            .mini-card-title { font-size:13px; font-weight:600; color:#4c1d95; }
            .mini-card-val { font-size:22px; font-weight:800; color:#111827; }
            </style>
            """, unsafe_allow_html=True)

            cols = st.columns(len(available))
            for i, col in enumerate(available):
                val = int(pd.to_numeric(fdf[col], errors='coerce').fillna(0).sum())
                with cols[i]:
                    st.markdown(f"""
                    <div class="mini-card">
                        <div class="mini-card-title">{col.replace('Timb. ','')}</div>
                        <div class="mini-card-val">{val:,}</div>
                    </div>
                    """, unsafe_allow_html=True)


def render_dashboard_spbu():
    df_spbu = load_spbu_csv(FILE_SPBU)
    geo = load_geojson(FILE_GEOJSON) if os.path.exists(FILE_GEOJSON) else None

    render_page_header("⛽ Dashboard SPBU - Kabupaten Tangerang",
                       "Dinas Perindustrian dan Perdagangan - Bidang Kemetrologian")

    # Helper darken (untuk card media BBM)
    def darken(hex_color, percent):
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        r = max(0, int(r * (1 - percent/100)))
        g = max(0, int(g * (1 - percent/100)))
        b = max(0, int(b * (1 - percent/100)))
        return f'#{r:02x}{g:02x}{b:02x}'

    # --- sidebar filter ---
    st.sidebar.markdown("---")
    st.sidebar.subheader("Filter SPBU")
    all_media = sorted({m for lst in df_spbu['media_list'] for m in lst}) if 'media_list' in df_spbu else []
    media_pick = st.sidebar.multiselect("Media BBM", all_media, key='spbu_media_pick')

    base = df_spbu.copy()
    if media_pick and 'media_list' in base.columns:
        base = base[base['media_list'].apply(lambda L: all(m in L for m in media_pick))]

    # --- state management ---
    for key in ['spbu_last_changed','spbu_kec_sel','spbu_name_sel','spbu_force_sync']:
        st.session_state.setdefault(key, "kec" if key=='spbu_last_changed' else "(Semua)" if 'sel' in key else False)

    def _mark_change(which):
        st.session_state['spbu_last_changed'] = which

    pending = st.session_state.pop('spbu_pending_pick', None)
    if pending:
        st.session_state.update({'spbu_last_changed':'name','spbu_kec_sel':pending['kec'],
                                 'spbu_name_sel':pending['name'],'spbu_force_sync':True})
        st.rerun()

    all_kec = uniq(base['kecamatan'], clean=True) if not base.empty else []
    all_spbu = uniq(base['nama_spbu'], clean=False) if not base.empty else []
    kec_ops = ['(Semua)'] + all_kec

    if st.session_state['spbu_force_sync']:
        st.session_state['spbu_kec_w'] = st.session_state['spbu_kec_sel'] if st.session_state['spbu_kec_sel'] in kec_ops else '(Semua)'
        st.session_state['spbu_name_w'] = st.session_state['spbu_name_sel'] if st.session_state['spbu_name_sel'] in (['(Semua)']+all_spbu) else '(Semua)'
        st.session_state['spbu_force_sync'] = False
    else:
        for w in ['spbu_kec_w','spbu_name_w']:
            st.session_state.setdefault(w, '(Semua)')
        if st.session_state['spbu_kec_w'] not in kec_ops:
            st.session_state['spbu_kec_w'] = '(Semua)'
        if st.session_state['spbu_name_w'] not in (['(Semua)']+all_spbu):
            st.session_state['spbu_name_w'] = '(Semua)'

    kec_pick = st.sidebar.selectbox("Kecamatan", kec_ops, key='spbu_kec_w', on_change=_mark_change, args=('kec',))
    if kec_pick != '(Semua)':
        spbu_in_kec = uniq(base[base['kecamatan']==kec_pick]['nama_spbu'], clean=False)
        spbu_ops = ['(Semua)'] + spbu_in_kec
        if st.session_state['spbu_name_sel'] != '(Semua)' and st.session_state['spbu_name_sel'] not in spbu_in_kec:
            spbu_ops.append(st.session_state['spbu_name_sel'])
    else:
        spbu_ops = ['(Semua)'] + all_spbu
    nama_pick = st.sidebar.selectbox("Nama SPBU", spbu_ops, key='spbu_name_w', on_change=_mark_change, args=('name',))

    # sinkronisasi
    new_kec, new_name = kec_pick, nama_pick
    if st.session_state['spbu_last_changed'] == 'name' and new_name != '(Semua)':
        kc = base[base['nama_spbu']==new_name]['kecamatan'].dropna()
        if not kc.empty:
            new_kec = kc.iloc[0]
    if st.session_state['spbu_last_changed'] == 'kec' and new_kec != '(Semua)' and new_name != '(Semua)':
        if base[(base['kecamatan']==new_kec)&(base['nama_spbu']==new_name)].empty:
            new_name = '(Semua)'

    need_rerun = False
    if st.session_state['spbu_kec_sel'] != new_kec:
        st.session_state['spbu_kec_sel'] = new_kec
        need_rerun = True
    if st.session_state['spbu_name_sel'] != new_name:
        st.session_state['spbu_name_sel'] = new_name
        need_rerun = True
    if need_rerun:
        st.session_state['spbu_force_sync'] = True
        st.rerun()

    kec, nama_spbu = st.session_state['spbu_kec_sel'], st.session_state['spbu_name_sel']
    fdf = base.copy()
    if kec != '(Semua)':
        fdf = fdf[fdf['kecamatan'] == kec]
    if nama_spbu != '(Semua)':
        fdf = fdf[fdf['nama_spbu'] == nama_spbu]

    # --- KPI & CARD ---
    if nama_spbu == '(Semua)':
        if kec == '(Semua)':
            c1,c2,c3 = st.columns(3)
            with c1:
                st.metric("Total Kecamatan", fdf['kecamatan'].nunique() if not fdf.empty else 0)
            with c2:
                st.metric("Total SPBU", fdf['nama_spbu'].nunique() if not fdf.empty else 0)
            varian = len(media_pick) if media_pick else len({m for L in fdf['media_list'] for m in L}) if not fdf.empty else 0
            with c3:
                st.metric("Varian Media BBM", varian)
        else:
            total_spbu = fdf['nama_spbu'].nunique() if not fdf.empty else 0
            media_list = sorted({m for L in fdf['media_list'] for m in L}) if not fdf.empty else []
            col1,col2 = st.columns(2)
            with col1:
                st.markdown(f"""
                <div style="background:linear-gradient(135deg,#667eea,#764ba2); color:white; padding:20px; border-radius:12px; text-align:center;">
                    <div style="font-size:14px; opacity:0.9; margin-bottom:5px;">Total SPBU di</div>
                    <div style="font-size:20px; font-weight:700; letter-spacing:0.5px;">{kec.upper()}</div>
                    <div style="font-size:32px; font-weight:700;">{total_spbu}</div>
                    <div style="font-size:14px; opacity:0.9; margin-bottom:5px;">SPBU</div>
                </div>
                """, unsafe_allow_html=True)
            with col2:
                st.markdown(f"""
                <div style="background:linear-gradient(135deg,#f093fb,#f5576c); color:white; padding:20px; border-radius:12px; margin-bottom:25px;">
                    <div style="font-size:14px; opacity:0.9; margin-bottom:5px;">Media BBM Tersedia di</div>
                    <div style="font-size:20px; font-weight:700; letter-spacing:0.5px;">{kec.upper()}</div>
                </div>
                """, unsafe_allow_html=True)

                if media_list:
                    colors = ['#FF6B6B','#4ECDC4','#FFD166','#06D6A0','#118AB2',
                              '#EF476F','#073B4C','#7209B7','#F3722C','#90BE6D','#43AA8B','#577590']
                    icon_map = {
                        'Pertalite': '⛽', 'Pertamax': '⚡', 'Solar': '🛢️',
                        'Diesel': '🚛', 'Super': '🌟', 'V-Power': '💎',
                        'BP 92': '🅱️', 'BP Ultimate': '💎', 'Pertamina Dex': '🛢️'
                    }
                    per_row = min(4, len(media_list))
                    per_row = max(per_row, 2)
                    for row_start in range(0, len(media_list), per_row):
                        row_media = media_list[row_start:row_start + per_row]
                        cols = st.columns(len(row_media))
                        for i, media in enumerate(row_media):
                            with cols[i]:
                                color = colors[(row_start + i) % len(colors)]
                                darkened = darken(color, 20)
                                icon = icon_map.get(media, '⛽')
                                st.markdown(f"""
                                <div style="
                                    background: linear-gradient(135deg, {color} 0%, {darkened} 100%);
                                    color: white;
                                    padding: 20px 12px;
                                    border-radius: 14px;
                                    text-align: center;
                                    min-height: 120px;
                                    display: flex;
                                    flex-direction: column;
                                    justify-content: center;
                                    align-items: center;
                                    box-shadow: 0 8px 16px rgba(0,0,0,0.15);
                                    border: 1px solid rgba(255,255,255,0.3);
                                    margin-bottom: 0;
                                ">
                                    <div style="font-size: 24px; margin-bottom: 8px;">{icon}</div>
                                    <div style="font-size: 14px; font-weight: 700; margin-bottom: 10px; 
                                                text-shadow: 0 2px 4px rgba(0,0,0,0.3);">{media}</div>
                                    <div style="
                                        background-color: rgba(255,255,255,0.3);
                                        padding: 6px 16px;
                                        border-radius: 30px;
                                        font-size: 11px;
                                        font-weight: 700;
                                        letter-spacing: 1px;
                                        backdrop-filter: blur(4px);
                                        border: 1px solid rgba(255,255,255,0.4);
                                    ">
                                        TERSEDIA
                                    </div>
                                </div>
                                """, unsafe_allow_html=True)
                        if row_start + per_row < len(media_list):
                            st.markdown('<div style="margin-bottom: 25px;"></div>', unsafe_allow_html=True)
                else:
                    st.markdown("""
                    <div style="background:rgba(255,255,255,0.1); padding:40px 20px; border-radius:12px; 
                                text-align:center; border:2px dashed rgba(255,255,255,0.3); margin-top:20px;">
                        <div style="font-size:48px; opacity:0.5; margin-bottom:15px;">⛽</div>
                        <div style="font-size:16px; font-weight:600; color:white;">Tidak ada data media BBM</div>
                    </div>
                    """, unsafe_allow_html=True)
    else:
        # detail SPBU
        info = base[base['nama_spbu']==nama_spbu].iloc[0]
        st.markdown("---")
        st.markdown(f"""
        <div style="background:#f3e8ff; padding:14px 16px; border-radius:12px; border-left:5px solid #8000FF;">
            <h4 style="color:#4B0082;">⛽ {nama_spbu}</h4>
            <p style="font-size:13px;"><b>Kecamatan:</b> {kec}<br>
            <b>Alamat:</b> {info['alamat']}<br><b>Media BBM:</b> {info['media_bbm']}</p>
        </div>
        """, unsafe_allow_html=True)

        media_list = fdf.iloc[0]['media_list'] if not fdf.empty and 'media_list' in fdf.columns else []
        if media_list:
            st.markdown("#### 📋 Media BBM Tersedia")
            colors = ["#8000FF","#4B0082","#6A5ACD","#9370DB","#8A2BE2",
                      "#FF6B6B","#4ECDC4","#FFD166","#06D6A0","#118AB2"]
            icon_map = {
                'Pertalite': '⛽', 'Pertamax': '⚡', 'Solar': '🛢️',
                'Diesel': '🚛', 'Super': '🌟', 'V-Power': '💎',
                'BP 92': '🅱️', 'BP Ultimate': '💎', 'Pertamina Dex': '🛢️'
            }
            per_row = min(4, len(media_list))
            for row_start in range(0, len(media_list), per_row):
                row_media = media_list[row_start:row_start + per_row]
                cols = st.columns(len(row_media))
                for i, media in enumerate(row_media):
                    with cols[i]:
                        color_idx = (row_start + i) % len(colors)
                        color = colors[color_idx]
                        darkened = darken(color, 20)
                        icon = icon_map.get(media, '⛽')
                        st.markdown(f"""
                        <div style="
                            background: linear-gradient(135deg, {color} 0%, {darkened} 100%);
                            color: white;
                            padding: 22px 12px;
                            border-radius: 16px;
                            min-height: 130px;
                            display: flex;
                            flex-direction: column;
                            justify-content: center;
                            align-items: center;
                            text-align: center;
                            box-shadow: 0 8px 16px rgba(0,0,0,0.2);
                            border: 1px solid rgba(255,255,255,0.3);
                            margin-bottom: 0;
                        ">
                            <div style="font-size: 28px; margin-bottom: 10px;">{icon}</div>
                            <div style="font-size: 15px; font-weight: 800; margin-bottom: 12px; 
                                        text-shadow: 0 2px 4px rgba(0,0,0,0.3);">{media}</div>
                            <div style="
                                background-color: rgba(255,255,255,0.3);
                                padding: 6px 18px;
                                border-radius: 30px;
                                font-size: 12px;
                                font-weight: 700;
                                letter-spacing: 1px;
                                backdrop-filter: blur(4px);
                                border: 1px solid rgba(255,255,255,0.4);
                            ">
                                TERSEDIA
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                if row_start + per_row < len(media_list):
                    st.markdown('<div style="margin-bottom: 25px;"></div>', unsafe_allow_html=True)
        else:
            st.info("SPBU ini belum memiliki data Media BBM.")

    # --- PETA SPBU ---
    st.subheader("🗺️ Peta Lokasi SPBU")
    center, zoom = [-6.2,106.55], 10
    coords = fdf[['lat','lon']].dropna() if {'lat','lon'}.issubset(fdf.columns) else pd.DataFrame()
    if not coords.empty:
        if nama_spbu != '(Semua)':
            r = fdf[fdf['nama_spbu']==nama_spbu].iloc[0]
            center = [float(r['lat']), float(r['lon'])]
            zoom = 16
        elif len(coords) == 1:
            center = [coords.iloc[0]['lat'], coords.iloc[0]['lon']]
            zoom = 14
    m = folium.Map(location=center, zoom_start=zoom, control_scale=True, tiles=None)
    folium.TileLayer("OpenStreetMap", control=False).add_to(m)
    if geo:
        folium.GeoJson(geo, name="Batas Kecamatan",
                       style_function=lambda x: {"color":"#8000FF","weight":2,"fillOpacity":0},
                       tooltip=folium.GeoJsonTooltip(fields=["kec_label"], aliases=["Kecamatan:"])).add_to(m)
    if not coords.empty:
        cluster = MarkerCluster(name="SPBU").add_to(m)
        for _, r in fdf.iterrows():
            if pd.isna(r['lat']) or pd.isna(r['lon']):
                continue
            is_sel = nama_spbu != '(Semua)' and r['nama_spbu'].strip().lower() == nama_spbu.strip().lower()
            folium.CircleMarker(
                location=[float(r['lat']), float(r['lon'])],
                radius=12 if is_sel else 9,
                color="#8000FF",
                fill=True,
                fill_opacity=0.9 if is_sel else 0.65,
                tooltip=r['nama_spbu'],
                popup=folium.Popup(f"<b>{r['nama_spbu']}</b><br>{r['alamat']}<br>Media: {r['media_bbm']}", max_width=280)
            ).add_to(cluster)
        if nama_spbu == '(Semua)' and len(coords) > 1:
            m.fit_bounds([[coords['lat'].min(), coords['lon'].min()],
                          [coords['lat'].max(), coords['lon'].max()]], padding=(30,30))
    folium.LayerControl(collapsed=False).add_to(m)
    map_state = st_folium(m, height=520, use_container_width=True, key="spbu_map")
    if pick_from_click(map_state, base, "nama_spbu", "kecamatan", "spbu"):
        st.rerun()


# ===============================================
# DASHBOARD PERDAGANGAN (diadaptasi)
# ===============================================

@st.cache_data
def load_perdagangan_data():
    df_raw = pd.read_csv("harga_pasar_2024_2025.csv")
    return prepare_price_dataframe(df_raw)

@st.cache_resource
def get_perdagangan_artifacts(pasar: str, komoditas: str):
    return load_artifacts(pasar, komoditas, ARTIFACT_WINDOW_SIZE)

def get_komoditas_style(nama: str):
    """Mengembalikan (kategori, bg_color, badge_color) berdasarkan nama komoditas."""
    n = str(nama).lower()
    if "beras" in n:
        return "BERAS", "#FFF8E1", "#F9A825"
    if "minyak" in n:
        return "MINYAK", "#FFF3E0", "#FB8C00"
    if "cabe" in n or "cabai" in n or "rawit" in n:
        return "CABAI", "#FFEBEE", "#E53935"
    if "bawang" in n:
        return "BAWANG", "#EDE7F6", "#8E24AA"
    if "tepung" in n or "segitiga biru" in n:
        return "TEPUNG", "#E8F5E9", "#43A047"
    if "gula" in n:
        return "GULA", "#F3E5F5", "#7B1FA2"
    if "ayam" in n or "daging" in n or "telur" in n:
        return "PROTEIN", "#E3F2FD", "#1E88E5"
    return "LAINNYA", "#F5F5F5", "#757575"

def render_dashboard_perdagangan():
    render_page_header("📊 Dashboard Harga Barang & Prediksi",
                       "Dinas Perindustrian dan Perdagangan - Bidang Perdagangan | Analisis Harga Pasar")

    # CSS tambahan untuk kartu komoditas dan badge
    st.markdown("""
    <style>
    .komod-card {
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    .komod-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 4px 10px rgba(0,0,0,0.18);
    }
    .komod-badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 999px;
        font-size: 10px;
        font-weight: 600;
        color: white;
        margin-left: 6px;
    }
    .badge{
      display:inline-block;
      padding:2px 10px;
      border-radius:999px;
      font-size:12px;
      font-weight:700;
      color:white;
      margin-right:6px;
    }
    .badge-up{ background:#E53935; }
    .badge-down{ background:#1E88E5; }
    .badge-flat{ background:#43A047; }
    .badge-vol{ background:#6D4C41; }
    .badge-soft{ opacity:0.92; }
    </style>
    """, unsafe_allow_html=True)

    # --- Load data ---
    try:
        df = load_perdagangan_data()
    except Exception as e:
        st.error(f"Gagal membaca dataset 'harga_pasar_2024_2025.csv': {e}")
        st.stop()

    # --- Pilih pasar ---
    pasar_list = sorted(df["pasar"].unique().tolist())
    pasar = st.selectbox("Pilih Pasar", pasar_list, key="dagang_pasar")

    df_pasar = df[df["pasar"] == pasar].copy()
    if df_pasar.empty:
        st.warning(f"Tidak ada data untuk pasar **{pasar}**.")
        st.stop()

    df_pasar["tanggal"] = pd.to_datetime(df_pasar["tanggal"])
    min_date = df_pasar["tanggal"].min().date()
    max_date = df_pasar["tanggal"].max().date()

    # --- Pilih tanggal ---
    st.markdown("#### 📅 Pilih Tanggal")
    selected_date = st.date_input(
        "Tanggal harga yang ingin dilihat",
        value=max_date,
        min_value=min_date,
        max_value=max_date,
        key="dagang_tgl"
    )

    df_hari_ini = df_pasar[df_pasar["tanggal"].dt.date == selected_date].copy()

    if df_hari_ini.empty:
        st.warning(f"Tidak ada data pada tanggal **{selected_date}**.")
    else:
        df_hari_ini = df_hari_ini.sort_values("komoditas")
        st.markdown(f"#### 💰 Daftar Harga Komoditas – Pasar **{pasar}** ({selected_date})")

        num_cols = 3
        cols = st.columns(num_cols)

        for i, row in df_hari_ini.iterrows():
            c = cols[i % num_cols]
            nama = str(row["komoditas"])
            harga = row["harga"]
            kategori, bg_color, badge_color = get_komoditas_style(nama)

            with c:
                st.markdown(
                    f"""
                    <div class="komod-card" style="
                        background-color: {bg_color};
                        padding: 14px 16px;
                        border-radius: 14px;
                        margin-bottom: 12px;
                        box-shadow: 0 2px 4px rgba(0,0,0,0.10);
                        border: 1px solid rgba(0,0,0,0.08);
                    ">
                        <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:6px;">
                            <div style="font-weight:700; font-size:14px;">
                                {nama.upper()}
                            </div>
                            <span class="komod-badge" style="background-color:{badge_color};">
                                {kategori}
                            </span>
                        </div>
                        <div style="font-size:12px; color:#555;">Harga</div>
                        <div style="font-size:20px; font-weight:800; color:#1A237E;">
                            Rp {harga:,.0f}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

    st.markdown("---")

    # --- Detail & Prediksi per komoditas ---
    st.markdown("### 🔍 Detail Per Komoditas + Prediksi")

    komoditas_list = sorted(df_pasar["komoditas"].unique().tolist())
    komoditas = st.selectbox(
        "Pilih komoditas",
        ["— Pilih komoditas —"] + komoditas_list,
        index=0,
        key="dagang_komoditas"
    )

    if komoditas == "— Pilih komoditas —":
        st.info("Pilih komoditas untuk melihat riwayat dan prediksi harganya.")
        return

    forecast_days = st.slider(
        "Jumlah hari prediksi",
        min_value=7,
        max_value=60,
        value=FORECAST_DAYS_DEFAULT,
        step=1,
        key="dagang_forecast_days"
    )

    df_sub = df_pasar[df_pasar["komoditas"] == komoditas].copy().sort_values("tanggal")
    if df_sub.empty:
        st.warning("Data historis kosong.")
        return

    st.caption(f"Periode: {df_sub['tanggal'].min().date()} s.d. {df_sub['tanggal'].max().date()}")

    loaded = get_perdagangan_artifacts(pasar, komoditas)
    if loaded is None:
        st.warning(
            f"Model untuk **{komoditas} – {pasar}** belum ada di folder `artifacts/` "
            f"(WS={ARTIFACT_WINDOW_SIZE})."
        )
        return

    model = loaded["model"]
    scaler = loaded["scaler"]
    mae = loaded.get("mae")
    rmse = loaded.get("rmse")
    if mae is not None and rmse is not None:
        st.caption(f"📌 Evaluasi model: MAE={mae:.0f} | RMSE={rmse:.0f}")

    df_pred = forecast_lstm(
        model=model,
        scaler=scaler,
        df_sub=df_sub,
        n_days=forecast_days,
        window_size=ARTIFACT_WINDOW_SIZE
    )

    if df_pred is None or df_pred.empty:
        st.warning("Prediksi tidak tersedia (cek artifacts / window size / data historis).")
        return

    # --- KPI dan Badge ---
    h = min(7, len(df_pred))
    last_actual = float(df_sub["harga"].iloc[-1])
    mean_pred_7 = float(df_pred["prediksi"].head(h).mean())
    last_pred_7 = float(df_pred["prediksi"].iloc[h-1])

    change_pct_mean = ((mean_pred_7 - last_actual) / last_actual * 100) if last_actual > 0 else 0.0
    change_pct_last = ((last_pred_7 - last_actual) / last_actual * 100) if last_actual > 0 else 0.0

    trend_score = change_pct_last if abs(change_pct_last) > abs(change_pct_mean) else change_pct_mean

    if len(df_pred) > 2:
        pct_changes = df_pred["prediksi"].pct_change().dropna() * 100
        volatility = float(pct_changes.std()) if not pct_changes.empty else 0.0
    else:
        volatility = 0.0

    if trend_score > 10:
        tren_text, tren_class = "TREND: naik tajam", "badge-up"
    elif trend_score > 3:
        tren_text, tren_class = "TREND: naik ringan", "badge-up"
    elif trend_score < -10:
        tren_text, tren_class = "TREND: turun tajam", "badge-down"
    elif trend_score < -3:
        tren_text, tren_class = "TREND: turun ringan", "badge-down"
    else:
        tren_text, tren_class = "TREND: stabil", "badge-flat"

    if volatility > 8:
        vol_text = "VOL: tinggi"
    elif volatility > 4:
        vol_text = "VOL: sedang"
    else:
        vol_text = "VOL: rendah"

    st.markdown(
        f'<span class="badge {tren_class}">{tren_text}</span>'
        f'<span class="badge badge-vol">{vol_text}</span>',
        unsafe_allow_html=True
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Harga terakhir", f"Rp {last_actual:,.0f}")
    c2.metric(f"Rata-rata prediksi {h} hari", f"Rp {mean_pred_7:,.0f}", f"{change_pct_mean:+.1f}%")
    c3.metric(f"Prediksi hari ke-{h}", f"Rp {last_pred_7:,.0f}", f"{change_pct_last:+.1f}%")
    c4.metric("Volatilitas prediksi", f"{volatility:.1f}%", "")

    # --- Grafik ---
    st.markdown("#### 📉 Riwayat + Prediksi Harga (Overlay)")
    df_sub_plot = df_sub.copy()
    df_sub_plot["tanggal"] = pd.to_datetime(df_sub_plot["tanggal"])
    df_pred_plot = df_pred.copy()
    df_pred_plot["tanggal"] = pd.to_datetime(df_pred_plot["tanggal"])
    last_actual_date = df_sub_plot["tanggal"].max()

    import plotly.graph_objects as go
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_sub_plot["tanggal"], y=df_sub_plot["harga"],
        mode="lines+markers", name="Aktual",
        hovertemplate="<b>%{x|%d-%m-%Y}</b><br>Aktual: <b>Rp %{y:,.0f}</b><extra></extra>"
    ))
    fig.add_trace(go.Scatter(
        x=df_pred_plot["tanggal"], y=df_pred_plot["prediksi"],
        mode="lines+markers", name="Prediksi", line=dict(dash="dash"),
        hovertemplate="<b>%{x|%d-%m-%Y}</b><br>Prediksi: <b>Rp %{y:,.0f}</b><extra></extra>"
    ))
    fig.add_shape(
        type="line", x0=last_actual_date, x1=last_actual_date, y0=0, y1=1,
        xref="x", yref="paper", line=dict(color="gray", width=2, dash="dot")
    )
    fig.update_layout(
        title={"text": f"{komoditas} – Pasar {pasar} (Prediksi {forecast_days} hari)", "x": 0.5},
        xaxis_title="Tanggal", yaxis_title="Harga (Rp)",
        template="plotly_white", hovermode="x unified",
        margin=dict(l=30, r=10, t=60, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5)
    )
    st.plotly_chart(fig, use_container_width=True)

    # --- Tabel prediksi ---
    st.markdown("#### 📋 Prediksi (ringkas)")
    df_pred_tampil = df_pred.copy()
    df_pred_tampil["tanggal"] = pd.to_datetime(df_pred_tampil["tanggal"]).dt.strftime("%d-%m-%Y")
    df_pred_tampil["prediksi"] = df_pred_tampil["prediksi"].round(0).astype(int)
    df_pred_tampil = df_pred_tampil.rename(columns={"tanggal": "Tanggal", "prediksi": "Prediksi (Rp)"})
    st.dataframe(df_pred_tampil.head(7), use_container_width=True, hide_index=True)
    with st.expander("Lihat semua prediksi"):
        st.dataframe(df_pred_tampil, use_container_width=True, hide_index=True)

    # --- Saran kebijakan ---
    st.markdown("#### 📑 Saran Kebijakan")
    st.markdown(kebijakan_saran(df_sub, df_pred, horizon_analisis=7))


# ===============================================
# NAVIGASI UTAMA
# ===============================================
def main():
    # Sidebar untuk pemilihan bidang
    with st.sidebar:
        st.markdown("## 🏛️ Dinas Perindustrian & Perdagangan")
        domain = st.radio(
            "Pilih Bidang",
            ["Kemetrologian", "Perdagangan"],
            key="domain_radio"
        )
        st.markdown("---")

    if domain == "Kemetrologian":
        with st.sidebar:
            st.markdown("### 📌 Dashboard Metrologi")
            page = st.radio(
                "Menu",
                ["🏪 Pasar (Tera Ulang)", "⛽ SPBU"],
                index=0,
                label_visibility="collapsed",
                key="metrologi_page"
            )
            st.markdown("---")
        if page == "🏪 Pasar (Tera Ulang)":
            render_dashboard_pasar()
        else:
            render_dashboard_spbu()
    else:
        # Bidang Perdagangan – tanpa sidebar tambahan
        render_dashboard_perdagangan()

if __name__ == "__main__":
    main()