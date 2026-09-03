from __future__ import annotations

import io
import hashlib
import re
import shutil
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image, ImageOps, ImageEnhance
import pytesseract
import yfinance as yf
from supabase import create_client, Client

APP_NAME = "G. Signal Tracker"
APP_VERSION = "V1.3"
BUCKET_NAME = "signal-screenshots"
LOCAL_TZ = ZoneInfo("Europe/Rome")

ROLE_LABELS = {
    "admin": "Amministratore",
    "collaborator": "Collaboratore",
    "viewer": "Solo lettura",
}
WRITE_ROLES = {"admin", "collaborator"}

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


# -----------------------------------------------------------------------------
# Configurazione Supabase / autenticazione
# -----------------------------------------------------------------------------

def get_secret(name: str, default: str = "") -> str:
    try:
        cfg = st.secrets.get("supabase", {})
        value = cfg.get(name, default)
        return str(value).strip() if value is not None else default
    except Exception:
        return default


def supabase_config() -> Dict[str, str]:
    return {
        "url": get_secret("url"),
        "anon_key": get_secret("anon_key") or get_secret("publishable_key"),
        "service_role_key": get_secret("service_role_key") or get_secret("secret_key"),
        "admin_email": get_secret("admin_email").lower(),
    }


def config_ready() -> bool:
    cfg = supabase_config()
    return bool(cfg["url"] and cfg["anon_key"])


def service_client() -> Optional[Client]:
    cfg = supabase_config()
    if not cfg["url"] or not cfg["service_role_key"]:
        return None
    return create_client(cfg["url"], cfg["service_role_key"])


def user_client() -> Client:
    client = st.session_state.get("sb_user_client")
    if client is None:
        raise RuntimeError("Sessione Supabase non disponibile. Effettua nuovamente il login.")
    return client


def current_user_id() -> str:
    return str(st.session_state.get("user_id", ""))


def current_email() -> str:
    return str(st.session_state.get("user_email", ""))


def current_role() -> str:
    return str(st.session_state.get("user_role", ""))


def can_write() -> bool:
    return current_role() in WRITE_ROLES


def is_admin() -> bool:
    return current_role() == "admin"


def clear_auth_state() -> None:
    for key in ["sb_user_client", "user_id", "user_email", "user_role"]:
        st.session_state.pop(key, None)


def fetch_own_role(client: Client, user_id: str) -> Optional[Dict[str, Any]]:
    res = client.table("app_users").select("user_id,email,role,active").eq("user_id", user_id).limit(1).execute()
    rows = res.data or []
    return rows[0] if rows else None


def bootstrap_first_admin(user_id: str, email: str) -> Optional[Dict[str, Any]]:
    cfg = supabase_config()
    if not cfg["admin_email"] or email.lower() != cfg["admin_email"]:
        return None
    admin = service_client()
    if admin is None:
        return None
    admin.table("app_users").upsert(
        {"user_id": user_id, "email": email.lower(), "role": "admin", "active": True},
        on_conflict="user_id",
    ).execute()
    return {"user_id": user_id, "email": email.lower(), "role": "admin", "active": True}


def perform_login(email: str, password: str) -> Tuple[bool, str]:
    cfg = supabase_config()
    try:
        client = create_client(cfg["url"], cfg["anon_key"])
        auth = client.auth.sign_in_with_password({"email": email.strip(), "password": password})
        user = getattr(auth, "user", None)
        if user is None:
            return False, "Login non riuscito."
        uid = str(getattr(user, "id", ""))
        uemail = str(getattr(user, "email", email)).lower()
        role_row = fetch_own_role(client, uid)
        if role_row is None:
            role_row = bootstrap_first_admin(uid, uemail)
        if role_row is None or not bool(role_row.get("active", False)):
            try:
                client.auth.sign_out()
            except Exception:
                pass
            return False, "Utente autenticato ma non autorizzato all'app. Chiedi all'amministratore di abilitarlo."

        st.session_state["sb_user_client"] = client
        st.session_state["user_id"] = uid
        st.session_state["user_email"] = uemail
        st.session_state["user_role"] = str(role_row.get("role", "viewer"))
        return True, "Accesso eseguito."
    except Exception as e:
        return False, f"Accesso non riuscito: {e}"


def show_login() -> None:
    st.title(f"📊 {APP_NAME} {APP_VERSION}")
    st.caption("Archivio condiviso e persistente · accesso riservato")
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("🔐 Accedi", type="primary", use_container_width=True)
    if submitted:
        ok, msg = perform_login(email, password)
        if ok:
            st.success(msg)
            st.rerun()
        else:
            st.error(msg)


def change_password_box() -> None:
    with st.expander("🔑 Cambia password"):
        p1 = st.text_input("Nuova password", type="password", key="new_pwd_1")
        p2 = st.text_input("Ripeti nuova password", type="password", key="new_pwd_2")
        if st.button("Aggiorna password", use_container_width=True):
            if len(p1) < 8:
                st.error("Usa una password di almeno 8 caratteri.")
            elif p1 != p2:
                st.error("Le password non coincidono.")
            else:
                try:
                    user_client().auth.update_user({"password": p1})
                    st.success("Password aggiornata.")
                except Exception as e:
                    st.error(f"Impossibile aggiornare la password: {e}")


# -----------------------------------------------------------------------------
# Utilità generali / OCR
# -----------------------------------------------------------------------------

def local_now() -> datetime:
    return datetime.now(LOCAL_TZ)


def now_iso() -> str:
    return local_now().isoformat(timespec="seconds")


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
    return ImageEnhance.Contrast(gray).enhance(contrast)


def run_ocr(img: Image.Image) -> Tuple[str, str]:
    if not configure_tesseract():
        raise RuntimeError(
            "OCR non disponibile: su Streamlit Community Cloud serve packages.txt con la riga tesseract-ocr."
        )
    full = preprocess_for_ocr(img, scale=2, contrast=2.2)
    full_text = pytesseract.image_to_string(full, config="--psm 11")
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
    aliases = {
        "E1": r"(?:E|£)\s*1",
        "E2": r"(?:E|£)\s*2",
        "S1": r"(?:S|\$)\s*1",
        "S2": r"(?:S|\$)\s*2",
        "T1": r"T\s*1",
        "T2": r"T\s*2",
    }
    m = re.search(aliases[tag] + r"\s*[:=]?\s*([0-9][0-9.,]*)", text, flags=re.I)
    return normalize_number(m.group(1)) if m else None


def infer_instrument(top_text: str, full_text: str) -> Tuple[str, str]:
    txt = (top_text + "\n" + full_text).lower()
    for key in sorted(INSTRUMENT_ALIASES, key=len, reverse=True):
        if re.search(r"(?<![a-z0-9])" + re.escape(key) + r"(?![a-z0-9])", txt):
            return INSTRUMENT_ALIASES[key]
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


# -----------------------------------------------------------------------------
# Supabase: database + storage persistente
# -----------------------------------------------------------------------------

def confirmations_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(x) for x in value]
    if isinstance(value, str) and value.strip():
        try:
            parsed = __import__("json").loads(value)
            return [str(x) for x in parsed] if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def upload_screenshot(uploaded_file) -> str:
    raw = uploaded_file.getvalue()
    digest = hashlib.sha1(raw).hexdigest()[:12]
    suffix = Path(uploaded_file.name).suffix.lower() or ".png"
    user_folder = current_user_id() or "unknown"
    path = f"{user_folder}/{local_now():%Y%m%d_%H%M%S}_{digest}{suffix}"
    mime = uploaded_file.type or {
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"
    }.get(suffix, "application/octet-stream")
    user_client().storage.from_(BUCKET_NAME).upload(
        path=path,
        file=raw,
        file_options={"content-type": mime, "upsert": "false"},
    )
    return path


def remove_screenshot(storage_path: str) -> None:
    if not storage_path:
        return
    try:
        user_client().storage.from_(BUCKET_NAME).remove([storage_path])
    except Exception:
        pass


def download_screenshot(storage_path: str) -> Optional[bytes]:
    if not storage_path:
        return None
    try:
        return user_client().storage.from_(BUCKET_NAME).download(storage_path)
    except Exception:
        return None


def insert_signal(data: Dict[str, Any]) -> int:
    payload = dict(data)
    payload["status"] = "PUBBLICATO"
    payload["created_by"] = current_user_id()
    payload["updated_by"] = current_user_id()
    res = user_client().table("signals").insert(payload).execute()
    rows = res.data or []
    if not rows:
        raise RuntimeError("Il database non ha restituito il segnale appena salvato.")
    return int(rows[0]["id"])


def load_signals() -> pd.DataFrame:
    res = user_client().table("signals").select("*").order("valid_date", desc=True).order("id", desc=True).execute()
    rows = res.data or []
    return pd.DataFrame(rows)


def load_signal(signal_id: int) -> Optional[Dict[str, Any]]:
    res = user_client().table("signals").select("*").eq("id", int(signal_id)).limit(1).execute()
    rows = res.data or []
    return rows[0] if rows else None


def update_signal(signal_id: int, **kwargs) -> None:
    if not kwargs:
        return
    kwargs["updated_by"] = current_user_id()
    kwargs["updated_at"] = now_iso()
    user_client().table("signals").update(kwargs).eq("id", int(signal_id)).execute()


# -----------------------------------------------------------------------------
# Dati mercato / monitoraggio trade
# -----------------------------------------------------------------------------

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


def evaluate_trade(row: Dict[str, Any]) -> Dict[str, Optional[str]]:
    if not row.get("ticker") or not row.get("entry_time") or row.get("actual_entry") is None or row.get("actual_stop") is None:
        return {"status": row.get("status"), "outcome": row.get("outcome"), "note": "Dati trade incompleti"}
    try:
        start_dt = datetime.fromisoformat(str(row["entry_time"]).replace("Z", "+00:00"))
    except Exception:
        return {"status": row.get("status"), "outcome": row.get("outcome"), "note": "Ora ingresso non valida"}

    df, interval = fetch_intraday(str(row["ticker"]), start_dt)
    if df.empty:
        return {"status": row.get("status"), "outcome": row.get("outcome"), "note": "Dati prezzo non disponibili"}

    direction = str(row["direction"]).upper()
    stop = float(row["actual_stop"])
    t1 = float(row["t1"]) if row.get("t1") is not None else None
    t2 = float(row["t2"]) if row.get("t2") is not None else None
    t1_time = row.get("t1_hit_time")
    t2_time = row.get("t2_hit_time")
    stop_time = row.get("stop_hit_time")
    t1_done = bool(t1_time)
    t2_done = bool(t2_time)

    for ts, bar in df.iterrows():
        high, low = float(bar["High"]), float(bar["Low"])
        if direction == "LONG":
            hit_stop = low <= stop
            hit_t1 = t1 is not None and high >= t1 and not t1_done
            hit_t2 = t2 is not None and high >= t2 and not t2_done
        else:
            hit_stop = high >= stop
            hit_t1 = t1 is not None and low <= t1 and not t1_done
            hit_t2 = t2 is not None and low <= t2 and not t2_done

        if hit_stop and (hit_t1 or hit_t2):
            return {
                "status": "AMBIGUO",
                "outcome": "AMBIGUO DOPO T1" if t1_done else "AMBIGUO",
                "t1_hit_time": t1_time,
                "t2_hit_time": t2_time,
                "stop_hit_time": stop_time,
                "note": f"Stop e target nella stessa barra {interval}; ordine non determinabile.",
            }
        if hit_t1:
            t1_done = True
            t1_time = ts.isoformat()
        if hit_t2:
            t2_done = True
            t2_time = ts.isoformat()
            return {
                "status": "CHIUSO", "outcome": "T2", "t1_hit_time": t1_time,
                "t2_hit_time": t2_time, "stop_hit_time": stop_time,
                "note": f"T2 raggiunto; controllo con barre {interval}.",
            }
        if hit_stop:
            stop_time = ts.isoformat()
            return {
                "status": "CHIUSO", "outcome": "T1 + STOP" if t1_done else "STOP",
                "t1_hit_time": t1_time, "t2_hit_time": t2_time, "stop_hit_time": stop_time,
                "note": f"Stop raggiunto; controllo con barre {interval}.",
            }

    if t1_done:
        return {
            "status": "T1 RAGGIUNTO", "outcome": "T1 APERTO", "t1_hit_time": t1_time,
            "t2_hit_time": t2_time, "stop_hit_time": stop_time,
            "note": f"T1 raggiunto, trade ancora da monitorare; barre {interval}.",
        }
    return {
        "status": "IN TRADE", "outcome": None, "t1_hit_time": t1_time,
        "t2_hit_time": t2_time, "stop_hit_time": stop_time,
        "note": f"Nessun livello finale raggiunto; barre {interval}.",
    }


def update_all_open_trades() -> Tuple[int, List[str]]:
    df = load_signals()
    if df.empty:
        return 0, []
    df = df[df["status"].isin(["IN TRADE", "T1 RAGGIUNTO"])]
    updated = 0
    notes: List[str] = []
    for _, r in df.iterrows():
        row = load_signal(int(r["id"]))
        if row is None:
            continue
        try:
            res = evaluate_trade(row)
            update_signal(
                int(row["id"]),
                status=res.get("status") or row.get("status"),
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


# -----------------------------------------------------------------------------
# UI helpers
# -----------------------------------------------------------------------------

def dataframe_for_display(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    for c in ["e1", "s1", "e2", "s2", "t1", "t2", "actual_entry", "actual_stop"]:
        if c in out.columns:
            out[c] = out[c].map(lambda x: "—" if pd.isna(x) else fmt_num(x))
    if "confirmations" in out.columns:
        out["confirmations"] = out["confirmations"].map(lambda x: ", ".join(confirmations_list(x)))
    cols = [
        "id", "valid_date", "instrument", "direction", "e1", "e2", "t1", "t2",
        "setup_origin", "confirmations", "actual_entry", "actual_stop", "status", "outcome",
    ]
    return out[[c for c in cols if c in out.columns]].rename(columns={
        "id": "ID", "valid_date": "Data", "instrument": "Strumento", "direction": "Dir.",
        "e1": "E1", "e2": "E2", "t1": "T1", "t2": "T2", "setup_origin": "Origine",
        "confirmations": "Conferme", "actual_entry": "Entry reale", "actual_stop": "Stop reale",
        "status": "Stato", "outcome": "Esito",
    })


def excel_bytes(df: pd.DataFrame) -> bytes:
    export = df.copy()
    if "confirmations" in export.columns:
        export["confirmations"] = export["confirmations"].map(lambda x: ", ".join(confirmations_list(x)))
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine="openpyxl") as writer:
        export.to_excel(writer, index=False, sheet_name="Segnali")
    return bio.getvalue()


@st.dialog("Screenshot originale", width="large")
def open_signal_image_dialog(storage_path: str, signal_label: str = "") -> None:
    raw = download_screenshot(storage_path)
    if not raw:
        st.warning("Screenshot non disponibile nello Storage.")
        return
    suffix = Path(storage_path).suffix.lower()
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(
        suffix, "application/octet-stream"
    )
    st.image(raw, caption=signal_label or Path(storage_path).name, use_container_width=True)
    st.caption("Usa lo zoom del browser per osservare meglio i dettagli del grafico.")
    st.download_button(
        "⬇️ Scarica screenshot originale",
        data=raw,
        file_name=Path(storage_path).name,
        mime=mime,
        use_container_width=True,
    )


def image_open_button(storage_path: str, signal_label: str, key: str, use_container_width: bool = True) -> None:
    if storage_path:
        if st.button("🖼️ Apri screenshot originale", key=key, use_container_width=use_container_width):
            open_signal_image_dialog(storage_path, signal_label)
    else:
        st.caption("🖼️ Screenshot originale non disponibile.")


# -----------------------------------------------------------------------------
# Pagine
# -----------------------------------------------------------------------------

def page_new_signal() -> None:
    if not can_write():
        st.error("Il tuo profilo è in sola lettura.")
        return
    st.subheader("Carica nuovo segnale")
    st.caption("Carica lo screenshot; l'OCR compila i campi e puoi correggerli prima del salvataggio.")

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
        "full_text": "", "top_text": "",
    }

    with st.form("signal_form"):
        st.markdown("#### 1. Segnale originale")
        c1, c2, c3 = st.columns(3)
        default_date = date.fromisoformat(ocr["valid_date"]) if ocr.get("valid_date") else local_now().date()
        valid_date = c1.date_input("Data di validità", value=default_date)
        instrument = c2.text_input("Strumento", value=ocr.get("instrument", ""))
        d_idx = 0 if ocr.get("direction") != "SHORT" else 1
        direction = c3.selectbox("Direzione", ["LONG", "SHORT"], index=d_idx)
        ticker = st.text_input(
            "Ticker Yahoo Finance", value=ocr.get("ticker", ""),
            help="Esempio GOLD = GC=F, NASDAQ = NQ=F. Correggibile manualmente.",
        )

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
        confirmations: List[str] = []
        for i, name in enumerate(CONFIRMATIONS):
            if cols[i % 4].checkbox(name, key=f"new_conf_{i}"):
                confirmations.append(name)
        notes = st.text_area("Note / motivazione del setup", placeholder="Scrivi solo se serve. Campo facoltativo.")
        submitted = st.form_submit_button("💾 Salva segnale", type="primary", use_container_width=True)

    if submitted:
        errors = []
        if not instrument.strip():
            errors.append("strumento")
        if t1 is None:
            errors.append("T1")
        if errors:
            st.error("Campi necessari mancanti: " + ", ".join(errors))
            return

        screenshot_path = ""
        try:
            with st.spinner("Salvataggio permanente in corso..."):
                screenshot_path = upload_screenshot(uploaded)
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
            st.success(f"Segnale #{signal_id} salvato in modo persistente.")
            st.session_state["ocr_hash"] = None
            st.session_state["ocr_data"] = None
        except Exception as e:
            if screenshot_path:
                remove_screenshot(screenshot_path)
            st.error(f"Salvataggio non riuscito: {e}")

    if ocr.get("full_text"):
        with st.expander("Testo letto dall'OCR"):
            st.code((ocr.get("top_text", "") + "\n---\n" + ocr.get("full_text", "")).strip())


def page_manage() -> None:
    if not can_write():
        st.error("Il tuo profilo è in sola lettura.")
        return
    st.subheader("Gestione trade reale")
    df = load_signals()
    if df.empty:
        st.info("Non ci sono segnali aperti da gestire.")
        return
    df = df[~df["status"].isin(["CHIUSO", "NESSUN TRADE", "ANNULLATO"])]
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
            f"**E1:** {fmt_num(row.get('e1')) or '—'} · **S1:** {fmt_num(row.get('s1')) or '—'} · "
            f"**E2:** {fmt_num(row.get('e2')) or '—'} · **S2:** {fmt_num(row.get('s2')) or '—'}"
        )
        st.write(f"**T1:** {fmt_num(row.get('t1')) or '—'} · **T2:** {fmt_num(row.get('t2')) or '—'}")
        conf = confirmations_list(row.get("confirmations"))
        st.write(
            f"**Origine:** {row.get('setup_origin') or '—'} · **Riferimento:** {row.get('reference_area') or '—'} · "
            f"**TF:** {row.get('setup_timeframe') or '—'}"
        )
        st.write(f"**Conferme:** {', '.join(conf) if conf else '—'}")
        if row.get("notes"):
            st.info(row["notes"])
        image_open_button(
            row.get("screenshot_path") or "",
            f"Segnale #{selected_id} · {row['instrument']} · {row['direction']} · {row['valid_date']}",
            key=f"open_img_manage_{selected_id}",
            use_container_width=False,
        )

    live_price = None
    with col_b:
        if st.button("💹 Leggi prezzo attuale", use_container_width=True):
            with st.spinner("Recupero prezzo..."):
                live_price, src = get_current_price(row.get("ticker") or "")
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
            entry_raw = c1.text_input(
                "Entry effettiva", value=fmt_num(suggested),
                help="Puoi usare il prezzo live come proposta o inserire il prezzo reale.",
            )
            stop_raw = c2.text_input("Stop effettivo", value="")
            dtc1, dtc2 = st.columns(2)
            now = local_now()
            entry_date = dtc1.date_input("Data ingresso", value=now.date())
            entry_time_value = dtc2.time_input("Ora ingresso", value=now.time().replace(microsecond=0))
            register = st.form_submit_button("🟢 REGISTRA INGRESSO", type="primary", use_container_width=True)
        if register:
            entry = normalize_number(entry_raw)
            stop = normalize_number(stop_raw)
            entry_dt = datetime.combine(entry_date, entry_time_value, tzinfo=LOCAL_TZ)
            if entry is None or stop is None:
                st.error("Inserisci Entry effettiva e Stop effettivo validi.")
            else:
                update_signal(
                    int(selected_id), actual_entry=entry, actual_stop=stop,
                    entry_time=entry_dt.isoformat(timespec="seconds"), status="IN TRADE",
                    outcome=None, result_note="Ingresso reale registrato",
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
        st.write(f"**Entry reale:** {fmt_num(row.get('actual_entry'))} · **Stop reale:** {fmt_num(row.get('actual_stop'))}")
        st.write(f"**Ora ingresso:** {row.get('entry_time') or '—'}")
        if row.get("t1_hit_time"):
            st.success(f"T1 raggiunto: {row['t1_hit_time']}")
        if st.button("🔄 Aggiorna questo trade", type="primary"):
            with st.spinner("Controllo sequenza prezzi..."):
                try:
                    res = evaluate_trade(row)
                    update_signal(
                        int(selected_id), status=res.get("status") or row["status"], outcome=res.get("outcome"),
                        t1_hit_time=res.get("t1_hit_time"), t2_hit_time=res.get("t2_hit_time"),
                        stop_hit_time=res.get("stop_hit_time"), result_note=res.get("note", ""), last_check=now_iso(),
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
    traded = int(df["actual_entry"].notna().sum()) if "actual_entry" in df else 0
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

    if can_write() and st.button("🔄 Aggiorna tutti i trade aperti"):
        with st.spinner("Controllo trade aperti..."):
            updated, notes = update_all_open_trades()
        st.success(f"Controllati {updated} trade.")
        if notes:
            st.warning("\n".join(notes))
        st.rerun()

    st.dataframe(dataframe_for_display(df), use_container_width=True, hide_index=True)
    st.download_button(
        "⬇️ Esporta storico Excel", data=excel_bytes(df),
        file_name=f"signal_tracker_{local_now().date().isoformat()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def explode_confirmations(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in df.iterrows():
        for c in confirmations_list(r.get("confirmations")):
            rows.append({"confirmation": c, "outcome": r.get("outcome"), "traded": pd.notna(r.get("actual_entry"))})
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
        by_origin = resolved.groupby("setup_origin", dropna=False).agg(
            Trade=("id", "count"), WinRate_T1=("win_t1", "mean"), T2=("t2_hit", "mean")
        ).reset_index()
        by_origin["WinRate_T1"] = (by_origin["WinRate_T1"] * 100).round(1)
        by_origin["T2"] = (by_origin["T2"] * 100).round(1)
        st.dataframe(by_origin, use_container_width=True, hide_index=True)

        st.markdown("#### Risultati per strumento")
        by_instr = resolved.groupby("instrument").agg(
            Trade=("id", "count"), WinRate_T1=("win_t1", "mean"), T2=("t2_hit", "mean")
        ).reset_index().sort_values(["Trade", "WinRate_T1"], ascending=[False, False])
        by_instr["WinRate_T1"] = (by_instr["WinRate_T1"] * 100).round(1)
        by_instr["T2"] = (by_instr["T2"] * 100).round(1)
        st.dataframe(by_instr, use_container_width=True, hide_index=True)

        st.markdown("#### Conferme osservate")
        ex = explode_confirmations(resolved)
        if ex.empty:
            st.caption("Nessuna conferma facoltativa registrata nei trade risolti.")
        else:
            ex["win_t1"] = ex["outcome"].isin(["T2", "T1 + STOP"]).astype(int)
            ex["t2_hit"] = (ex["outcome"] == "T2").astype(int)
            by_conf = ex.groupby("confirmation").agg(
                Presenze=("confirmation", "size"), WinRate_T1=("win_t1", "mean"), T2=("t2_hit", "mean")
            ).reset_index().sort_values("Presenze", ascending=False)
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
                row.get("screenshot_path") or "",
                f"Segnale #{sid} · {row['instrument']} · {row['direction']} · {row['valid_date']}",
                key=f"open_img_archive_{sid}",
            )
            with st.expander("Dettaglio completo", expanded=False):
                clean = {k: v for k, v in row.items() if k not in {"ocr_text", "created_by", "updated_by"}}
                st.json(clean, expanded=False)
                if row.get("ocr_text"):
                    st.code(row["ocr_text"])


def page_users() -> None:
    if not is_admin():
        st.error("Sezione riservata all'amministratore.")
        return
    admin = service_client()
    if admin is None:
        st.error("Manca service_role_key nei Secrets di Streamlit. Senza questa chiave non puoi gestire gli utenti dall'app.")
        return

    st.subheader("Gestione utenti")
    st.caption("Crea colleghi autorizzati e assegna il livello di accesso. Le password temporanee vanno condivise in modo privato.")

    with st.form("create_user_form"):
        c1, c2 = st.columns(2)
        email = c1.text_input("Email nuovo utente")
        role = c2.selectbox("Ruolo", ["collaborator", "viewer"], format_func=lambda x: ROLE_LABELS[x])
        temp_password = st.text_input("Password temporanea", type="password", help="Minimo 8 caratteri. L'utente potrà cambiarla dopo l'accesso.")
        create = st.form_submit_button("➕ Crea utente", type="primary", use_container_width=True)
    if create:
        if "@" not in email or len(temp_password) < 8:
            st.error("Inserisci un'email valida e una password temporanea di almeno 8 caratteri.")
        else:
            try:
                resp = admin.auth.admin.create_user({
                    "email": email.strip().lower(),
                    "password": temp_password,
                    "email_confirm": True,
                })
                new_user = getattr(resp, "user", None)
                uid = str(getattr(new_user, "id", ""))
                if not uid:
                    raise RuntimeError("Supabase non ha restituito l'ID del nuovo utente.")
                admin.table("app_users").upsert({
                    "user_id": uid, "email": email.strip().lower(), "role": role, "active": True,
                }, on_conflict="user_id").execute()
                st.success(f"Utente {email.strip().lower()} creato come {ROLE_LABELS[role]}.")
                st.rerun()
            except Exception as e:
                st.error(f"Creazione non riuscita: {e}")

    res = admin.table("app_users").select("user_id,email,role,active,created_at").order("email").execute()
    users = res.data or []
    if users:
        display = pd.DataFrame(users)
        if "role" in display:
            display["role"] = display["role"].map(lambda x: ROLE_LABELS.get(str(x), str(x)))
        display = display.rename(columns={"email": "Email", "role": "Ruolo", "active": "Attivo", "created_at": "Creato"})
        st.dataframe(display[[c for c in ["Email", "Ruolo", "Attivo", "Creato"] if c in display.columns]], use_container_width=True, hide_index=True)

        st.markdown("#### Modifica autorizzazione")
        user_map = {u["email"]: u for u in users}
        selected_email = st.selectbox("Utente", list(user_map.keys()))
        selected = user_map[selected_email]
        role_options = ["admin", "collaborator", "viewer"]
        idx = role_options.index(selected.get("role", "viewer")) if selected.get("role") in role_options else 2
        c1, c2 = st.columns(2)
        new_role = c1.selectbox("Ruolo", role_options, index=idx, format_func=lambda x: ROLE_LABELS[x], key="edit_role")
        active = c2.checkbox("Utente attivo", value=bool(selected.get("active", True)), key="edit_active")
        if st.button("💾 Salva autorizzazione", use_container_width=True):
            if selected_email.lower() == current_email().lower() and (new_role != "admin" or not active):
                st.error("Per sicurezza non puoi togliere a te stesso il ruolo amministratore o disattivarti da questa schermata.")
            else:
                try:
                    admin.table("app_users").update({"role": new_role, "active": active, "updated_at": now_iso()}).eq("user_id", selected["user_id"]).execute()
                    st.success("Autorizzazione aggiornata.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Aggiornamento non riuscito: {e}")


def page_info() -> None:
    st.subheader("Impostazione del metodo")
    st.markdown(
        """
        **Principio operativo**

        - **Contesto**: Balance / Punto di svolta / entrambi, con eventuali conferme facoltative.
        - **Segnale originale**: E1/E2 e S1/S2 sono riferimenti indicativi definiti prima della giornata operativa.
        - **Trade reale**: Entry effettiva e Stop effettivo vengono registrati quando la dinamica del mercato dà l'ingresso.
        - **Nessun trade**: se non compare un ingresso valido, il segnale non viene classificato come perdita.
        - **Statistiche**: vengono separate la qualità dell'idea iniziale e l'efficacia dei trade realmente eseguiti.

        **Persistenza e collaborazione**

        Dalla V1.3 segnali e screenshot vengono conservati in **Supabase**. Un reboot o un nuovo deploy di Streamlit
        non cancella più l'archivio. Gli utenti hanno ruoli separati: Amministratore, Collaboratore e Solo lettura.
        """
    )


# -----------------------------------------------------------------------------
# Avvio app
# -----------------------------------------------------------------------------
st.set_page_config(page_title=f"{APP_NAME} {APP_VERSION}", page_icon="📊", layout="wide")

if not config_ready():
    st.title(f"📊 {APP_NAME} {APP_VERSION}")
    st.error("Supabase non è ancora configurato nei Secrets di Streamlit.")
    st.code(
        '[supabase]\nurl = "https://TUO-PROGETTO.supabase.co"\nanon_key = "..."\nservice_role_key = "..."\nadmin_email = "tua@email.it"',
        language="toml",
    )
    st.caption("Non caricare mai service_role_key nel repository GitHub: va inserita solo nei Secrets dell'app Streamlit.")
    st.stop()

if not st.session_state.get("sb_user_client"):
    show_login()
    st.stop()

st.title(f"📊 {APP_NAME} {APP_VERSION}")
st.caption("Screenshot → segnale strutturato → trade reale → monitoraggio → statistiche")

role = current_role()
role_label = ROLE_LABELS.get(role, role)

with st.sidebar:
    st.markdown(f"### {APP_NAME}")
    st.caption(f"👤 {current_email()}\n\n**{role_label}**")

    pages = ["Dashboard"]
    if can_write():
        pages += ["Carica nuovo segnale", "Gestione trade"]
    pages += ["Statistiche", "Archivio"]
    if is_admin():
        pages += ["Utenti"]
    pages += ["Info"]

    page = st.radio("Sezione", pages)
    st.divider()
    st.caption("E1/E2 = livelli indicativi. Il Win Rate operativo usa Entry e Stop reali.")
    change_password_box()
    if st.button("🚪 Esci", use_container_width=True):
        try:
            user_client().auth.sign_out()
        except Exception:
            pass
        clear_auth_state()
        st.rerun()

try:
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
    elif page == "Utenti":
        page_users()
    else:
        page_info()
except Exception as e:
    st.error(f"Errore applicazione: {e}")
    st.caption("Se l'errore riguarda autorizzazioni o tabelle mancanti, verifica di aver eseguito SETUP_SUPABASE.sql nel progetto Supabase.")
