# models_lstm.py
"""
Fungsi-fungsi model LSTM untuk prediksi harga komoditas per pasar.

Dipakai di app.py dengan:
    from models import train_lstm_for, forecast_lstm
"""

import numpy as np
import pandas as pd
from pathlib import Path
import json
import joblib
import tensorflow as tf
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense
from tensorflow.keras.callbacks import EarlyStopping
import math


def _ensure_datetime(df: pd.DataFrame, col: str = "tanggal") -> pd.DataFrame:
    """Pastikan kolom tanggal bertipe datetime dan di-sort naik."""
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], errors="coerce")
        df = df.dropna(subset=[col]).sort_values(col)
    return df


def _create_sequences(series_scaled: np.ndarray, window_size: int):
    """
    Mengubah deret 1D (data sudah di-scale) menjadi
    X shape (n_samples, window_size, 1)
    y shape (n_samples,)
    """
    X, y = [], []
    for i in range(window_size, len(series_scaled)):
        X.append(series_scaled[i - window_size:i, 0])
        y.append(series_scaled[i, 0])
    X = np.array(X)
    y = np.array(y)
    X = np.reshape(X, (X.shape[0], X.shape[1], 1))
    return X, y


def _build_lstm_model(window_size: int) -> Sequential:
    """Membangun arsitektur LSTM sederhana untuk univariate forecasting."""
    model = Sequential()
    model.add(LSTM(64, return_sequences=False, input_shape=(window_size, 1)))
    model.add(Dense(32, activation="relu"))
    model.add(Dense(1))

    model.compile(optimizer="adam", loss="mse")
    return model


def train_lstm_for(
    df: pd.DataFrame,
    komoditas: str,
    pasar: str,
    window_size: int = 30,
    epochs: int = 30,
):
    """
    Melatih model LSTM untuk kombinasi (komoditas, pasar) tertentu.

    Parameters
    ----------
    df : DataFrame
        Data panjang dengan kolom minimal: ['tanggal', 'komoditas', 'pasar', 'harga'].
    komoditas : str
        Nama komoditas yang akan dilatih modelnya (uppercase / lowercase tidak masalah,
        akan dicocokkan casefold).
    pasar : str
        Nama pasar (CISOKA / SEPATAN / dll, disesuaikan dengan isi df['pasar']).
    window_size : int, default 30
        Banyaknya hari historis yang dipakai sebagai input sequence LSTM.
    epochs : int, default 30
        Jumlah epoch training.

    Returns
    -------
    model : keras.Model
    scaler : MinMaxScaler
    df_sub : DataFrame (data historis untuk komoditas & pasar ini, sudah di-sort)
    history : History object (keras)
    metrics : (mae, rmse) pada data test
    """
    # Filter data untuk komoditas & pasar tertentu
    df_sub = df.copy()
    df_sub["komoditas"] = df_sub["komoditas"].astype(str).str.upper().str.strip()
    df_sub["pasar"] = df_sub["pasar"].astype(str).str.upper().str.strip()

    komo_upper = str(komoditas).upper().strip()
    pasar_upper = str(pasar).upper().strip()

    df_sub = df_sub[
        (df_sub["komoditas"] == komo_upper) & (df_sub["pasar"] == pasar_upper)
    ].copy()

    # Pastikan tanggal rapi
    df_sub = _ensure_datetime(df_sub, "tanggal")

    # Buang baris tanpa harga
    df_sub = df_sub.dropna(subset=["harga"]).copy()

    if len(df_sub) <= window_size + 5:
        print(
            f"[train_lstm_for] Data terlalu sedikit untuk "
            f"{komoditas} - {pasar} (n={len(df_sub)})."
        )
        return None, None, df_sub, None, (None, None)

    # Ambil hanya deret harga sebagai numpy
    values = df_sub["harga"].values.reshape(-1, 1)

    # Scaling
    scaler = MinMaxScaler(feature_range=(0, 1))
    values_scaled = scaler.fit_transform(values)

    # Buat sequence
    X, y = _create_sequences(values_scaled, window_size)

    # Train-test split (80% train, 20% test)
    split_idx = int(len(X) * 0.8)
    X_train, y_train = X[:split_idx], y[:split_idx]
    X_test, y_test = X[split_idx:], y[split_idx:]

    # Bangun model
    tf.keras.backend.clear_session()
    model = _build_lstm_model(window_size)

    # Early stopping biar tidak overfitting
    es = EarlyStopping(
        monitor="val_loss",
        patience=5,
        restore_best_weights=True,
        verbose=0,
    )

    history = model.fit(
        X_train,
        y_train,
        epochs=epochs,
        batch_size=16,
        validation_split=0.1,
        callbacks=[es],
        verbose=0,
    )

    # Evaluasi di data test
    y_pred_test_scaled = model.predict(X_test, verbose=0)
    # Inverse transform
    y_test_inv = scaler.inverse_transform(y_test.reshape(-1, 1)).ravel()
    y_pred_test_inv = scaler.inverse_transform(y_pred_test_scaled).ravel()

    mae = mean_absolute_error(y_test_inv, y_pred_test_inv)
    rmse = math.sqrt(mean_squared_error(y_test_inv, y_pred_test_inv))

    return model, scaler, df_sub, history, (mae, rmse)


def forecast_lstm(
    model,
    scaler: MinMaxScaler,
    df_sub: pd.DataFrame,
    n_days: int = 30,
    window_size: int = 30,
) -> pd.DataFrame:
    """
    Membuat prediksi n hari ke depan untuk kombinasi (komoditas, pasar) tertentu,
    menggunakan model dan scaler yang sudah ditraining.

    Parameters
    ----------
    model : keras.Model
        Model LSTM terlatih dari train_lstm_for.
    scaler : MinMaxScaler
        Scaler yang dipakai saat training.
    df_sub : DataFrame
        Data historis untuk komoditas & pasar ini (output dari train_lstm_for).
        Kolom minimal: ['tanggal', 'harga'].
    n_days : int, default 30
        Banyaknya hari yang ingin diprediksi ke depan.
    window_size : int, default 30
        Window historis yang dipakai seperti saat training.

    Returns
    -------
    df_pred : DataFrame
        Tabel berisi tanggal prediksi dan nilai prediksi.
        Kolom: ['tanggal', 'prediksi']
    """
    if model is None or scaler is None or df_sub is None or df_sub.empty:
        return pd.DataFrame(columns=["tanggal", "prediksi"])

    df_sub = _ensure_datetime(df_sub, "tanggal")
    df_sub = df_sub.dropna(subset=["harga"]).copy()
    values = df_sub["harga"].values.reshape(-1, 1)
    values_scaled = scaler.transform(values)

    if len(values_scaled) < window_size:
        print("[forecast_lstm] Data historis kurang dari window_size.")
        return pd.DataFrame(columns=["tanggal", "prediksi"])

    # Ambil window terakhir
    last_window = values_scaled[-window_size:].copy().reshape(1, window_size, 1)

    preds_scaled = []
    current_window = last_window

    for _ in range(n_days):
        next_scaled = model.predict(current_window, verbose=0)[0, 0]
        preds_scaled.append(next_scaled)

        # Update window: geser satu langkah, tambahkan prediksi baru
        new_window = np.append(current_window[0, 1:, 0], next_scaled)
        current_window = new_window.reshape(1, window_size, 1)

    preds_scaled = np.array(preds_scaled).reshape(-1, 1)
    preds_inv = scaler.inverse_transform(preds_scaled).ravel()

    # Buat tanggal prediksi mulai dari tanggal terakhir + 1 hari
    last_date = df_sub["tanggal"].max()
    future_dates = pd.date_range(start=last_date + pd.Timedelta(days=1),
                                 periods=n_days, freq="D")

    df_pred = pd.DataFrame({
        "tanggal": future_dates,
        "prediksi": preds_inv
    })

    return df_pred
    
# =========================
# SAVE / LOAD ARTEFAK (.keras + joblib + meta.json)
# =========================

ARTIFACT_DIR = Path("artifacts")

def _slug(s: str) -> str:
    s = str(s).strip().upper()
    return "".join(ch if ch.isalnum() else "_" for ch in s)

def _artifact_base(pasar: str, komoditas: str, window_size: int) -> str:
    return f"{_slug(pasar)}__{_slug(komoditas)}__WS{int(window_size)}"

def save_artifacts(model, scaler, meta: dict, pasar: str, komoditas: str, window_size: int):
    """
    Simpan:
      - model.keras
      - scaler.joblib
      - meta.json
    """
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    base = _artifact_base(pasar, komoditas, window_size)

    model_path = ARTIFACT_DIR / f"{base}.keras"
    scaler_path = ARTIFACT_DIR / f"{base}.scaler.joblib"
    meta_path = ARTIFACT_DIR / f"{base}.meta.json"

    model.save(model_path)                 # <-- model.keras
    joblib.dump(scaler, scaler_path)       # <-- scaler.joblib
    meta_path.write_text(
        json.dumps(meta or {}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    return {"model_path": str(model_path), "scaler_path": str(scaler_path), "meta_path": str(meta_path)}

def load_artifacts(pasar: str, komoditas: str, window_size: int):
    """
    Load artefak. Return dict atau None jika tidak ada.
    """
    base = _artifact_base(pasar, komoditas, window_size)

    model_path = ARTIFACT_DIR / f"{base}.keras"
    scaler_path = ARTIFACT_DIR / f"{base}.scaler.joblib"
    meta_path = ARTIFACT_DIR / f"{base}.meta.json"

    if not model_path.exists() or not scaler_path.exists():
        return None

    model = tf.keras.models.load_model(model_path)
    scaler = joblib.load(scaler_path)
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}

    # Biar app.py gampang, return sekalian mae/rmse kalau ada di meta
    return {
        "model": model,
        "scaler": scaler,
        "meta": meta,
        "mae": meta.get("mae"),
        "rmse": meta.get("rmse"),
        "dir": str(ARTIFACT_DIR),
    }
