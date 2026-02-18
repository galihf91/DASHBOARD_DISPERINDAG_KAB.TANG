# 📊 Dashboard Harga Barang & Prediksi (LSTM)
Aplikasi dashboard interaktif untuk memonitor harga harian komoditas di pasar-pasar Kabupaten Tangerang, lengkap dengan fitur analisis prediksi harga menggunakan model LSTM (Long Short-Term Memory) dan rekomendasi kebijakan otomatis.

Dikembangkan untuk Dinas Perindustrian & Perdagangan Kabupaten Tangerang.

---

## 🚀 Fitur Utama

### **1. Dashboard Harga Harian (Tab 1)**
- Pilih pasar (Cisoka / Sepatan atau lainnya)
- Tampilkan semua harga komoditas per tanggal dalam bentuk kartu yang elegan
- Grafik batang interaktif
- Detail riwayat harga per komoditas + grafik interaktif

---

### **2. Training Model LSTM (Tab 2)**
- Pilih komoditas & pasar
- Atur parameter:
  - window size
  - jumlah hari prediksi
  - epoch training
- Training model LSTM langsung di dalam dashboard
- Evaluasi model (MAE & RMSE)
- Grafik **Aktual vs Prediksi** menggunakan Plotly premium
- Tabel hasil prediksi yang rapi & informatif

---

### **3. Saran Kebijakan Otomatis**
Sistem memberikan rekomendasi kebijakan berdasarkan:
- tren harga (naik / turun / stabil)
- volatilitas harga
- rata-rata prediksi ke depan
- potensi intervensi pasar

---

## 🧠 Teknologi yang Digunakan

- **Python 3**
- **Streamlit** — tampilan dashboard interaktif
- **Pandas & NumPy** — pengolahan data
- **Plotly** — grafik premium
- **TensorFlow (LSTM)** — model prediksi harga
- **Scikit-Learn** — scaling & evaluasi
- **Joblib** — penyimpanan scaler (opsional)
- **utils.py** — manajemen data & saran kebijakan
- **models.py** — training + forecasting LSTM

---

## 📁 Struktur Folder

