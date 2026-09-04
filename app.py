from __future__ import annotations

import io
import hashlib
import re
import shutil
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from urllib.parse import quote
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image, ImageOps, ImageEnhance
import pytesseract
import yfinance as yf
from supabase import create_client, Client

APP_NAME = "G. Signal Tracker"
APP_VERSION = "V3.3"
BUCKET_NAME = "signal-screenshots"
LOCAL_TZ = ZoneInfo("Europe/Rome")

ROLE_LABELS = {
    "admin": "Amministratore",
    "collaborator": "Collaboratore",
    "viewer": "Solo lettura",
}
WRITE_ROLES = {"admin", "collaborator"}

CONFIRMATIONS = [
    "Revolving Door",
    "Medie mobili",
    "M4",
    "Divergenze",
    "Stocastico/TDI",
    "Bollinger",
    "Supertrend",
    "Price Action",
    "News",
    "Altro",
]

SETUP_ORIGINS = [
    "—",
    "Revolving Door",
    "Balance",
    "Punto di svolta",
    "Balance + Punto di svolta",
    "Massimo e minimo Settimanale",
    "Massimo e minimo Mensile",
    "Massimo e minimo Trimestrale",
    "Massimo e minimo Annuale",
    "Altro",
]
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
    "futures t-note'10 anni": ("10Y T-NOTE FUTURES", "ZN=F"),
    "t-note'10 anni": ("10Y T-NOTE FUTURES", "ZN=F"),
    "t-note 10 anni": ("10Y T-NOTE FUTURES", "ZN=F"),
    "10-year t-note": ("10Y T-NOTE FUTURES", "ZN=F"),
    "10 year t-note": ("10Y T-NOTE FUTURES", "ZN=F"),
    "10y t-note": ("10Y T-NOTE FUTURES", "ZN=F"),
    "t-note": ("10Y T-NOTE FUTURES", "ZN=F"),
    "zn": ("10Y T-NOTE FUTURES", "ZN=F"),
}

TRADINGVIEW_SYMBOL_BY_YAHOO = {
    "GC=F": "COMEX:GC1!",
    "NQ=F": "CME_MINI:NQ1!",
    "ES=F": "CME_MINI:ES1!",
    "YM=F": "CBOT_MINI:YM1!",
    "RTY=F": "CME_MINI:RTY1!",
    "CL=F": "NYMEX:CL1!",
    "SI=F": "COMEX:SI1!",
    "HG=F": "COMEX:HG1!",
    "NG=F": "NYMEX:NG1!",
    "ZC=F": "CBOT:ZC1!",
    "ZW=F": "CBOT:ZW1!",
    "ZS=F": "CBOT:ZS1!",
    "6E=F": "CME:6E1!",
    "6B=F": "CME:6B1!",
    "6A=F": "CME:6A1!",
    "6J=F": "CME:6J1!",
    "ZN=F": "CBOT:ZN1!",
    "ZB=F": "CBOT:ZB1!",
    "ZF=F": "CBOT:ZF1!",
    "ZT=F": "CBOT:ZT1!",
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


def _option_index(options: List[str], value: Any, default: int = 0) -> int:
    try:
        return options.index(str(value))
    except Exception:
        return default


def _local_datetime_from_db(value: Any) -> datetime:
    """Converte un timestamp Supabase in Europe/Rome per i campi di modifica."""
    if not value:
        return local_now()
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=LOCAL_TZ)
        else:
            dt = dt.astimezone(LOCAL_TZ)
        return dt
    except Exception:
        return local_now()


def _num_changed(old: Any, new: Optional[float]) -> bool:
    try:
        if old is None and new is None:
            return False
        if old is None or new is None:
            return True
        return not np.isclose(float(old), float(new), rtol=0.0, atol=1e-9)
    except Exception:
        return str(old) != str(new)


def _edit_signal_body(row: Dict[str, Any], key_prefix: str) -> None:
    """Correzione completa del segnale; dalla Dashboard consente anche di registrare il trade reale."""
    if not can_write():
        st.warning("Il tuo profilo è in sola lettura.")
        return

    sid = int(row["id"])
    current_conf = confirmations_list(row.get("confirmations"))
    has_real_trade = row.get("actual_entry") is not None or bool(row.get("entry_time"))
    current_entry_dt = _local_datetime_from_db(row.get("entry_time")) if has_real_trade else local_now()

    st.caption(
        "Puoi correggere segnale, origine, conferme, livelli e note. "
        "Da qui puoi anche registrare Entry e Stop reali quando il setup diventa operativo."
    )

    with st.form(f"{key_prefix}_edit_signal_{sid}"):
        st.markdown("#### Segnale originale")
        c1, c2, c3 = st.columns(3)
        try:
            current_date = date.fromisoformat(str(row.get("valid_date")))
        except Exception:
            current_date = local_now().date()
        valid_date_edit = c1.date_input("Data di validità", value=current_date, key=f"{key_prefix}_date_{sid}")
        instrument_edit = c2.text_input("Strumento", value=str(row.get("instrument") or ""), key=f"{key_prefix}_instr_{sid}")
        direction_edit = c3.selectbox(
            "Direzione", ["LONG", "SHORT"],
            index=_option_index(["LONG", "SHORT"], row.get("direction")),
            key=f"{key_prefix}_dir_{sid}",
        )
        ticker_edit = st.text_input(
            "Ticker Yahoo Finance", value=str(row.get("ticker") or ""), key=f"{key_prefix}_ticker_{sid}"
        )

        a1, a2, a3, a4 = st.columns(4)
        e1_edit = normalize_number(a1.text_input("E1 indicativa", fmt_num(row.get("e1")), key=f"{key_prefix}_e1_{sid}"))
        s1_edit = normalize_number(a2.text_input("S1 indicativo", fmt_num(row.get("s1")), key=f"{key_prefix}_s1_{sid}"))
        e2_edit = normalize_number(a3.text_input("E2 indicativa", fmt_num(row.get("e2")), key=f"{key_prefix}_e2_{sid}"))
        s2_edit = normalize_number(a4.text_input("S2 indicativo", fmt_num(row.get("s2")), key=f"{key_prefix}_s2_{sid}"))
        b1, b2 = st.columns(2)
        t1_edit = normalize_number(b1.text_input("T1", fmt_num(row.get("t1")), key=f"{key_prefix}_t1_{sid}"))
        t2_edit = normalize_number(b2.text_input("T2", fmt_num(row.get("t2")), key=f"{key_prefix}_t2_{sid}"))

        st.markdown("#### Contesto del setup")
        c1, c2, c3 = st.columns(3)
        setup_origin_edit = c1.selectbox(
            "Origine del setup", SETUP_ORIGINS,
            index=_option_index(SETUP_ORIGINS, row.get("setup_origin")),
            key=f"{key_prefix}_origin_{sid}",
        )
        reference_area_edit = c2.text_input(
            "Livello / area Balance o svolta", value=str(row.get("reference_area") or ""),
            key=f"{key_prefix}_reference_{sid}",
        )
        setup_tf_edit = c3.selectbox(
            "Timeframe del riferimento", TIMEFRAMES,
            index=_option_index(TIMEFRAMES, row.get("setup_timeframe")),
            key=f"{key_prefix}_tf_{sid}",
        )

        st.markdown("**Conferme osservate — facoltative**")
        conf_cols = st.columns(4)
        confirmations_edit: List[str] = []
        for i, name in enumerate(CONFIRMATIONS):
            checked = conf_cols[i % 4].checkbox(
                name, value=name in current_conf, key=f"{key_prefix}_conf_{sid}_{i}"
            )
            if checked:
                confirmations_edit.append(name)
        notes_edit = st.text_area(
            "Note / motivazione del setup", value=str(row.get("notes") or ""),
            key=f"{key_prefix}_notes_{sid}",
        )

        st.markdown("#### Trade reale")
        if not has_real_trade:
            st.caption("Lascia vuoti Entry e Stop finché non decidi di entrare. Quando li compili entrambi il trade passa automaticamente IN TRADE.")
        tc1, tc2 = st.columns(2)
        actual_entry_edit = normalize_number(tc1.text_input(
            "Entry effettiva", fmt_num(row.get("actual_entry")), key=f"{key_prefix}_actual_entry_{sid}"
        ))
        actual_stop_edit = normalize_number(tc2.text_input(
            "Stop effettivo", fmt_num(row.get("actual_stop")), key=f"{key_prefix}_actual_stop_{sid}"
        ))
        td1, td2 = st.columns(2)
        entry_date_edit = td1.date_input(
            "Data ingresso", value=current_entry_dt.date(), key=f"{key_prefix}_entry_date_{sid}"
        )
        entry_time_edit = td2.time_input(
            "Ora ingresso", value=current_entry_dt.time().replace(microsecond=0), key=f"{key_prefix}_entry_time_{sid}"
        )

        save_edit = st.form_submit_button("💾 Salva modifiche", type="primary", use_container_width=True)

    if save_edit:
        errors: List[str] = []
        if not instrument_edit.strip():
            errors.append("strumento")
        if t1_edit is None:
            errors.append("T1")

        trade_started_now = (not has_real_trade) and (actual_entry_edit is not None or actual_stop_edit is not None)
        if (has_real_trade or trade_started_now) and (actual_entry_edit is None or actual_stop_edit is None):
            errors.append("Entry/Stop reale")
        if errors:
            st.error("Campi necessari mancanti o non validi: " + ", ".join(errors))
            return

        updates: Dict[str, Any] = {
            "valid_date": valid_date_edit.isoformat(),
            "instrument": instrument_edit.strip(),
            "ticker": ticker_edit.strip(),
            "direction": direction_edit,
            "e1": e1_edit, "s1": s1_edit, "e2": e2_edit, "s2": s2_edit,
            "t1": t1_edit, "t2": t2_edit,
            "setup_origin": setup_origin_edit,
            "reference_area": reference_area_edit.strip(),
            "setup_timeframe": setup_tf_edit,
            "confirmations": confirmations_edit,
            "notes": notes_edit.strip(),
        }

        monitoring_changed = False
        if has_real_trade or trade_started_now:
            new_entry_dt = datetime.combine(entry_date_edit, entry_time_edit, tzinfo=LOCAL_TZ)
            updates.update({
                "actual_entry": actual_entry_edit,
                "actual_stop": actual_stop_edit,
                "entry_time": new_entry_dt.isoformat(timespec="seconds"),
            })
            if not has_real_trade:
                monitoring_changed = True
            else:
                old_entry_dt = _local_datetime_from_db(row.get("entry_time"))
                monitoring_changed = (
                    _num_changed(row.get("actual_entry"), actual_entry_edit)
                    or _num_changed(row.get("actual_stop"), actual_stop_edit)
                    or _num_changed(row.get("t1"), t1_edit)
                    or _num_changed(row.get("t2"), t2_edit)
                    or str(row.get("direction") or "") != direction_edit
                    or str(row.get("ticker") or "").strip() != ticker_edit.strip()
                    or old_entry_dt.replace(microsecond=0) != new_entry_dt.replace(microsecond=0)
                )

        if monitoring_changed:
            updates.update({
                "status": "IN TRADE",
                "outcome": None,
                "t1_hit_time": None,
                "t2_hit_time": None,
                "stop_hit_time": None,
                "result_note": "Ingresso/dati trade registrati o corretti; monitoraggio da ricalcolare",
                "last_check": None,
            })

        try:
            update_signal(sid, **updates)
            if trade_started_now:
                st.success("Ingresso reale registrato. Il trade è ora IN TRADE e verrà monitorato automaticamente.")
            elif monitoring_changed:
                st.success("Modifiche salvate. Il monitoraggio è stato azzerato e verrà ricalcolato con i nuovi dati.")
            else:
                st.success("Modifiche salvate.")
            st.rerun()
        except Exception as e:
            st.error(f"Modifica non riuscita: {e}")

    if not has_real_trade and str(row.get("status") or "") == "PUBBLICATO":
        st.divider()
        st.caption("Se la dinamica non offre un ingresso valido puoi chiudere il setup senza conteggiarlo come perdita.")
        c1, c2 = st.columns(2)
        if c1.button("⚪ NESSUN TRADE", key=f"{key_prefix}_no_trade_{sid}", use_container_width=True):
            update_signal(sid, status="NESSUN TRADE", outcome="NESSUN TRADE", result_note="Segnale non eseguito")
            st.rerun()
        if c2.button("⛔ SETUP ANNULLATO", key=f"{key_prefix}_cancel_{sid}", use_container_width=True):
            update_signal(sid, status="ANNULLATO", outcome="ANNULLATO", result_note="Setup annullato")
            st.rerun()


def edit_signal_panel(row: Dict[str, Any], key_prefix: str) -> None:
    """Versione espandibile usata nell'Archivio."""
    if not can_write():
        return
    with st.expander("✏️ Modifica dati segnale", expanded=False):
        _edit_signal_body(row, key_prefix)


@st.dialog("Modifica segnale", width="large")
def edit_signal_dialog(signal_id: int) -> None:
    row = load_signal(int(signal_id))
    if not row:
        st.warning("Segnale non trovato.")
        return
    st.markdown(f"### #{int(signal_id)} · {row.get('instrument','')} · {row.get('direction','')}")
    _edit_signal_body(row, key_prefix=f"dash_dialog_{int(signal_id)}")


# -----------------------------------------------------------------------------
# Dati mercato / monitoraggio trade
# -----------------------------------------------------------------------------

def effective_yahoo_ticker(row: Dict[str, Any]) -> str:
    """Usa il ticker salvato; se manca prova a ricavarlo dal nome strumento."""
    stored = str(row.get("ticker") or "").strip()
    if stored:
        return stored
    name = str(row.get("instrument") or "").lower()
    for key in sorted(INSTRUMENT_ALIASES, key=len, reverse=True):
        if key in name:
            return INSTRUMENT_ALIASES[key][1]
    return ""


def yahoo_chart_url(row: Dict[str, Any]) -> str:
    ticker = effective_yahoo_ticker(row)
    return f"https://finance.yahoo.com/chart/{quote(ticker, safe='')}" if ticker else ""


def tradingview_symbol(row: Dict[str, Any]) -> str:
    ticker = effective_yahoo_ticker(row)
    return TRADINGVIEW_SYMBOL_BY_YAHOO.get(ticker, "")


def tradingview_chart_url(row: Dict[str, Any]) -> str:
    symbol = tradingview_symbol(row)
    return f"https://www.tradingview.com/chart/?symbol={quote(symbol, safe='')}" if symbol else ""

@st.cache_data(ttl=55, show_spinner=False)
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


@st.cache_data(ttl=50, show_spinner=False)
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


def _store_market_quote(ticker: str, price: Optional[float], quote_time: Any = None, source: str = "Yahoo Finance") -> None:
    """Conserva in sessione l'ultimo prezzo già letto, evitando richieste duplicate a Yahoo."""
    if not ticker or price is None:
        return
    try:
        value = float(price)
        if not np.isfinite(value):
            return
    except Exception:
        return

    if quote_time is None:
        ts = local_now().isoformat(timespec="seconds")
    else:
        try:
            if hasattr(quote_time, "isoformat"):
                ts = quote_time.isoformat()
            else:
                ts = str(quote_time)
        except Exception:
            ts = local_now().isoformat(timespec="seconds")

    quotes = st.session_state.setdefault("market_quotes", {})
    quotes[str(ticker)] = {"price": value, "time": ts, "source": source}


def _recent_market_quote(ticker: str, max_age_seconds: int = 120) -> Optional[Dict[str, Any]]:
    if not ticker:
        return None
    item = (st.session_state.get("market_quotes") or {}).get(str(ticker))
    if not item or item.get("price") is None:
        return None
    try:
        ts = datetime.fromisoformat(str(item.get("time", "")).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=LOCAL_TZ)
        else:
            ts = ts.astimezone(LOCAL_TZ)
        if local_now() - ts > timedelta(seconds=max_age_seconds):
            return None
    except Exception:
        return None
    return item


def get_market_quote(ticker: str, allow_fetch: bool = True) -> Tuple[Optional[float], str, Optional[str]]:
    """Prezzo corrente con riuso del dato già acquisito dal monitoraggio."""
    recent = _recent_market_quote(ticker)
    if recent:
        return float(recent["price"]), str(recent.get("source") or "Yahoo Finance"), str(recent.get("time") or "")
    if not allow_fetch:
        return None, "", None
    price, source = get_current_price(ticker)
    if price is not None:
        _store_market_quote(ticker, price, local_now(), source)
        recent = _recent_market_quote(ticker)
        return price, source, str(recent.get("time")) if recent else now_iso()
    return None, source, None


def active_target_distance(row: Dict[str, Any], current_price: Optional[float]) -> Tuple[Optional[str], Optional[float], Optional[float]]:
    """Restituisce target attivo (T1/T2), distanza in punti e percentuale dal prezzo corrente."""
    if current_price is None:
        return None, None, None
    status = str(row.get("status") or "")
    if status not in {"IN TRADE", "T1 RAGGIUNTO"}:
        return None, None, None

    if row.get("t1_hit_time"):
        label = "T2"
        target = row.get("t2")
        if row.get("t2_hit_time"):
            return None, None, None
    else:
        label = "T1"
        target = row.get("t1")

    if target is None:
        return None, None, None
    try:
        price = float(current_price)
        target_value = float(target)
    except Exception:
        return None, None, None
    if price == 0:
        return label, None, None

    direction = str(row.get("direction") or "").upper()
    remaining = target_value - price if direction == "LONG" else price - target_value
    remaining = max(0.0, remaining)
    pct = (remaining / abs(price)) * 100.0
    return label, remaining, pct


def format_target_distance(row: Dict[str, Any], current_price: Optional[float]) -> str:
    label, points, pct = active_target_distance(row, current_price)
    if not label or points is None or pct is None:
        return "—"
    return f"{label}: {float(points):.1f} pt · {pct:.2f}%"


def open_trade_status_label(row: Dict[str, Any]) -> str:
    if str(row.get("status") or "") == "T1 RAGGIUNTO" or (row.get("t1_hit_time") and not row.get("t2_hit_time")):
        return "T1 OK - T2 IN ATTESA"
    return str(row.get("status") or "—")


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

    # L'ultima chiusura della serie intraday è riutilizzata anche come prezzo corrente in UI.
    try:
        closes = df["Close"].dropna()
        if not closes.empty:
            # La freschezza della cache deve riferirsi al momento in cui abbiamo
            # recuperato il dato, non all'orario della barra Yahoo. I futures
            # possono essere ritardati: usando l'orario della barra la quote
            # veniva subito considerata "scaduta" e Dashboard mostrava —.
            market_ts = closes.index[-1]
            source = f"Yahoo Finance · ultimo dato {market_ts}"
            _store_market_quote(str(row["ticker"]), float(closes.iloc[-1]), local_now(), source)
    except Exception:
        pass

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
            "status": "T1 RAGGIUNTO", "outcome": None, "t1_hit_time": t1_time,
            "t2_hit_time": t2_time, "stop_hit_time": stop_time,
            "note": f"T1 raggiunto; T2 ancora in attesa. Controllo con barre {interval}.",
        }
    return {
        "status": "IN TRADE", "outcome": None, "t1_hit_time": t1_time,
        "t2_hit_time": t2_time, "stop_hit_time": stop_time,
        "note": f"T1 non ancora raggiunto; controllo con barre {interval}.",
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

STATUS_DISPLAY = {
    "PUBBLICATO": "IDEA / IN ATTESA",
    "IN TRADE": "TRADE ATTIVATO",
    "T1 RAGGIUNTO": "TRADE ATTIVATO · T1",
    "NESSUN TRADE": "NON ATTIVATO",
    "ANNULLATO": "ANNULLATO",
    "CHIUSO": "CHIUSO",
    "AMBIGUO": "DA VERIFICARE",
}

def operational_status_label(value: Any) -> str:
    raw = str(value or "—")
    return STATUS_DISPLAY.get(raw, raw)

def dataframe_for_display(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    for c in ["e1", "s1", "e2", "s2", "t1", "t2", "actual_entry", "actual_stop"]:
        if c in out.columns:
            out[c] = out[c].map(lambda x: "—" if pd.isna(x) else fmt_num(x))
    if "confirmations" in out.columns:
        out["confirmations"] = out["confirmations"].map(lambda x: ", ".join(confirmations_list(x)))
    if "outcome" in out.columns:
        out["outcome"] = out["outcome"].map(
            lambda x: "—" if x is None or pd.isna(x) or str(x) in {"None", "T1 APERTO"} else str(x)
        )
    if "status" in out.columns:
        out["status"] = out["status"].map(operational_status_label)
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


def styled_signals_dataframe(df: pd.DataFrame, quotes: Optional[Dict[str, float]] = None):
    """Evidenzia livelli raggiunti e aggiunge prezzo/distanza del target attivo sulla stessa riga."""
    display = dataframe_for_display(df)
    if display.empty:
        return display

    quotes = quotes or {}
    display["Prezzo attuale"] = "—"
    display["TradingView"] = ""
    display["Dist. target"] = "—"

    raw_by_id: Dict[int, Dict[str, Any]] = {}
    for _, r in df.iterrows():
        try:
            raw_by_id[int(r["id"])] = r.to_dict() if hasattr(r, "to_dict") else dict(r)
        except Exception:
            pass

    # Compila i dati dinamici prima dello styling.
    for idx, drow in display.iterrows():
        try:
            sid = int(drow.get("ID"))
        except Exception:
            continue
        raw = raw_by_id.get(sid)
        if not raw:
            continue
        status = str(raw.get("status") or "")
        if status == "T1 RAGGIUNTO":
            display.at[idx, "Stato"] = "T1 OK - T2 IN ATTESA"
            display.at[idx, "Esito"] = "—"
        elif str(raw.get("outcome") or "") == "T1 APERTO":
            # Compatibilità con record salvati dalle versioni precedenti.
            display.at[idx, "Esito"] = "—"

        ticker = effective_yahoo_ticker(raw)
        tv_url = tradingview_chart_url(raw)
        if tv_url:
            display.at[idx, "TradingView"] = tv_url
        price = quotes.get(ticker) if ticker else None
        if price is not None:
            # Il prezzo corrente è utile anche quando il segnale è ancora IDEA / IN ATTESA.
            display.at[idx, "Prezzo attuale"] = f"{float(price):.1f}"
            if status in {"IN TRADE", "T1 RAGGIUNTO"}:
                display.at[idx, "Dist. target"] = format_target_distance(raw, price)

    # La distanza resta vicino allo Stato; prezzo attuale e collegamento TradingView
    # vengono messi alla fine, uno accanto all'altro.
    ordered = list(display.columns)
    for col in ["Prezzo attuale", "TradingView", "Dist. target"]:
        ordered.remove(col)
    insert_at = ordered.index("Stato") if "Stato" in ordered else len(ordered)
    ordered.insert(insert_at, "Dist. target")
    ordered.extend(["Prezzo attuale", "TradingView"])
    display = display[ordered]

    def style_row(row: pd.Series) -> List[str]:
        styles = [""] * len(row.index)
        try:
            sid = int(row.get("ID"))
        except Exception:
            return styles
        raw = raw_by_id.get(sid)
        if raw is None:
            return styles

        def set_style(col: str, css: str) -> None:
            if col in row.index:
                styles[row.index.get_loc(col)] = css

        if raw.get("t1_hit_time"):
            set_style("T1", "background-color: #1f6f3d; color: white; font-weight: 700;")
        if raw.get("t2_hit_time"):
            set_style("T2", "background-color: #0b7a3b; color: white; font-weight: 700;")
        if raw.get("stop_hit_time"):
            set_style("Stop reale", "background-color: #8b2f2f; color: white; font-weight: 700;")

        status = str(raw.get("status") or "")
        outcome = str(raw.get("outcome") or "")
        if status == "T1 RAGGIUNTO":
            css = "background-color: #1f6f3d; color: white; font-weight: 700;"
        elif status == "CHIUSO" and outcome == "T2":
            css = "background-color: #0b7a3b; color: white; font-weight: 700;"
        elif status == "CHIUSO" and "STOP" in outcome:
            css = "background-color: #8b2f2f; color: white; font-weight: 700;"
        elif status == "AMBIGUO":
            css = "background-color: #7a4d00; color: white; font-weight: 700;"
        elif status == "IN TRADE":
            css = "background-color: #24476b; color: white; font-weight: 700;"
        else:
            css = ""
        if css:
            set_style("Stato", css)
            if row.get("Esito") != "—":
                set_style("Esito", css)
        return styles

    return display.style.apply(style_row, axis=1)


def dashboard_quotes(df: pd.DataFrame, allow_fetch: bool) -> Dict[str, float]:
    """Prezzi per tutti i segnali ancora attivi: idea, trade aperto e T1 già raggiunto."""
    quotes: Dict[str, float] = {}
    if df.empty:
        return quotes
    active_statuses = {"PUBBLICATO", "IN TRADE", "T1 RAGGIUNTO"}
    active_df = df[df["status"].isin(active_statuses)] if "status" in df else pd.DataFrame()
    if active_df.empty:
        return quotes

    tickers: List[str] = []
    for _, r in active_df.iterrows():
        ticker = effective_yahoo_ticker(r.to_dict())
        if ticker and ticker not in tickers:
            tickers.append(ticker)

    for ticker in tickers:
        price, _, _ = get_market_quote(ticker, allow_fetch=allow_fetch)
        if price is not None:
            quotes[ticker] = float(price)
    return quotes


def last_market_check_label(df: pd.DataFrame) -> str:
    if df.empty or "last_check" not in df.columns:
        return "—"
    ts = pd.to_datetime(df["last_check"], utc=True, errors="coerce").dropna()
    if ts.empty:
        return "—"
    last = ts.max().tz_convert(LOCAL_TZ)
    return last.strftime("%d/%m/%Y %H:%M:%S")


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


def trade_is_concluded(row: Dict[str, Any]) -> bool:
    """True solo per trade realmente entrati e ormai risolti/da verificare."""
    return row.get("actual_entry") is not None and str(row.get("status") or "") in {"CHIUSO", "AMBIGUO"}


@st.dialog("Screenshot finale", width="large")
def final_screenshot_dialog(signal_id: int) -> None:
    row = load_signal(int(signal_id))
    if not row:
        st.warning("Segnale non trovato.")
        return
    if not trade_is_concluded(row):
        st.info("Lo screenshot finale diventa disponibile quando il trade è concluso.")
        return

    sid = int(row["id"])
    label = f"Segnale #{sid} · {row.get('instrument','')} · {row.get('direction','')} · {row.get('valid_date','')}"
    existing_path = str(row.get("final_screenshot_path") or "")

    if existing_path:
        raw = download_screenshot(existing_path)
        if raw:
            st.image(raw, caption=f"Screenshot finale · {label}", use_container_width=True)
        else:
            st.warning("Il percorso dello screenshot finale è salvato, ma il file non è disponibile nello Storage.")
    else:
        st.caption("Nessuno screenshot finale caricato. Campo facoltativo.")

    if not can_write():
        return

    uploaded = st.file_uploader(
        "📸 Carica screenshot finale — facoltativo",
        type=["png", "jpg", "jpeg", "webp"],
        key=f"final_shot_upload_{sid}",
    )
    if uploaded is not None:
        action_label = "💾 Salva screenshot finale" if not existing_path else "🔁 Sostituisci screenshot finale"
        if st.button(action_label, key=f"save_final_shot_{sid}", type="primary", use_container_width=True):
            new_path = ""
            try:
                new_path = upload_screenshot(uploaded)
                update_signal(sid, final_screenshot_path=new_path)
                if existing_path and existing_path != new_path:
                    remove_screenshot(existing_path)
                st.success("Screenshot finale salvato.")
                st.rerun()
            except Exception as e:
                if new_path:
                    remove_screenshot(new_path)
                st.error(
                    "Salvataggio screenshot finale non riuscito. "
                    "Verifica di aver eseguito la migration Supabase V3.0. "
                    f"Dettaglio: {e}"
                )

    if existing_path:
        if st.button("🗑️ Rimuovi screenshot finale", key=f"remove_final_shot_{sid}", use_container_width=True):
            try:
                update_signal(sid, final_screenshot_path=None)
                remove_screenshot(existing_path)
                st.success("Screenshot finale rimosso.")
                st.rerun()
            except Exception as e:
                st.error(f"Rimozione non riuscita: {e}")


def final_screenshot_button(row: Dict[str, Any], key: str, use_container_width: bool = True) -> None:
    if not trade_is_concluded(row):
        return
    has_final = bool(row.get("final_screenshot_path"))
    label = "📸 Apri screenshot finale" if has_final else "📸 Carica screenshot finale"
    if st.button(label, key=key, use_container_width=use_container_width, disabled=(not has_final and not can_write())):
        final_screenshot_dialog(int(row["id"]))


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
        distinct_signal = st.checkbox(
            "È un nuovo segnale distinto anche se esiste già lo stesso strumento/direzione nella stessa giornata",
            value=False,
            help="Lascia deselezionato normalmente. Serve solo quando la sala pubblica davvero più setup separati sullo stesso strumento nella stessa giornata.",
        )
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

        # Protezione contro gli aggiornamenti salvati per errore come nuovi segnali.
        # Non altera il segnale originale già archiviato: invita a correggere/aggiornare quello esistente.
        try:
            existing = load_signals()
            if not existing.empty:
                same = existing[
                    (existing["valid_date"].astype(str) == valid_date.isoformat())
                    & (existing["instrument"].fillna("").astype(str).str.upper().str.strip() == instrument.strip().upper())
                    & (existing["direction"].fillna("").astype(str).str.upper().str.strip() == direction.strip().upper())
                ]
                if not same.empty and not distinct_signal:
                    existing_id = int(same.iloc[0]["id"])
                    st.warning(
                        f"Possibile aggiornamento del segnale #{existing_id}: esiste già {instrument.strip()} {direction} "
                        f"per {valid_date.isoformat()}. Non ho creato un duplicato. Apri il segnale esistente dalla Dashboard/Archivio; "
                        "se invece è davvero un nuovo setup distinto, seleziona la conferma dedicata e salva di nuovo."
                    )
                    return
        except Exception as e:
            st.warning(f"Controllo duplicati non disponibile: {e}")

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


@st.fragment(run_every="60s")
def dashboard_live_panel(auto_monitor: bool) -> None:
    # Il frammento si aggiorna ogni 60 secondi solo mentre la Dashboard è aperta.
    manual_update = st.button("🔄 Aggiorna ora", key="dashboard_manual_update") if can_write() else False
    notes: List[str] = []
    updated = 0

    if manual_update:
        with st.spinner("Controllo trade aperti..."):
            updated, notes = update_all_open_trades()
    elif auto_monitor and can_write():
        updated, notes = update_all_open_trades()

    df = load_signals()
    if df.empty:
        st.info("Nessun segnale salvato.")
        return

    total = len(df)
    traded = int(df["actual_entry"].notna().sum()) if "actual_entry" in df else 0
    no_trade = int(df["status"].isin(["NESSUN TRADE", "ANNULLATO"]).sum())
    t1_success = int((df["t1_hit_time"].notna() & (df["status"] != "AMBIGUO")).sum())
    stopped_before_t1 = int((df["outcome"] == "STOP").sum())
    resolved_for_wr = t1_success + stopped_before_t1
    wr = (100 * t1_success / resolved_for_wr) if resolved_for_wr else 0.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Segnali pubblicati", total)
    c2.metric("Trade eseguiti", traded)
    c3.metric("Nessun trade / annullati", no_trade)
    c4.metric("Win Rate base", f"{wr:.1f}%", help="T1 raggiunto prima dello Stop / trade già risolti. Non è ancora una misura di P&L.")

    if auto_monitor and can_write():
        st.caption(
            f"🟢 Monitoraggio automatico attivo · controllo ogni 60 secondi · ultimo controllo: {last_market_check_label(df)}. "
            "Fonte Yahoo Finance: il prezzo mostrato è l’ultimo dato disponibile e può essere ritardato."
        )
    else:
        st.caption(f"Ultimo controllo mercato: {last_market_check_label(df)}")

    if manual_update:
        st.success(f"Controllati {updated} trade aperti.")
    if notes:
        st.warning("\n".join(notes))

    quotes = dashboard_quotes(df, allow_fetch=True)
    table_event = st.dataframe(
        styled_signals_dataframe(df, quotes),
        use_container_width=True,
        hide_index=True,
        key="dashboard_signals_table",
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "TradingView": st.column_config.LinkColumn(
                "TV",
                help="Apri direttamente il grafico dello strumento su TradingView",
                display_text="📊 Apri",
                width="small",
            )
        },
    )
    st.markdown(
        "<div style='font-weight:800; color:#ffb347; text-transform:uppercase; margin-top:0.20rem; margin-bottom:0.15rem;'>"
        "⬆️ SELEZIONA IL RIQUADRO ☐ A SINISTRA DELLA RIGA PER MOSTRARE I COMANDI MODIFICA E APRI GRAFICO SCREENSHOT ORIGINALE."
        "</div>",
        unsafe_allow_html=True,
    )
    st.caption("E1/E2 = livelli indicativi. Il Win Rate operativo usa Entry e Stop reali.")

    selected_rows = []
    try:
        selected_rows = list(table_event.selection.rows)
    except Exception:
        try:
            selected_rows = list(table_event.get("selection", {}).get("rows", []))
        except Exception:
            selected_rows = []

    if selected_rows:
        pos = int(selected_rows[0])
        if 0 <= pos < len(df):
            selected_raw = df.iloc[pos].to_dict()
            sid = int(selected_raw["id"])
            st.caption(
                f"Segnale selezionato: #{sid} · {selected_raw.get('instrument','')} · "
                f"{selected_raw.get('direction','')} · {selected_raw.get('valid_date','')}"
            )
            concluded = trade_is_concluded(selected_raw)
            if can_write():
                cols = st.columns(3 if concluded else 2)
                if cols[0].button("✏️ Modifica", key=f"dashboard_edit_{sid}", use_container_width=True):
                    edit_signal_dialog(sid)
                if cols[1].button(
                    "🖼️ Apri grafico Screenshot originale", key=f"dashboard_image_{sid}",
                    use_container_width=True, disabled=not bool(selected_raw.get("screenshot_path")),
                ):
                    open_signal_image_dialog(
                        selected_raw.get("screenshot_path") or "",
                        f"Segnale #{sid} · {selected_raw.get('instrument','')} · {selected_raw.get('direction','')} · {selected_raw.get('valid_date','')}",
                    )
                if concluded:
                    has_final = bool(selected_raw.get("final_screenshot_path"))
                    final_label = "📸 Apri screenshot finale" if has_final else "📸 Carica screenshot finale"
                    if cols[2].button(final_label, key=f"dashboard_final_{sid}", use_container_width=True):
                        final_screenshot_dialog(sid)
            else:
                cols = st.columns(2 if concluded and selected_raw.get("final_screenshot_path") else 1)
                if cols[0].button(
                    "🖼️ Apri grafico Screenshot originale", key=f"dashboard_image_view_{sid}",
                    use_container_width=True, disabled=not bool(selected_raw.get("screenshot_path")),
                ):
                    open_signal_image_dialog(
                        selected_raw.get("screenshot_path") or "",
                        f"Segnale #{sid} · {selected_raw.get('instrument','')} · {selected_raw.get('direction','')} · {selected_raw.get('valid_date','')}",
                    )
                if concluded and selected_raw.get("final_screenshot_path"):
                    if cols[1].button("📸 Apri screenshot finale", key=f"dashboard_final_view_{sid}", use_container_width=True):
                        final_screenshot_dialog(sid)

            # Il grafico TradingView è apribile direttamente dalla colonna TV della tabella,
            # senza dover selezionare la riga o entrare in modifica.
    st.download_button(
        "⬇️ Esporta storico Excel", data=excel_bytes(df),
        file_name=f"signal_tracker_{local_now().date().isoformat()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="dashboard_excel_download",
    )


def page_dashboard() -> None:
    st.subheader("Dashboard")
    if can_write():
        auto_monitor = st.toggle(
            "Monitoraggio automatico trade aperti (ogni 60 secondi)",
            value=True,
            help="Attivo solo mentre questa Dashboard resta aperta. Controlla T1, T2 e Stop usando i dati intraday disponibili da Yahoo Finance.",
        )
    else:
        auto_monitor = False
        st.caption("Profilo in sola lettura: il monitoraggio viene aggiornato dagli utenti autorizzati alla scrittura.")
    dashboard_live_panel(auto_monitor)


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
            concluded = trade_is_concluded(row)
            if concluded:
                a1, a2 = st.columns(2)
                with a1:
                    image_open_button(
                        row.get("screenshot_path") or "",
                        f"Segnale #{sid} · {row['instrument']} · {row['direction']} · {row['valid_date']}",
                        key=f"open_img_archive_{sid}",
                    )
                with a2:
                    final_screenshot_button(row, key=f"final_img_archive_{sid}")
            else:
                image_open_button(
                    row.get("screenshot_path") or "",
                    f"Segnale #{sid} · {row['instrument']} · {row['direction']} · {row['valid_date']}",
                    key=f"open_img_archive_{sid}",
                )
            edit_signal_panel(row, key_prefix="archive")


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

        - **Contesto**: Balance / Punto di svolta / Revolving Door, con eventuali conferme facoltative.
        - **Segnale originale**: E1/E2 e S1/S2 sono riferimenti indicativi definiti prima della giornata operativa.
        - **Trade reale**: Entry effettiva e Stop effettivo vengono registrati quando la dinamica del mercato dà l'ingresso.
        - **Nessun trade**: se non compare un ingresso valido, il segnale non viene classificato come perdita.
        - **Statistiche**: vengono separate la qualità dell'idea iniziale e l'efficacia dei trade realmente eseguiti.
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
        pages += ["Carica nuovo segnale"]
    pages += ["Statistiche", "Archivio"]
    if is_admin():
        pages += ["Utenti"]
    pages += ["Info"]

    page = st.radio("Sezione", pages)
    st.divider()
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
