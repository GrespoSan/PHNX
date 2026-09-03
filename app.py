from __future__ import annotations

import io
import json
import re
import shutil
import sqlite3
import hashlib
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image, ImageOps, ImageEnhance
import pytesseract
import yfinance as yf

APP_NAME = "G. Signal Tracker"
APP_VERSION = "V1.2"
DATA_DIR = Path("data")
SCREENSHOT_DIR = DATA_DIR / "screenshots"
DB_PATH = DATA_DIR / "signals.db"
DATA_DIR.mkdir(exist_ok=True)
SCREENSHOT_DIR.mkdir(exist_ok=True)

CONFIRMATIONS = [
    "Medie mobili",
    "M4",
    "Stocastico/TDI",
    "Bollinger",
    "Supertrend",
    "Price Action",
    "Altro",
]

SETUP_ORIGINS = ["—", "Balance", "Punto di svolta", "Balance + Punto di svolta", "Altro"]
TIMEFRAMES = ["—", "15m", "30m", "1H", "2H", "4H", "Daily", "Weekly", "Monthly", "Altro"]

# Alias liberi: l'utente può sempre correggere ticker e nome strumento prima del salvataggio.
INSTRUMENT_ALIASES = {
    "futures oro": ("GOLD FUTURES", "GC=F"),
    "oro": ("GOLD FUTURES", "GC=F"),
    "gold": ("GOLD FUTURES", "GC=F"),
    "gc": ("GOLD FUTURES", "GC=F"),
    "nasdaq": ("NASDAQ FUTURES", "NQ=F"),
    "nq": ("NASDAQ FUTURES", "NQ=F"),
    "sp 500": ("S&P 500 FUTURES", "ES=F"),
    "s&p 500": ("S&P 500 FUTURES", "ES=F"),
    "es": ("S&P 500 FUTURES", "ES=F"),
    "dow": ("DOW FUTURES", "YM=F"),
    "ym": ("DOW FUTURES", "YM=F"),
    "russell": ("RUSSELL 2000 FUTURES", "RTY=F"),
    "rty": ("RUSSELL 2000 FUTURES", "RTY=F"),
    "crude": ("WTI CRUDE OIL", "CL=F"),
    "wti": ("WTI CRUDE OIL", "CL=F"),
    "cl": ("WTI CRUDE OIL", "CL=F"),
    "silver": ("SILVER FUTURES", "SI=F"),
    "argento": ("SILVER FUTURES", "SI=F"),
    "si": ("SILVER FUTURES", "SI=F"),
    "copper": ("COPPER FUTURES", "HG=F"),
    "rame": ("COPPER FUTURES", "HG=F"),
    "hg": ("COPPER FUTURES", "HG=F"),
    "natural gas": ("NATURAL GAS", "NG=F"),
    "gas naturale": ("NATURAL GAS", "NG=F"),
    "ng": ("NATURAL GAS", "NG=F"),
    "corn": ("CORN FUTURES", "ZC=F"),
    "mais": ("CORN FUTURES", "ZC=F"),
    "zc": ("CORN FUTURES", "ZC=F"),
    "wheat": ("WHEAT FUTURES", "ZW=F"),
    "grano": ("WHEAT FUTURES", "ZW=F"),
    "zw": ("WHEAT FUTURES", "ZW=F"),
    "soybean": ("SOYBEAN FUTURES", "ZS=F"),
    "soia": ("SOYBEAN FUTURES", "ZS=F"),
    "zs": ("SOYBEAN FUTURES", "ZS=F"),
    "euro fx": ("EURO FX FUTURES", "6E=F"),
    "6e": ("EURO FX FUTURES", "6E=F"),
    "british pound": ("BRITISH POUND FUTURES", "6B=F"),
    "6b": ("BRITISH POUND FUTURES", "6B=F"),
    "australian dollar": ("AUSTRALIAN DOLLAR FUTURES", "6A=F"),
    "6a": ("AUSTRALIAN DOLLAR FUTURES", "6A=F"),
    "japanese yen": ("JAPANESE YEN FUTURES", "6J=F"),
    "6j": ("JAPANESE YEN FUTURES", "6J=F"),
}


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                valid_date TEXT NOT NULL,
                instrument TEXT NOT NULL,
                ticker TEXT,
                direction TEXT NOT NULL,
                e1 REAL,
                s1 REAL,
                e2 REAL,
                s2 REAL,
                t1 REAL,
                t2 REAL,
                setup_origin TEXT,
                reference_area TEXT,
                setup_timeframe TEXT,
                confirmations TEXT,
                notes TEXT,
                screenshot_path TEXT,
                ocr_text TEXT,
                status TEXT NOT NULL DEFAULT 'PUBBLICATO',
                actual_entry REAL,
                actual_stop REAL,
                entry_time TEXT,
                t1_hit_time TEXT,
                t2_hit_time TEXT,
                stop_hit_time TEXT,
                outcome TEXT,
                result_note TEXT,
                last_check TEXT
            )
            """
        )
        conn.commit()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def configure_tesseract() -> bool:
    if shutil.which("tesseract"):
        return True
    common = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for p in common:
        if Path(p).exists():
            pytesseract.pytesseract.tesseract_cmd = p
            return True
    return False


def preprocess_for_ocr(img: Image.Image, scale: int = 2, contrast: float = 2.3) -> Image.Image:
    gray = ImageOps.grayscale(img)
    if scale > 1:
        gray = gray.resize((gray.width * scale, gray.height * scale))
    gray = ImageEnhance.Contrast(gray).enhance(contrast)
    return gray


def run_ocr(img: Image.Image) -> Tuple[str, str]:
    """Ritorna OCR completo + OCR fascia alta, utile per lo strumento TradingView."""
    if not configure_tesseract():
        raise RuntimeError(
            "OCR non disponibile: su Streamlit Community Cloud serve anche il file packages.txt con la riga tesseract-ocr nel repository."
        )

    full = preprocess_for_ocr(img, scale=2, contrast=2.2)
    full_text = pytesseract.image_to_string(full, config="--psm 11")

    # La descrizione dello strumento è normalmente nella parte alta del grafico.
    h = max(90, int(img.height * 0.16))
    w = max(500, int(img.width * 0.50))
    top = img.crop((0, 0, min(w, img.width), min(h, img.height)))
    top = preprocess_for_ocr(top, scale=4, contrast=3.0)
    top_text = pytesseract.image_to_string(top, config="--psm 11")
    return full_text, top_text


def normalize_number(raw: Optional[str]) -> Optional[float]:
    if raw is None:
        return None
    s = str(raw).strip().replace(" ", "")
    if not s:
        return None
    s = re.sub(r"[^0-9,.-]", "", s)
    if not s or s in {"-", ".", ","}:
        return None

    if "," in s and "." in s:
        # L'ultimo separatore viene interpretato come separatore decimale.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")

    try:
        return float(s)
    except ValueError:
        return None


def fmt_num(v: Optional[float]) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return ""
    return f"{float(v):.6f}".rstrip("0").rstrip(".")


def parse_date(raw: str) -> Optional[str]:
    m = re.search(r"\b([0-3]?\d)[./-]([01]?\d)[./-](\d{2}|\d{4})\b", raw)
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 2000
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def extract_tag_value(text: str, tag: str) -> Optional[float]:
    # Tollera E1 4445.6, E1:4445,6, "£1" OCR, spazi e trattini.
    aliases = {
        "E1": r"(?:E|£)\s*1",
        "E2": r"(?:E|£)\s*2",
        "S1": r"(?:S|\$)\s*1",
        "S2": r"(?:S|\$)\s*2",
        "T1": r"T\s*1",
        "T2": r"T\s*2",
    }
    pat = aliases[tag]
    m = re.search(pat + r"\s*[:=]?\s*([0-9][0-9.,]*)", text, flags=re.I)
    return normalize_number(m.group(1)) if m else None


def infer_instrument(top_text: str, full_text: str) -> Tuple[str, str]:
    txt = (top_text + "\n" + full_text).lower()
    # Prima match sulle frasi più lunghe, per evitare alias troppo corti.
    for key in sorted(INSTRUMENT_ALIASES, key=len, reverse=True):
        if re.search(r"(?<![a-z0-9])" + re.escape(key) + r"(?![a-z0-9])", txt):
            return INSTRUMENT_ALIASES[key]

    # Se non riconosciuto, prova a conservare la prima riga utile della fascia alta.
    for line in top_text.splitlines():
        clean = line.strip()
        if clean and len(clean) >= 3 and "tradingview" not in clean.lower():
            return clean[:80], ""
    return "", ""


def parse_signal(full_text: str, top_text: str) -> Dict[str, Any]:
    combined = top_text + "\n" + full_text
    direction_match = re.search(r"\b(LONG|SHORT)\b", combined, flags=re.I)
    instrument, ticker = infer_instrument(top_text, full_text)
    return {
        "valid_date": parse_date(combined),
        "instrument": instrument,
        "ticker": ticker,
        "direction": direction_match.group(1).upper() if direction_match else "",
        "e1": extract_tag_value(combined, "E1"),
        "s1": extract_tag_value(combined, "S1"),
        "e2": extract_tag_value(combined, "E2"),
        "s2": extract_tag_value(combined, "S2"),
        "t1": extract_tag_value(combined, "T1"),
        "t2": extract_tag_value(combined, "T2"),
    }


def save_screenshot(uploaded_file) -> str:
    raw = uploaded_file.getvalue()
    digest = hashlib.sha1(raw).hexdigest()[:12]
    suffix = Path(uploaded_file.name).suffix.lower() or ".png"
    path = SCREENSHOT_DIR / f"{datetime.now():%Y%m%d_%H%M%S}_{digest}{suffix}"
    path.write_bytes(raw)
    return str(path)


def insert_signal(data: Dict[str, Any]) -> int:
    ts = now_iso()
    cols = [
        "created_at", "updated_at", "valid_date", "instrument", "ticker", "direction",
        "e1", "s1", "e2", "s2", "t1", "t2", "setup_origin", "reference_area",
        "setup_timeframe", "confirmations", "notes", "screenshot_path", "ocr_text", "status"
    ]
    vals = [
        ts, ts, data["valid_date"], data["instrument"], data.get("ticker", ""), data["direction"],
        data.get("e1"), data.get("s1"), data.get("e2"), data.get("s2"), data.get("t1"), data.get("t2"),
        data.get("setup_origin", "—"), data.get("reference_area", ""), data.get("setup_timeframe", "—"),
        json.dumps(data.get("confirmations", []), ensure_ascii=False), data.get("notes", ""),
        data.get("screenshot_path", ""), data.get("ocr_text", ""), "PUBBLICATO"
    ]
    with get_conn() as conn:
        cur = conn.execute(
            f"INSERT INTO signals ({','.join(cols)}) VALUES ({','.join(['?'] * len(cols))})", vals
        )
        conn.commit()
        return int(cur.lastrowid)


def load_signals(where: str = "", params: tuple = ()) -> pd.DataFrame:
    q = "SELECT * FROM signals"
    if where:
        q += " WHERE " + where
    q += " ORDER BY valid_date DESC, id DESC"
    with get_conn() as conn:
        return pd.read_sql_query(q, conn, params=params)


def load_signal(signal_id: int) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM signals WHERE id=?", (signal_id,)).fetchone()
        return row


def update_signal(signal_id: int, **kwargs) -> None:
    if not kwargs:
        return
    kwargs["updated_at"] = now_iso()
    assignments = ", ".join([f"{k}=?" for k in kwargs])
    vals = list(kwargs.values()) + [signal_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE signals SET {assignments} WHERE id=?", vals)
        conn.commit()


def get_current_price(ticker: str) -> Tuple[Optional[float], str]:
    if not ticker:
        return None, "Ticker Yahoo Finance mancante"
    try:
        t = yf.Ticker(ticker)
        try:
            info = t.fast_info
            p = info.get("last_price") if hasattr(info, "get") else info["last_price"]
            if p is not None and np.isfinite(float(p)):
                return float(p), "Yahoo Finance"
        except Exception:
            pass
        hist = t.history(period="1d", interval="1m", auto_adjust=False, prepost=True)
        if hist.empty:
            hist = t.history(period="5d", interval="5m", auto_adjust=False, prepost=True)
        if not hist.empty:
            return float(hist["Close"].dropna().iloc[-1]), "Yahoo Finance"
        return None, "Nessun dato restituito da Yahoo Finance"
    except Exception as e:
        return None, f"Errore Yahoo Finance: {e}"


def fetch_intraday(ticker: str, start_dt: datetime) -> Tuple[pd.DataFrame, str]:
    """Scarica dati sufficientemente granulari per ricostruire l'ordine target/stop."""
    now = datetime.now(start_dt.tzinfo) if start_dt.tzinfo else datetime.now()
    age_days = max(0, (now - start_dt).days)
    if age_days <= 6:
        interval, period = "1m", "7d"
    elif age_days <= 58:
        interval, period = "5m", "60d"
    elif age_days <= 700:
        interval, period = "60m", "730d"
    else:
        interval, period = "1d", "max"

    df = yf.Ticker(ticker).history(period=period, interval=interval, auto_adjust=False, prepost=True)
    if df.empty:
        return df, interval

    # Confronto timezone robusto.
    idx = df.index
    try:
        if idx.tz is not None and start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=idx.tz)
        elif idx.tz is None and start_dt.tzinfo is not None:
            start_dt = start_dt.replace(tzinfo=None)
        elif idx.tz is not None and start_dt.tzinfo is not None:
            start_dt = start_dt.astimezone(idx.tz)
        df = df[df.index >= start_dt]
    except Exception:
        pass
    return df, interval


def evaluate_trade(row: sqlite3.Row) -> Dict[str, Optional[str]]:
    if not row["ticker"] or not row["entry_time"] or row["actual_entry"] is None or row["actual_stop"] is None:
        return {"status": row["status"], "outcome": row["outcome"], "note": "Dati trade incompleti"}

    try:
        start_dt = datetime.fromisoformat(row["entry_time"])
    except Exception:
        return {"status": row["status"], "outcome": row["outcome"], "note": "Ora ingresso non valida"}

    df, interval = fetch_intraday(row["ticker"], start_dt)
    if df.empty:
        return {"status": row["status"], "outcome": row["outcome"], "note": "Dati prezzo non disponibili"}

    direction = row["direction"].upper()
    stop = float(row["actual_stop"])
    t1 = float(row["t1"]) if row["t1"] is not None else None
    t2 = float(row["t2"]) if row["t2"] is not None else None

    t1_time = row["t1_hit_time"]
    t2_time = row["t2_hit_time"]
    stop_time = row["stop_hit_time"]
    t1_done = bool(t1_time)
    t2_done = bool(t2_time)

    for ts, bar in df.iterrows():
        high, low = float(bar["High"]), float(bar["Low"])
        if direction == "LONG":
            hit_stop = low <= stop
            hit_t1 = (t1 is not None and high >= t1 and not t1_done)
            hit_t2 = (t2 is not None and high >= t2 and not t2_done)
        else:
            hit_stop = high >= stop
            hit_t1 = (t1 is not None and low <= t1 and not t1_done)
            hit_t2 = (t2 is not None and low <= t2 and not t2_done)

        # Se nella stessa barra non sappiamo se sia avvenuto prima stop o nuovo target.
        if hit_stop and (hit_t1 or hit_t2):
            status = "AMBIGUO"
            outcome = "AMBIGUO DOPO T1" if t1_done else "AMBIGUO"
            return {
                "status": status,
                "outcome": outcome,
                "t1_hit_time": t1_time,
                "t2_hit_time": t2_time,
                "stop_hit_time": stop_time,
                "note": f"Stop e target nella stessa barra {interval}; ordine non determinabile."
            }

        if hit_t1:
            t1_done = True
            t1_time = ts.isoformat()

        if hit_t2:
            t2_done = True
            t2_time = ts.isoformat()
            return {
                "status": "CHIUSO",
                "outcome": "T2",
                "t1_hit_time": t1_time,
                "t2_hit_time": t2_time,
                "stop_hit_time": stop_time,
                "note": f"T2 raggiunto; controllo con barre {interval}."
            }

        if hit_stop:
            stop_time = ts.isoformat()
            return {
                "status": "CHIUSO",
                "outcome": "T1 + STOP" if t1_done else "STOP",
                "t1_hit_time": t1_time,
                "t2_hit_time": t2_time,
                "stop_hit_time": stop_time,
                "note": f"Stop raggiunto; controllo con barre {interval}."
            }

    if t1_done:
        return {
            "status": "T1 RAGGIUNTO",
            "outcome": "T1 APERTO",
            "t1_hit_time": t1_time,
            "t2_hit_time": t2_time,
            "stop_hit_time": stop_time,
            "note": f"T1 raggiunto, trade ancora da monitorare; barre {interval}."
        }
    return {
        "status": "IN TRADE",
        "outcome": None,
        "t1_hit_time": t1_time,
        "t2_hit_time": t2_time,
        "stop_hit_time": stop_time,
        "note": f"Nessun livello finale raggiunto; barre {interval}."
    }


def update_all_open_trades() -> Tuple[int, List[str]]:
    df = load_signals("status IN ('IN TRADE','T1 RAGGIUNTO')")
    updated = 0
    notes = []
    for _, r in df.iterrows():
        row = load_signal(int(r["id"]))
        if row is None:
            continue
        try:
            res = evaluate_trade(row)
            update_signal(
                int(row["id"]),
                status=res.get("status") or row["status"],
                outcome=res.get("outcome"),
                t1_hit_time=res.get("t1_hit_time"),
                t2_hit_time=res.get("t2_hit_time"),
                stop_hit_time=res.get("stop_hit_time"),
                result_note=res.get("note", ""),
                last_check=now_iso(),
            )
            updated += 1
        except Exception as e:
            notes.append(f"#{int(r['id'])}: {e}")
    return updated, notes


def dataframe_for_display(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    for c in ["e1", "s1", "e2", "s2", "t1", "t2", "actual_entry", "actual_stop"]:
        if c in out.columns:
            out[c] = out[c].map(lambda x: "—" if pd.isna(x) else fmt_num(x))
    if "confirmations" in out.columns:
        out["confirmations"] = out["confirmations"].map(
            lambda x: ", ".join(json.loads(x)) if isinstance(x, str) and x.startswith("[") else (x or "")
        )
    cols = [
        "id", "valid_date", "instrument", "direction", "e1", "e2", "t1", "t2",
        "setup_origin", "confirmations", "actual_entry", "actual_stop", "status", "outcome"
    ]
    return out[[c for c in cols if c in out.columns]].rename(columns={
        "id": "ID", "valid_date": "Data", "instrument": "Strumento", "direction": "Dir.",
        "e1": "E1", "e2": "E2", "t1": "T1", "t2": "T2", "setup_origin": "Origine",
        "confirmations": "Conferme", "actual_entry": "Entry reale", "actual_stop": "Stop reale",
        "status": "Stato", "outcome": "Esito"
    })


def excel_bytes(df: pd.DataFrame) -> bytes:
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Segnali")
    return bio.getvalue()


def to_float_field(label: str, value: Optional[float], key: str) -> Optional[float]:
    raw = st.text_input(label, value=fmt_num(value), key=key)
    if not raw.strip():
        return None
    val = normalize_number(raw)
    if val is None:
        st.error(f"Valore non valido per {label}: {raw}")
    return val


@st.dialog("Screenshot del segnale", width="large")
def open_signal_image_dialog(image_path: str, signal_label: str = "") -> None:
    """Apre lo screenshot salvato in una finestra ampia per studio/consultazione."""
    path = Path(image_path) if image_path else None
    if not path or not path.exists():
        st.warning("Immagine non disponibile. Su Streamlit Cloud i file locali possono scomparire dopo un riavvio/deploy.")
        return

    st.image(str(path), caption=signal_label or path.name, use_container_width=True)
    st.caption("Puoi usare lo zoom del browser per osservare meglio i dettagli del grafico.")
    try:
        raw = path.read_bytes()
        mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }.get(path.suffix.lower(), "application/octet-stream")
        st.download_button(
            "⬇️ Scarica immagine originale",
            data=raw,
            file_name=path.name,
            mime=mime,
            use_container_width=True,
        )
    except Exception:
        pass


def image_open_button(image_path: str, signal_label: str, key: str, use_container_width: bool = True) -> None:
    """Mostra un pulsante esplicito per aprire lo screenshot associato al segnale."""
    if image_path and Path(image_path).exists():
        if st.button("🖼️ Apri immagine per studio", key=key, use_container_width=use_container_width):
            open_signal_image_dialog(image_path, signal_label)
    else:
        st.caption("🖼️ Immagine del segnale non disponibile.")


def page_new_signal() -> None:
    st.subheader("Nuovo segnale da screenshot")
    st.caption("Lo screenshot viene letto automaticamente; prima del salvataggio puoi correggere qualsiasi campo.")

    uploaded = st.file_uploader("Carica screenshot Telegram / TradingView", type=["png", "jpg", "jpeg", "webp"])
    if not uploaded:
        st.info("Carica uno screenshot per iniziare.")
        return

    raw = uploaded.getvalue()
    file_hash = hashlib.sha1(raw).hexdigest()
    if st.session_state.get("ocr_hash") != file_hash:
        st.session_state["ocr_hash"] = file_hash
        st.session_state["ocr_data"] = None
        st.session_state["ocr_error"] = None

    img = Image.open(io.BytesIO(raw)).convert("RGB")
    st.image(img, caption=f"Anteprima · {uploaded.name}", use_container_width=True)

    if st.button("🔎 Leggi screenshot", type="primary"):
        try:
            with st.spinner("Lettura OCR in corso..."):
                full_text, top_text = run_ocr(img)
                parsed = parse_signal(full_text, top_text)
                st.session_state["ocr_data"] = {**parsed, "full_text": full_text, "top_text": top_text}
                st.session_state["ocr_error"] = None
        except Exception as e:
            st.session_state["ocr_error"] = str(e)

    if st.session_state.get("ocr_error"):
        st.error(st.session_state["ocr_error"])
        st.caption("Puoi comunque proseguire inserendo i dati manualmente.")

    ocr = st.session_state.get("ocr_data") or {
        "valid_date": None, "instrument": "", "ticker": "", "direction": "",
        "e1": None, "s1": None, "e2": None, "s2": None, "t1": None, "t2": None,
        "full_text": "", "top_text": ""
    }

    with st.form("signal_form"):
        st.markdown("#### 1. Segnale originale")
        c1, c2, c3 = st.columns(3)
        default_date = date.fromisoformat(ocr["valid_date"]) if ocr.get("valid_date") else date.today()
        valid_date = c1.date_input("Data di validità", value=default_date)
        instrument = c2.text_input("Strumento", value=ocr.get("instrument", ""))
        direction_options = ["LONG", "SHORT"]
        d_idx = 0 if ocr.get("direction") != "SHORT" else 1
        direction = c3.selectbox("Direzione", direction_options, index=d_idx)
        ticker = st.text_input("Ticker Yahoo Finance", value=ocr.get("ticker", ""), help="Esempio GOLD = GC=F, NASDAQ = NQ=F. Correggibile manualmente.")

        a1, a2, a3, a4 = st.columns(4)
        e1 = normalize_number(a1.text_input("E1 indicativa", fmt_num(ocr.get("e1"))))
        s1 = normalize_number(a2.text_input("S1 indicativo", fmt_num(ocr.get("s1"))))
        e2 = normalize_number(a3.text_input("E2 indicativa", fmt_num(ocr.get("e2"))))
        s2 = normalize_number(a4.text_input("S2 indicativo", fmt_num(ocr.get("s2"))))
        b1, b2 = st.columns(2)
        t1 = normalize_number(b1.text_input("T1", fmt_num(ocr.get("t1"))))
        t2 = normalize_number(b2.text_input("T2", fmt_num(ocr.get("t2"))))

        st.markdown("#### 2. Contesto del setup — facoltativo")
        c1, c2, c3 = st.columns(3)
        setup_origin = c1.selectbox("Origine del setup", SETUP_ORIGINS)
        reference_area = c2.text_input("Livello / area Balance o svolta", placeholder="es. 4365–4398")
        setup_tf = c3.selectbox("Timeframe del riferimento", TIMEFRAMES)

        st.markdown("**Conferme osservate — tutte facoltative**")
        cols = st.columns(4)
        confirmations = []
        for i, name in enumerate(CONFIRMATIONS):
            if cols[i % 4].checkbox(name, key=f"new_conf_{i}"):
                confirmations.append(name)
        notes = st.text_area("Note / motivazione del setup", placeholder="Scrivi solo se serve. Campo facoltativo.")

        submitted = st.form_submit_button("💾 Salva segnale", type="primary", use_container_width=True)

    if submitted:
        errors = []
        if not instrument.strip():
            errors.append("strumento")
        if not direction:
            errors.append("direzione")
        if t1 is None:
            errors.append("T1")
        if errors:
            st.error("Campi necessari mancanti: " + ", ".join(errors))
            return

        screenshot_path = save_screenshot(uploaded)
        signal_id = insert_signal({
            "valid_date": valid_date.isoformat(),
            "instrument": instrument.strip(),
            "ticker": ticker.strip(),
            "direction": direction,
            "e1": e1, "s1": s1, "e2": e2, "s2": s2, "t1": t1, "t2": t2,
            "setup_origin": setup_origin,
            "reference_area": reference_area.strip(),
            "setup_timeframe": setup_tf,
            "confirmations": confirmations,
            "notes": notes.strip(),
            "screenshot_path": screenshot_path,
            "ocr_text": (ocr.get("top_text", "") + "\n" + ocr.get("full_text", "")).strip(),
        })
        st.success(f"Segnale #{signal_id} salvato.")
        st.session_state["ocr_hash"] = None
        st.session_state["ocr_data"] = None

    if ocr.get("full_text"):
        with st.expander("Testo letto dall'OCR"):
            st.code((ocr.get("top_text", "") + "\n---\n" + ocr.get("full_text", "")).strip())


def page_manage() -> None:
    st.subheader("Gestione trade reale")
    df = load_signals("status NOT IN ('CHIUSO','NESSUN TRADE','ANNULLATO')")
    if df.empty:
        st.info("Non ci sono segnali aperti da gestire.")
        return

    labels = {
        int(r["id"]): f"#{int(r['id'])} · {r['valid_date']} · {r['instrument']} · {r['direction']} · {r['status']}"
        for _, r in df.iterrows()
    }
    selected_id = st.selectbox("Seleziona segnale", list(labels.keys()), format_func=lambda x: labels[x])
    row = load_signal(int(selected_id))
    if row is None:
        return

    col_a, col_b = st.columns([2, 1])
    with col_a:
        st.markdown(f"### {row['instrument']} — {row['direction']}")
        st.write(f"**Data:** {row['valid_date']}  |  **Stato:** {row['status']}")
        st.write(
            f"**E1:** {fmt_num(row['e1']) or '—'} · **S1:** {fmt_num(row['s1']) or '—'} · "
            f"**E2:** {fmt_num(row['e2']) or '—'} · **S2:** {fmt_num(row['s2']) or '—'}"
        )
        st.write(f"**T1:** {fmt_num(row['t1']) or '—'} · **T2:** {fmt_num(row['t2']) or '—'}")
        conf = json.loads(row["confirmations"] or "[]")
        st.write(f"**Origine:** {row['setup_origin'] or '—'} · **Riferimento:** {row['reference_area'] or '—'} · **TF:** {row['setup_timeframe'] or '—'}")
        st.write(f"**Conferme:** {', '.join(conf) if conf else '—'}")
        if row["notes"]:
            st.info(row["notes"])
        image_open_button(
            row["screenshot_path"] or "",
            f"Segnale #{selected_id} · {row['instrument']} · {row['direction']} · {row['valid_date']}",
            key=f"open_img_manage_{selected_id}",
            use_container_width=False,
        )

    live_price = None
    with col_b:
        if st.button("💹 Leggi prezzo attuale", use_container_width=True):
            with st.spinner("Recupero prezzo..."):
                live_price, src = get_current_price(row["ticker"] or "")
            if live_price is not None:
                st.metric("Prezzo attuale", fmt_num(live_price))
                st.caption(src + " · dato indicativo, può essere ritardato")
                st.session_state[f"live_{selected_id}"] = live_price
            else:
                st.warning(src)
        elif f"live_{selected_id}" in st.session_state:
            live_price = st.session_state[f"live_{selected_id}"]
            st.metric("Ultimo prezzo letto", fmt_num(live_price))

    if row["status"] == "PUBBLICATO":
        st.markdown("#### Registra ingresso effettivo")
        suggested = st.session_state.get(f"live_{selected_id}")
        with st.form(f"entry_form_{selected_id}"):
            c1, c2 = st.columns(2)
            entry_raw = c1.text_input("Entry effettiva", value=fmt_num(suggested), help="Puoi usare il prezzo live come proposta o inserire il prezzo reale.")
            stop_raw = c2.text_input("Stop effettivo", value="")
            dtc1, dtc2 = st.columns(2)
            entry_date = dtc1.date_input("Data ingresso", value=date.today())
            entry_time_value = dtc2.time_input("Ora ingresso", value=datetime.now().time().replace(microsecond=0))
            register = st.form_submit_button("🟢 REGISTRA INGRESSO", type="primary", use_container_width=True)
        if register:
            entry = normalize_number(entry_raw)
            stop = normalize_number(stop_raw)
            entry_dt = datetime.combine(entry_date, entry_time_value)
            if entry is None or stop is None:
                st.error("Inserisci Entry effettiva e Stop effettivo validi.")
            else:
                update_signal(
                    int(selected_id),
                    actual_entry=entry,
                    actual_stop=stop,
                    entry_time=entry_dt.isoformat(timespec="seconds"),
                    status="IN TRADE",
                    outcome=None,
                    result_note="Ingresso reale registrato",
                )
                st.success("Ingresso reale registrato. Da ora il trade può essere monitorato automaticamente.")
                st.rerun()

        c1, c2 = st.columns(2)
        if c1.button("⚪ NESSUN TRADE", use_container_width=True):
            update_signal(int(selected_id), status="NESSUN TRADE", outcome="NESSUN TRADE", result_note="Segnale non eseguito")
            st.rerun()
        if c2.button("⛔ SETUP ANNULLATO", use_container_width=True):
            update_signal(int(selected_id), status="ANNULLATO", outcome="ANNULLATO", result_note="Setup annullato")
            st.rerun()
    else:
        st.markdown("#### Trade in monitoraggio")
        st.write(f"**Entry reale:** {fmt_num(row['actual_entry'])} · **Stop reale:** {fmt_num(row['actual_stop'])}")
        st.write(f"**Ora ingresso:** {row['entry_time'] or '—'}")
        if row["t1_hit_time"]:
            st.success(f"T1 raggiunto: {row['t1_hit_time']}")
        if st.button("🔄 Aggiorna questo trade", type="primary"):
            with st.spinner("Controllo sequenza prezzi..."):
                try:
                    res = evaluate_trade(row)
                    update_signal(
                        int(selected_id),
                        status=res.get("status") or row["status"],
                        outcome=res.get("outcome"),
                        t1_hit_time=res.get("t1_hit_time"),
                        t2_hit_time=res.get("t2_hit_time"),
                        stop_hit_time=res.get("stop_hit_time"),
                        result_note=res.get("note", ""),
                        last_check=now_iso(),
                    )
                    st.success(res.get("note", "Aggiornato"))
                    st.rerun()
                except Exception as e:
                    st.error(str(e))


def page_dashboard() -> None:
    st.subheader("Dashboard")
    df = load_signals()
    if df.empty:
        st.info("Nessun segnale salvato.")
        return

    total = len(df)
    traded = int(df["actual_entry"].notna().sum())
    no_trade = int(df["status"].isin(["NESSUN TRADE", "ANNULLATO"]).sum())
    t1_success = int(df["outcome"].isin(["T2", "T1 + STOP", "T1 APERTO"]).sum())
    stopped_before_t1 = int((df["outcome"] == "STOP").sum())
    resolved_for_wr = t1_success + stopped_before_t1
    wr = (100 * t1_success / resolved_for_wr) if resolved_for_wr else 0.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Segnali pubblicati", total)
    c2.metric("Trade eseguiti", traded)
    c3.metric("Nessun trade / annullati", no_trade)
    c4.metric("Win Rate base", f"{wr:.1f}%", help="T1 raggiunto prima dello Stop / trade già risolti. Non è ancora una misura di P&L.")

    if st.button("🔄 Aggiorna tutti i trade aperti"):
        with st.spinner("Controllo trade aperti..."):
            updated, notes = update_all_open_trades()
        st.success(f"Controllati {updated} trade.")
        if notes:
            st.warning("\n".join(notes))
        st.rerun()

    st.dataframe(dataframe_for_display(df), use_container_width=True, hide_index=True)

    st.download_button(
        "⬇️ Esporta storico Excel",
        data=excel_bytes(df),
        file_name=f"signal_tracker_{date.today().isoformat()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def explode_confirmations(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in df.iterrows():
        try:
            confs = json.loads(r["confirmations"] or "[]")
        except Exception:
            confs = []
        for c in confs:
            rows.append({"confirmation": c, "outcome": r["outcome"], "traded": pd.notna(r["actual_entry"])})
    return pd.DataFrame(rows)


def page_stats() -> None:
    st.subheader("Statistiche")
    df = load_signals()
    if df.empty:
        st.info("Servono segnali salvati per costruire le statistiche.")
        return

    traded = df[df["actual_entry"].notna()].copy()
    resolved = traded[traded["outcome"].isin(["T2", "T1 + STOP", "STOP"])].copy()
    if resolved.empty:
        st.info("Non ci sono ancora abbastanza trade risolti per statistiche operative affidabili.")
    else:
        resolved["win_t1"] = resolved["outcome"].isin(["T2", "T1 + STOP"]).astype(int)
        resolved["t2_hit"] = (resolved["outcome"] == "T2").astype(int)
        c1, c2, c3 = st.columns(3)
        c1.metric("Trade risolti", len(resolved))
        c2.metric("T1 prima dello Stop", f"{resolved['win_t1'].mean()*100:.1f}%")
        c3.metric("T2 raggiunto", f"{resolved['t2_hit'].mean()*100:.1f}%")

        st.markdown("#### Risultati per origine del setup")
        by_origin = (
            resolved.groupby("setup_origin", dropna=False)
            .agg(Trade=("id", "count"), WinRate_T1=("win_t1", "mean"), T2=("t2_hit", "mean"))
            .reset_index()
        )
        by_origin["WinRate_T1"] = (by_origin["WinRate_T1"] * 100).round(1)
        by_origin["T2"] = (by_origin["T2"] * 100).round(1)
        st.dataframe(by_origin, use_container_width=True, hide_index=True)

        st.markdown("#### Risultati per strumento")
        by_instr = (
            resolved.groupby("instrument")
            .agg(Trade=("id", "count"), WinRate_T1=("win_t1", "mean"), T2=("t2_hit", "mean"))
            .reset_index()
            .sort_values(["Trade", "WinRate_T1"], ascending=[False, False])
        )
        by_instr["WinRate_T1"] = (by_instr["WinRate_T1"] * 100).round(1)
        by_instr["T2"] = (by_instr["T2"] * 100).round(1)
        st.dataframe(by_instr, use_container_width=True, hide_index=True)

        st.markdown("#### Conferme osservate")
        ex = explode_confirmations(resolved)
        if ex.empty:
            st.caption("Nessuna conferma facoltativa registrata nei trade risolti.")
        else:
            # Ricostruisce win per outcome per ogni flag.
            ex["win_t1"] = ex["outcome"].isin(["T2", "T1 + STOP"]).astype(int)
            ex["t2_hit"] = (ex["outcome"] == "T2").astype(int)
            by_conf = (
                ex.groupby("confirmation")
                .agg(Presenze=("confirmation", "size"), WinRate_T1=("win_t1", "mean"), T2=("t2_hit", "mean"))
                .reset_index()
                .sort_values("Presenze", ascending=False)
            )
            by_conf["WinRate_T1"] = (by_conf["WinRate_T1"] * 100).round(1)
            by_conf["T2"] = (by_conf["T2"] * 100).round(1)
            st.dataframe(by_conf, use_container_width=True, hide_index=True)

    st.markdown("#### Nota metodologica")
    st.caption(
        "Il Win Rate base considera vincente un trade in cui T1 viene raggiunto prima dello Stop. "
        "E1/E2 e S1/S2 restano livelli indicativi del segnale originale e non vengono usati come esecuzioni reali. "
        "I casi in cui stop e target ricadono nella stessa barra vengono marcati AMBIGUI invece di forzare un risultato."
    )


def page_archive() -> None:
    st.subheader("Archivio segnali")
    df = load_signals()
    if df.empty:
        st.info("Archivio vuoto.")
        return

    c1, c2, c3 = st.columns(3)
    dir_filter = c1.selectbox("Direzione", ["TUTTE", "LONG", "SHORT"])
    status_values = ["TUTTI"] + sorted([x for x in df["status"].dropna().unique().tolist()])
    status_filter = c2.selectbox("Stato", status_values)
    instrument_values = ["TUTTI"] + sorted(df["instrument"].dropna().unique().tolist())
    instrument_filter = c3.selectbox("Strumento", instrument_values)

    f = df.copy()
    if dir_filter != "TUTTE":
        f = f[f["direction"] == dir_filter]
    if status_filter != "TUTTI":
        f = f[f["status"] == status_filter]
    if instrument_filter != "TUTTI":
        f = f[f["instrument"] == instrument_filter]

    st.dataframe(dataframe_for_display(f), use_container_width=True, hide_index=True)

    ids = f["id"].astype(int).tolist()
    if ids:
        sid = st.selectbox("Apri dettaglio segnale", ids, format_func=lambda x: f"Segnale #{x}")
        row = load_signal(int(sid))
        if row:
            image_open_button(
                row["screenshot_path"] or "",
                f"Segnale #{sid} · {row['instrument']} · {row['direction']} · {row['valid_date']}",
                key=f"open_img_archive_{sid}",
            )
            with st.expander("Dettaglio completo", expanded=False):
                st.json({k: row[k] for k in row.keys() if k not in {"ocr_text"}}, expanded=False)
                if row["screenshot_path"] and Path(row["screenshot_path"]).exists():
                    st.image(row["screenshot_path"], caption=f"Anteprima screenshot segnale #{sid}", use_container_width=True)
                if row["ocr_text"]:
                    st.code(row["ocr_text"])


def page_info() -> None:
    st.subheader("Impostazione del metodo")
    st.markdown(
        """
        **Principio della V1**

        - **Contesto**: Balance / Punto di svolta / entrambi, con eventuali conferme facoltative.
        - **Segnale originale**: E1/E2 e S1/S2 sono riferimenti indicativi definiti prima della giornata operativa.
        - **Trade reale**: Entry effettiva e Stop effettivo vengono registrati quando la dinamica del mercato dà l'ingresso.
        - **Nessun trade**: se non compare un ingresso valido, il segnale non viene classificato come perdita.
        - **Statistiche**: vengono separate la qualità dell'idea iniziale e l'efficacia dei trade realmente eseguiti.

        **Persistenza dati**

        La V1 usa un database SQLite locale (`data/signals.db`). È ideale per uso locale. Su Streamlit Community Cloud
        il filesystem dell'app può essere ricreato dopo riavvii/deploy: per uso condiviso stabile la fase successiva sarà
        collegare un database persistente (es. Supabase/PostgreSQL) senza cambiare il modello dei segnali.
        """
    )


st.set_page_config(page_title=f"{APP_NAME} {APP_VERSION}", page_icon="📊", layout="wide")
init_db()

st.title(f"📊 {APP_NAME} {APP_VERSION}")
st.caption("Screenshot → segnale strutturato → trade reale → monitoraggio → statistiche")

with st.sidebar:
    st.markdown(f"### {APP_NAME}")
    page = st.radio(
        "Sezione",
        ["Dashboard", "Carica nuovo segnale", "Gestione trade", "Statistiche", "Archivio", "Info"],
    )
    st.divider()
    st.caption("E1/E2 = livelli indicativi. Il Win Rate operativo usa Entry e Stop reali.")

if page == "Dashboard":
    page_dashboard()
elif page == "Carica nuovo segnale":
    page_new_signal()
elif page == "Gestione trade":
    page_manage()
elif page == "Statistiche":
    page_stats()
elif page == "Archivio":
    page_archive()
else:
    page_info()
