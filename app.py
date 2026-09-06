from __future__ import annotations

import io
import hashlib
import hmac
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
APP_VERSION = "V4.7"
BUCKET_NAME = "signal-screenshots"
LOCAL_TZ = ZoneInfo("Europe/Rome")

ROLE_LABELS = {
    "admin": "Amministratore",
    "collaborator": "Collaboratore",
}
WRITE_ROLES = {"admin", "collaborator"}

CONFIRMATIONS = [
    "Revolving Door",
    "Medie mobili",
    "M4",
    "Divergenze",
    "Stocastico/TDI",
    "Supertrend",
    "Fibonacci",
    "Altro",
]

# Codici usati nella nuova tabella inserita negli screenshot.
# La conferma viene attivata SOLO quando accanto al codice è presente una X.
CONFIRMATION_CODE_MAP = {
    "RD": "Revolving Door",
    "STOC/TDI": "Stocastico/TDI",
    "MM": "Medie mobili",
    "M4": "M4",
    "ST": "Supertrend",
    "DIV": "Divergenze",
    "FIBO": "Fibonacci",
}

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
    "swiss franc futures": ("SWISS FRANC FUTURES", "6S=F"),
    "swiss franc": ("SWISS FRANC FUTURES", "6S=F"),
    "6s1": ("SWISS FRANC FUTURES", "6S=F"),
    "6s": ("SWISS FRANC FUTURES", "6S=F"),
    "futures t-note'10 anni": ("10Y T-NOTE FUTURES", "ZN=F"),
    "t-note'10 anni": ("10Y T-NOTE FUTURES", "ZN=F"),
    "t-note 10 anni": ("10Y T-NOTE FUTURES", "ZN=F"),
    "10-year t-note": ("10Y T-NOTE FUTURES", "ZN=F"),
    "10 year t-note": ("10Y T-NOTE FUTURES", "ZN=F"),
    "10y t-note": ("10Y T-NOTE FUTURES", "ZN=F"),
    "t-note": ("10Y T-NOTE FUTURES", "ZN=F"),
    "zn": ("10Y T-NOTE FUTURES", "ZN=F"),
    "euro stoxx 50": ("EURO STOXX 50", "^STOXX50E"),
    "euro stoxx": ("EURO STOXX 50", "^STOXX50E"),
    "stoxx 50": ("EURO STOXX 50", "^STOXX50E"),
    "stoxx50": ("EURO STOXX 50", "^STOXX50E"),
    "fesx": ("EURO STOXX 50", "^STOXX50E"),
    "dax 40": ("DAX", "^GDAXI"),
    "dax index": ("DAX", "^GDAXI"),
    "dax": ("DAX", "^GDAXI"),
    "fdxm": ("DAX", "^GDAXI"),
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
    "6S=F": "CME:6S1!",
    "ZN=F": "CBOT:ZN1!",
    "ZB=F": "CBOT:ZB1!",
    "ZF=F": "CBOT:ZF1!",
    "ZT=F": "CBOT:ZT1!",
    "^GDAXI": "EUREX:FDXM1!",
    "^STOXX50E": "EUREX:FESX1!",
}


# -----------------------------------------------------------------------------
# Configurazione Supabase / accesso app con sola password
# -----------------------------------------------------------------------------

def get_secret(name: str, default: str = "") -> str:
    """Legge un segreto dalla sezione [supabase]."""
    try:
        cfg = st.secrets.get("supabase", {})
        value = cfg.get(name, default)
        return str(value).strip() if value is not None else default
    except Exception:
        return default


def get_access_secret(name: str, default: str = "") -> str:
    """Legge un segreto dalla sezione [access]."""
    try:
        cfg = st.secrets.get("access", {})
        value = cfg.get(name, default)
        return str(value) if value is not None else default
    except Exception:
        return default


def supabase_config() -> Dict[str, str]:
    return {
        "url": get_secret("url"),
        "service_role_key": get_secret("service_role_key") or get_secret("secret_key"),
    }


def access_config() -> Dict[str, str]:
    return {
        "admin_password": get_access_secret("admin_password"),
        "collaborator_password": get_access_secret("collaborator_password"),
    }


def config_ready() -> bool:
    sb = supabase_config()
    access = access_config()
    return bool(
        sb["url"]
        and sb["service_role_key"]
        and access["admin_password"]
        and access["collaborator_password"]
        and access["admin_password"] != access["collaborator_password"]
    )


def service_client() -> Optional[Client]:
    cfg = supabase_config()
    if not cfg["url"] or not cfg["service_role_key"]:
        return None
    return create_client(cfg["url"], cfg["service_role_key"])


def user_client() -> Client:
    """Client backend usato dall'app dopo lo sblocco con password.

    La service role resta esclusivamente nei Secrets di Streamlit e non viene
    mai mostrata al browser. I permessi dell'interfaccia continuano a dipendere
    dal ruolo ricavato dalla password inserita.
    """
    client = st.session_state.get("sb_service_client")
    if client is None:
        client = service_client()
        if client is None:
            raise RuntimeError("Connessione Supabase non disponibile.")
        st.session_state["sb_service_client"] = client
    return client


def current_role() -> str:
    return str(st.session_state.get("user_role", ""))


def can_write() -> bool:
    return current_role() in WRITE_ROLES


def is_admin() -> bool:
    return current_role() == "admin"


def clear_auth_state() -> None:
    for key in ["app_unlocked", "user_role", "sb_service_client"]:
        st.session_state.pop(key, None)


def audit_user_id() -> Optional[str]:
    """Restituisce, se disponibile, un UUID esistente per i campi audit.

    Mantiene compatibilità con le colonne created_by/updated_by già presenti
    nel database senza richiedere l'autenticazione email/password di Supabase.
    """
    try:
        client = user_client()
        role = current_role()
        res = (
            client.table("app_users")
            .select("user_id")
            .eq("role", role)
            .eq("active", True)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        if rows and rows[0].get("user_id"):
            return str(rows[0]["user_id"])
        # fallback: usa un amministratore già presente, se disponibile
        res = (
            client.table("app_users")
            .select("user_id")
            .eq("role", "admin")
            .eq("active", True)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        if rows and rows[0].get("user_id"):
            return str(rows[0]["user_id"])
    except Exception:
        pass
    return None


def perform_login(password: str) -> Tuple[bool, str]:
    pwd = str(password or "")
    access = access_config()
    admin_pwd = access["admin_password"]
    collaborator_pwd = access["collaborator_password"]

    if admin_pwd and hmac.compare_digest(pwd, admin_pwd):
        role = "admin"
    elif collaborator_pwd and hmac.compare_digest(pwd, collaborator_pwd):
        role = "collaborator"
    else:
        return False, "Password non corretta."

    client = service_client()
    if client is None:
        return False, "Connessione Supabase non disponibile."

    st.session_state["sb_service_client"] = client
    st.session_state["user_role"] = role
    st.session_state["app_unlocked"] = True
    return True, "Accesso eseguito."


def show_login() -> None:
    st.title(f"📊 {APP_NAME} {APP_VERSION}")
    st.caption("Archivio condiviso e persistente · accesso riservato")
    with st.form("login_form"):
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("🔓 Entra", type="primary", use_container_width=True)
    if submitted:
        ok, msg = perform_login(password)
        if ok:
            st.rerun()
        else:
            st.error(msg)


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
    """OCR generale + OCR dedicato alla fascia superiore con la nuova tabella.

    La vecchia versione leggeva solo la parte alta SINISTRA e quindi perdeva la tabella
    che ora si trova in alto a destra. Manteniamo due sole chiamate a Tesseract, ma il
    secondo passaggio copre tutta la larghezza del grafico e circa il 36% superiore.
    """
    if not configure_tesseract():
        raise RuntimeError(
            "OCR non disponibile: su Streamlit Community Cloud serve packages.txt con la riga tesseract-ocr."
        )
    full = preprocess_for_ocr(img, scale=2, contrast=2.2)
    full_text = pytesseract.image_to_string(full, config="--psm 11")

    # Fascia superiore completa: contiene intestazione TradingView + tabella + timeframe.
    h = max(180, int(img.height * 0.36))
    top = img.crop((0, 0, img.width, min(h, img.height)))
    top = preprocess_for_ocr(top, scale=2, contrast=2.4)
    top_text = pytesseract.image_to_string(top, config="--psm 11")
    return full_text, top_text


def _numeric_or_none(value: Any) -> Optional[float]:
    """Converte un valore numerico opzionale; None/NaN/NaT restano assenti."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    try:
        v = float(value)
        return v if np.isfinite(v) else None
    except Exception:
        return None


def _max_true_run(mask: np.ndarray) -> int:
    if mask.size == 0:
        return 0
    arr = mask.astype(np.int8)
    diff = np.diff(np.concatenate(([0], arr, [0])))
    starts = np.where(diff == 1)[0]
    ends = np.where(diff == -1)[0]
    if starts.size == 0:
        return 0
    return int(np.max(ends - starts))


def _candidate_horizontal_lines(img: Image.Image) -> List[int]:
    """Trova lunghe linee orizzontali nel grafico senza dipendenze aggiuntive."""
    gray = np.array(ImageOps.grayscale(img))
    h, w = gray.shape
    x0, x1 = int(w * 0.20), int(w * 0.94)
    min_run = max(120, int(w * 0.14))
    candidates: List[Tuple[int, int]] = []
    for y in range(max(20, int(h * 0.10)), min(h - 20, int(h * 0.88))):
        run = _max_true_run(gray[y, x0:x1] < 155)
        if run >= min_run:
            candidates.append((y, run))
    groups: List[List[Tuple[int, int]]] = []
    for y, run in candidates:
        if not groups or y - groups[-1][-1][0] > 3:
            groups.append([])
        groups[-1].append((y, run))
    return [max(group, key=lambda item: item[1])[0] for group in groups]


def _normalize_chart_tag(token: str) -> Optional[str]:
    s = str(token or "").upper().strip()
    s = s.replace("$", "S").replace("£", "E")
    s = re.sub(r"[^A-Z0-9]", "", s)
    aliases = {"TL": "T1", "TI": "T1", "SI": "S1", "EI": "E1"}
    s = aliases.get(s, s)
    return s if re.fullmatch(r"[EST][123]", s) else None


def _ocr_chart_tag_positions(img: Image.Image) -> Dict[str, float]:
    """Legge E/S/T direttamente dalle etichette stampate sulle linee."""
    w, h = img.size
    found: Dict[str, Tuple[float, float]] = {}
    # Ritaglio concentrato sulla zona in cui normalmente sono scritte E/S/T.
    crops = [(0.50, 0.85, 0.12, 0.75), (0.48, 0.88, 0.20, 0.70)]
    for crop_no, (xf0, xf1, yf0, yf1) in enumerate(crops):
        x0, x1 = int(w * xf0), int(w * xf1)
        y0, y1 = int(h * yf0), int(h * yf1)
        crop = ImageOps.grayscale(img.crop((x0, y0, x1, y1)))
        scale = 4
        crop = crop.resize((crop.width * scale, crop.height * scale))
        crop = ImageEnhance.Contrast(crop).enhance(3.0)
        try:
            data = pytesseract.image_to_data(crop, config="--psm 11", output_type=pytesseract.Output.DICT)
        except Exception:
            continue
        n = len(data.get("text", []))
        for i in range(n):
            tag = _normalize_chart_tag(data["text"][i])
            if not tag:
                continue
            try:
                conf = float(data.get("conf", [0] * n)[i])
            except Exception:
                conf = 0.0
            if conf < 20:
                continue
            top = float(data["top"][i])
            height = float(data["height"][i])
            yy = y0 + (top + height / 2.0) / scale
            if tag not in found or conf > found[tag][1]:
                found[tag] = (yy, conf)
        # Se il primo ritaglio ha già trovato almeno due riferimenti utili,
        # evitiamo una seconda chiamata OCR costosa.
        if crop_no == 0 and len(found) >= 2:
            break
    return {tag: yy for tag, (yy, _) in found.items()}

def _ocr_dark_price_near_y(img: Image.Image, y: int) -> Optional[float]:
    """Legge il cartellino prezzo scuro a destra, anche se è leggermente spostato."""
    w, h = img.size
    x0, x1 = int(w * 0.95), int(w * 0.997)
    scored: List[Tuple[float, int]] = []
    for off in range(-24, 25, 2):
        yy = max(12, min(h - 13, int(y + off)))
        small = np.array(ImageOps.grayscale(img.crop((x0, yy - 10, x1, yy + 11))))
        scored.append((float(np.mean(small < 85)), yy))

    # Proviamo solo i tre centri più plausibili per non rallentare l'OCR.
    centers: List[Tuple[float, int]] = []
    for score, yy in sorted(scored, reverse=True):
        if score < 0.08:
            continue
        if any(abs(yy - prev_y) < 5 for _, prev_y in centers):
            continue
        centers.append((score, yy))
        if len(centers) == 3:
            break

    integer_fallback: Optional[float] = None
    for _, yy in centers:
        crop = ImageOps.grayscale(img.crop((x0, yy - 12, x1, yy + 13)))
        crop = crop.resize((crop.width * 8, crop.height * 8))
        arr = np.array(crop)
        for threshold in (100, 130):
            bw = Image.fromarray(np.where(arr < threshold, 0, 255).astype("uint8"))
            try:
                raw = pytesseract.image_to_string(
                    bw, config="--psm 7 -c tessedit_char_whitelist=0123456789.,"
                ).strip()
            except Exception:
                continue
            m = re.search(r"\d+(?:[.,]\d+)?", raw)
            if not m:
                continue
            token = m.group(0)
            value = normalize_number(token)
            if value is None:
                continue
            # Se è presente il separatore decimale è quasi sempre la lettura più
            # affidabile dei cartellini TradingView (es. 6.520, 107.8125).
            if "." in token or "," in token:
                return value
            if integer_fallback is None:
                integer_fallback = value
    return integer_fallback

def extract_chart_levels_from_lines(img: Image.Image) -> Dict[str, float]:
    """
    OCR posizionale: associa E1/E2/S1/S2/T1/T2/T3 alle linee orizzontali
    e ai cartellini prezzo sulla scala destra. È un fallback e i campi restano
    sempre correggibili manualmente.
    """
    lines = _candidate_horizontal_lines(img)
    if not lines:
        return {}
    tag_positions = _ocr_chart_tag_positions(img)
    assigned_y: Dict[str, int] = {}
    for tag, yy in tag_positions.items():
        nearest = min(lines, key=lambda ly: abs(ly - yy))
        if abs(nearest - yy) <= 32:
            assigned_y[tag] = nearest

    # Caso frequente: E1/T1 sono attraversati dalla linea e Tesseract vede E2/T2.
    # Tra E2 e T2 la sequenza geometrica è E1 -> T1 sia LONG sia SHORT.
    if "E2" in assigned_y and "T2" in assigned_y:
        y_e2, y_t2 = assigned_y["E2"], assigned_y["T2"]
        lo, hi = sorted((y_e2, y_t2))
        occupied = set(assigned_y.values())
        between = [ly for ly in lines if lo < ly < hi and ly not in occupied]
        between.sort(key=lambda ly: abs(ly - y_e2))
        missing = [tag for tag in ("E1", "T1") if tag not in assigned_y]
        if len(between) == len(missing) and 0 < len(missing) <= 2:
            for tag, ly in zip(missing, between):
                assigned_y[tag] = ly

    result: Dict[str, float] = {}
    for tag, ly in assigned_y.items():
        value = _ocr_dark_price_near_y(img, ly)
        if value is not None:
            result[tag.lower()] = value
    return result


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
        "T3": r"T\s*3",
    }
    m = re.search(aliases[tag] + r"\s*[:=]?\s*([0-9][0-9.,]*)", text, flags=re.I)
    return normalize_number(m.group(1)) if m else None


def extract_shared_stop_value(text: str) -> Optional[float]:
    """Legge la nuova riga singola `Stop 1,23456` della tabella."""
    m = re.search(r"\bSTOP\b\s*[:=]?\s*([0-9][0-9.,]*)", str(text or ""), flags=re.I)
    return normalize_number(m.group(1)) if m else None


def _confirmation_code_in_line(line: str, code: str) -> bool:
    """Riconosce il codice conferma senza confondere ST con STOC/TDI."""
    raw = str(line or "").upper().replace("×", "X")
    compact = re.sub(r"[^A-Z0-9/]", "", raw)
    if code == "STOC/TDI":
        return compact.startswith("STOC/TDI") or compact.startswith("STOCTDI")
    if code == "DIV":
        return compact.startswith("DIV")
    return compact.startswith(code) and (compact == code or compact.startswith(code + "X"))


def _line_has_x_after_code(line: str, code: str) -> bool:
    raw = str(line or "").upper().replace("×", "X")
    if code == "STOC/TDI":
        return bool(re.search(r"STOC\s*/?\s*TDI.*?X", raw))
    if code == "DIV":
        return bool(re.search(r"DIV\.?\s*.*?X", raw))
    return bool(re.search(r"(?<![A-Z0-9])" + re.escape(code) + r"(?![A-Z0-9]).*?X", raw))


def _is_x_marker(line: str) -> bool:
    compact = re.sub(r"[^A-Z]", "", str(line or "").upper().replace("×", "X"))
    return compact in {"X", "XX"}


def parse_table_metadata(text: str) -> Dict[str, Any]:
    """Estrae contesto e conferme dalla nuova tabella in alto nello screenshot.

    Regola fondamentale: una conferma viene selezionata solo se accanto alla relativa
    sigla è presente una X. RD nella riga intestazione resta invece Origine del setup.
    """
    raw = str(text or "")
    lines = [re.sub(r"\s+", " ", ln.strip()) for ln in raw.splitlines() if ln.strip()]

    # Origine setup: nella nuova tabella RD è nella riga con LONG/SHORT e data.
    setup_origin = "—"
    for i, line in enumerate(lines):
        if re.fullmatch(r"RD\.?", line.upper().strip()):
            prev = " ".join(lines[max(0, i - 2):i]).upper()
            if re.search(r"\b(?:LONG|SHORT)\b", prev) or re.search(r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}", prev):
                setup_origin = "Revolving Door"
                break
    if setup_origin == "—":
        m = re.search(r"\b(?:LONG|SHORT)\b[\s\S]{0,50}?\d{1,2}[./-]\d{1,2}[./-]\d{2,4}[\s\S]{0,30}?\bRD\b", raw, flags=re.I)
        if m:
            setup_origin = "Revolving Door"

    # Timeframe scritto nel box a destra: es. Timeframe 30-Minute.
    setup_timeframe = "—"
    tfm = re.search(r"TIME\s*FRAME\s*([0-9]{1,3})\s*[- ]?\s*(MINUTE|MIN|MINUTI|HOUR|H)?", raw, flags=re.I)
    if not tfm:
        tfm = re.search(r"TIMEFRAME\s*([0-9]{1,3})\s*[- ]?\s*(MINUTE|MIN|MINUTI|HOUR|H)?", raw, flags=re.I)
    if tfm:
        n = int(tfm.group(1))
        unit = (tfm.group(2) or "MIN").upper()
        if unit.startswith("H"):
            setup_timeframe = f"{n}H" if f"{n}H" in TIMEFRAMES else "—"
        else:
            setup_timeframe = {15: "15m", 30: "30m", 60: "1H", 120: "2H", 240: "4H"}.get(n, "—")

    confirmations: List[str] = []
    for i, line in enumerate(lines):
        for code, label in CONFIRMATION_CODE_MAP.items():
            if not _confirmation_code_in_line(line, code):
                continue
            checked = _line_has_x_after_code(line, code)
            if not checked and i + 1 < len(lines):
                checked = _is_x_marker(lines[i + 1])
            if checked and label not in confirmations:
                confirmations.append(label)

    return {
        "setup_origin": setup_origin,
        "setup_timeframe": setup_timeframe,
        "confirmations": confirmations,
    }


def _normalize_confirmation_code_token(line: str) -> Optional[str]:
    """Normalizza le sigle della terza colonna della tabella, tollerando piccoli errori OCR."""
    compact = re.sub(r"[^A-Z0-9]", "", str(line or "").upper())
    if not compact:
        return None
    if compact.startswith("STOC") or compact in {"STOCTDI", "STOCITD", "STOCTD", "STOTDI"}:
        return "STOC/TDI"
    if compact == "MM":
        return "MM"
    if compact == "M4":
        return "M4"
    if compact == "ST":
        return "ST"
    if compact.startswith("DIV"):
        return "DIV"
    if compact.startswith("FIB"):
        return "FIBO"
    if compact == "RD":
        return "RD"
    return None


def extract_confirmation_codes_by_row(text: str) -> Dict[str, str]:
    """Associa la sigla conferma alla riga E1/E2/T1/T2/T3/STOP della nuova tabella."""
    lines = [ln.strip() for ln in str(text or "").splitlines() if ln.strip()]
    wanted = ["E1", "E2", "T1", "T2", "T3", "STOP"]
    positions: Dict[str, int] = {}
    start = 0
    for tag in wanted:
        for i in range(start, len(lines)):
            if re.sub(r"[^A-Z0-9]", "", lines[i].upper()) == tag:
                positions[tag] = i
                start = i + 1
                break

    out: Dict[str, str] = {}
    ordered_positions = sorted(positions.items(), key=lambda kv: kv[1])
    for idx, (tag, pos) in enumerate(ordered_positions):
        next_pos = ordered_positions[idx + 1][1] if idx + 1 < len(ordered_positions) else min(len(lines), pos + 10)
        for ln in lines[pos + 1:next_pos]:
            code = _normalize_confirmation_code_token(ln)
            if code and code != "RD":
                out[tag] = code
                break
    return out


def _detect_signal_table_bbox(img: Image.Image) -> Optional[Tuple[int, int, int, int]]:
    """Trova automaticamente la tabella azzurra, ovunque sia posizionata nello screenshot.

    Il template usa un fondo azzurro molto chiaro. Lavoriamo su una copia ridotta e
    cerchiamo la componente con area, densità e proporzioni compatibili con la griglia.
    Non usiamo coordinate fisse: la tabella può essere spostata sul grafico.
    """
    max_w = 900
    scale = min(1.0, max_w / max(1, img.width))
    work = img if scale >= 0.999 else img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))))
    arr = np.array(work.convert("RGB"))
    rr = arr[:, :, 0].astype(np.int16)
    gg = arr[:, :, 1].astype(np.int16)
    bb = arr[:, :, 2].astype(np.int16)

    # Fondo della tabella: chiaro, con dominante blu. Esclude trendline ciano e box scuri.
    mask = (rr > 160) & (gg > 170) & (bb > 190) & ((bb - rr) > 10) & ((bb - gg) > 4)
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    candidates: List[Tuple[float, int, int, int, int]] = []

    for y in range(h):
        for x in range(w):
            if not mask[y, x] or seen[y, x]:
                continue
            stack = [(y, x)]
            seen[y, x] = True
            min_x = max_x = x
            min_y = max_y = y
            count = 0
            while stack:
                yy, xx = stack.pop()
                count += 1
                min_x = min(min_x, xx); max_x = max(max_x, xx)
                min_y = min(min_y, yy); max_y = max(max_y, yy)
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = yy + dy, xx + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))

            bw = max_x - min_x + 1
            bh = max_y - min_y + 1
            if bw < max(70, int(w * 0.08)) or bh < max(45, int(h * 0.07)):
                continue
            aspect = bw / max(1, bh)
            density = count / max(1, bw * bh)
            if not (1.15 <= aspect <= 5.0 and density >= 0.35):
                continue
            score = float(count) * density
            candidates.append((score, min_x, min_y, max_x, max_y))

    if not candidates:
        return None
    _, min_x, min_y, max_x, max_y = max(candidates, key=lambda item: item[0])
    inv = 1.0 / scale
    x0 = max(0, int(round(min_x * inv)) - 2)
    y0 = max(0, int(round(min_y * inv)) - 2)
    x1 = min(img.width, int(round((max_x + 1) * inv)) + 2)
    y1 = min(img.height, int(round((max_y + 1) * inv)) + 2)
    return (x0, y0, x1, y1)


def _ocr_signal_table_text(img: Image.Image, bbox: Tuple[int, int, int, int]) -> str:
    """OCR dedicato alla sola tabella, dopo averla individuata automaticamente."""
    crop = ImageOps.grayscale(img.crop(bbox))
    scale = 4
    crop = crop.resize((crop.width * scale, crop.height * scale))
    arr = np.array(crop)
    # Soglia più scura: elimina quasi tutta la griglia azzurra e lascia testo/numeri.
    bw = Image.fromarray(np.where(arr < 160, 0, 255).astype("uint8"))
    return pytesseract.image_to_string(bw, config="--psm 11")


def _ocr_table_context_text(img: Image.Image, bbox: Tuple[int, int, int, int]) -> str:
    """Legge i box colorati (strumento/data e Timeframe) vicini alla tabella.

    Il box Timeframe ha testo bianco su fondo blu/viola: un OCR generale spesso lo
    perde. Individuiamo quindi i rettangoli scuri colorati vicino alla tabella,
    li invertiamo e li leggiamo singolarmente. La posizione assoluta non conta.
    """
    x0, y0, x1, y1 = bbox
    bw = x1 - x0
    bh = y1 - y0
    nx0 = max(0, x0 - int(bw * 0.30))
    nx1 = min(img.width, x1 + int(bw * 1.20))
    ny0 = max(0, y0 - int(bh * 0.30))
    ny1 = min(img.height, y0 + int(bh * 0.60))

    arr = np.array(img.crop((nx0, ny0, nx1, ny1)).convert("RGB"))
    rr = arr[:, :, 0].astype(np.int16)
    gg = arr[:, :, 1].astype(np.int16)
    bb = arr[:, :, 2].astype(np.int16)
    # Blu/viola scuro dei due box del template; esclude quasi tutto il grafico.
    mask = (bb > 80) & ((bb - rr) > 25) & ((bb - gg) > 15) & (rr < 120) & (gg < 150)
    h, w = mask.shape
    seen = np.zeros_like(mask, dtype=bool)
    comps: List[Tuple[int, int, int, int, int]] = []
    for y in range(h):
        for x in range(w):
            if not mask[y, x] or seen[y, x]:
                continue
            stack = [(y, x)]
            seen[y, x] = True
            min_x = max_x = x; min_y = max_y = y; count = 0
            while stack:
                yy, xx = stack.pop(); count += 1
                min_x = min(min_x, xx); max_x = max(max_x, xx)
                min_y = min(min_y, yy); max_y = max(max_y, yy)
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    cy, cx = yy + dy, xx + dx
                    if 0 <= cy < h and 0 <= cx < w and mask[cy, cx] and not seen[cy, cx]:
                        seen[cy, cx] = True; stack.append((cy, cx))
            cw = max_x - min_x + 1; ch = max_y - min_y + 1
            density = count / max(1, cw * ch)
            if cw >= max(60, int(bw * 0.30)) and ch >= max(12, int(bh * 0.06)) and cw / max(1, ch) >= 2.0 and density >= 0.35:
                comps.append((count, min_x, min_y, max_x, max_y))

    texts: List[str] = []
    for _, min_x, min_y, max_x, max_y in sorted(comps, key=lambda c: (c[2], c[1]))[:6]:
        bx0 = max(0, nx0 + min_x - 2); by0 = max(0, ny0 + min_y - 2)
        bx1 = min(img.width, nx0 + max_x + 3); by1 = min(img.height, ny0 + max_y + 3)
        crop = ImageOps.grayscale(img.crop((bx0, by0, bx1, by1)))
        crop = ImageOps.invert(crop).resize((crop.width * 5, crop.height * 5))
        crop = ImageEnhance.Contrast(crop).enhance(2.0)
        try:
            txt = pytesseract.image_to_string(crop, config="--psm 7").strip()
        except Exception:
            txt = ""
        if txt:
            texts.append(txt)
    return "\n".join(texts)

def _table_row_segments(text: str) -> Dict[str, List[str]]:
    """Divide il testo OCR della tabella nelle righe E1/E2/T1/T2/T3/STOP."""
    lines = [re.sub(r"\s+", " ", ln.strip()) for ln in str(text or "").splitlines() if ln.strip()]
    wanted = ["E1", "E2", "T1", "T2", "T3", "STOP"]
    found: List[Tuple[str, int]] = []
    for i, line in enumerate(lines):
        compact = re.sub(r"[^A-Z0-9]", "", line.upper())
        if compact in wanted:
            found.append((compact, i))
    # Se Tesseract duplica un'etichetta, teniamo la prima occorrenza utile.
    unique: List[Tuple[str, int]] = []
    seen_tags = set()
    for tag, pos in found:
        if tag not in seen_tags:
            unique.append((tag, pos)); seen_tags.add(tag)
    unique.sort(key=lambda item: item[1])
    out: Dict[str, List[str]] = {}
    for j, (tag, pos) in enumerate(unique):
        end = unique[j + 1][1] if j + 1 < len(unique) else len(lines)
        out[tag] = lines[pos + 1:end]
    return out


def _numeric_from_table_segment(lines: List[str]) -> Optional[float]:
    for line in lines:
        upper = str(line or "").upper()
        # Evita che M4 venga interpretato come valore 4.
        for m in re.finditer(r"(?<![A-Z0-9])([0-9][0-9\s.,]*)(?![A-Z])", upper):
            value = normalize_number(m.group(1))
            if value is not None:
                return value
    return None


def _parse_timeframe_text(text: str) -> str:
    raw = re.sub(r"\s+", " ", str(text or "")).upper()
    raw = raw.replace("–", "-").replace("—", "-").replace("−", "-")
    m = re.search(r"TIME\s*FRAME\s*([0-9]{1,3})\s*[- ]?\s*(MINUTE|MIN|MINUTI|HOUR|H)?", raw)
    if not m:
        m = re.search(r"TIMEFRAME\s*([0-9]{1,3})\s*[- ]?\s*(MINUTE|MIN|MINUTI|HOUR|H)?", raw)
    if m:
        n = int(m.group(1))
        unit = (m.group(2) or "MIN").upper()
        if unit.startswith("H"):
            return f"{n}H" if f"{n}H" in TIMEFRAMES else "—"
        return {15: "15m", 30: "30m", 60: "1H", 120: "2H", 240: "4H"}.get(n, "—")
    if re.search(r"TIME\s*FRAME\s*DAILY|TIMEFRAME\s*DAILY", raw):
        return "Daily"
    if re.search(r"TIME\s*FRAME\s*WEEKLY|TIMEFRAME\s*WEEKLY", raw):
        return "Weekly"
    if re.search(r"TIME\s*FRAME\s*MONTHLY|TIMEFRAME\s*MONTHLY", raw):
        return "Monthly"
    return "—"


def _checked_rows_from_table_bbox(img: Image.Image, bbox: Tuple[int, int, int, int]) -> List[str]:
    """Rileva le X nella quarta colonna usando il bbox reale della tabella."""
    arr = np.array(img.convert("RGB"))
    x_left, y_top, x_right, y_bottom = bbox
    row_labels = ["HEADER", "E1", "E2", "T1", "T2", "T3", "STOP"]
    # La colonna X è l'ultima e molto stretta. Prendiamo circa l'ultimo 13% del
    # bbox reale della tabella: abbastanza largo per piccole variazioni di scala,
    # ma senza invadere la colonna delle sigle conferma.
    x0 = int(x_left + (x_right - x_left) * 0.87)
    x1 = max(x0 + 2, x_right - 2)
    checked: List[str] = []
    for r, label in enumerate(row_labels):
        yy0 = int(y_top + r * (y_bottom - y_top) / len(row_labels)) + 3
        yy1 = int(y_top + (r + 1) * (y_bottom - y_top) / len(row_labels)) - 3
        if yy1 <= yy0:
            continue
        cell = arr[yy0:yy1, x0:x1]
        if cell.size == 0:
            continue
        rr, gg, bb = cell[:, :, 0], cell[:, :, 1], cell[:, :, 2]
        dark_neutral = (rr < 145) & (gg < 145) & (bb < 145)
        if label != "HEADER" and int(dark_neutral.sum()) >= 8:
            checked.append(label)
    return checked


def extract_signal_table_data(img: Image.Image) -> Optional[Dict[str, Any]]:
    """Estrae la nuova tabella in modo posizionale e indipendente dalla sua posizione."""
    bbox = _detect_signal_table_bbox(img)
    if not bbox:
        return None
    table_text = _ocr_signal_table_text(img, bbox)
    segments = _table_row_segments(table_text)
    if len(segments) < 3:
        return None

    values = {tag.lower(): _numeric_from_table_segment(lines) for tag, lines in segments.items()}
    row_codes: Dict[str, str] = {}
    for tag, lines in segments.items():
        for line in lines:
            code = _normalize_confirmation_code_token(line)
            if code and code != "RD":
                row_codes[tag] = code
                break

    checked_rows = _checked_rows_from_table_bbox(img, bbox)
    confirmations: List[str] = []
    for row_tag in checked_rows:
        code = row_codes.get(row_tag)
        label = CONFIRMATION_CODE_MAP.get(code or "")
        if label and label not in confirmations:
            confirmations.append(label)

    context_text = _ocr_table_context_text(img, bbox)
    header_text = table_text + "\n" + context_text
    direction_match = re.search(r"\b(LONG|SHORT)\b", header_text, flags=re.I)
    setup_origin = "Revolving Door" if re.search(r"(?<![A-Z0-9])RD(?![A-Z0-9])", header_text, flags=re.I) else "—"
    setup_timeframe = _parse_timeframe_text(context_text)
    shared_stop = values.get("stop")

    return {
        "bbox": bbox,
        "table_text": table_text,
        "context_text": context_text,
        "valid_date": parse_date(header_text),
        "direction": direction_match.group(1).upper() if direction_match else "",
        "e1": values.get("e1"),
        "e2": values.get("e2"),
        "t1": values.get("t1"),
        "t2": values.get("t2"),
        "t3": values.get("t3"),
        "shared_stop": shared_stop,
        "setup_origin": setup_origin,
        "setup_timeframe": setup_timeframe,
        "confirmations": confirmations,
        "row_codes": row_codes,
        "checked_rows": checked_rows,
    }


def extract_confirmations_from_table_image(img: Image.Image, ocr_text: str = "") -> Optional[List[str]]:
    """Compatibilità: usa il nuovo rilevamento dinamico della tabella."""
    data = extract_signal_table_data(img)
    return None if data is None else list(data.get("confirmations") or [])

def _normalize_instrument_text(value: Any) -> str:
    """Normalizza punteggiatura/spazi OCR per riconoscere in modo robusto gli strumenti."""
    s = str(value or "").lower()
    s = s.replace("’", "'").replace("`", "'").replace("´", "'")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _known_instrument_from_text(value: Any) -> Optional[Tuple[str, str]]:
    txt = _normalize_instrument_text(value)
    if not txt:
        return None
    ordered = sorted(
        INSTRUMENT_ALIASES,
        key=lambda k: len(_normalize_instrument_text(k)),
        reverse=True,
    )
    for key in ordered:
        key_norm = _normalize_instrument_text(key)
        if not key_norm:
            continue
        if re.search(r"(?<![a-z0-9])" + re.escape(key_norm) + r"(?![a-z0-9])", txt):
            return INSTRUMENT_ALIASES[key]
    return None


def canonical_instrument_label(value: Any) -> str:
    """Ripulisce anche vecchi record OCR già salvati, senza alterare il database."""
    found = _known_instrument_from_text(value)
    return found[0] if found else str(value or "").strip()


def normalize_level_for_instrument(instrument: Any, value: Any) -> Optional[float]:
    """Corregge il punto usato come separatore delle migliaia sui grafici europei."""
    v = _numeric_or_none(value)
    if v is None:
        return None
    label = canonical_instrument_label(instrument).upper()
    # Esempi TradingView in locale IT: 6.407 = 6407; 23.950 = 23950.
    if label == "EURO STOXX 50" and 1.0 <= abs(v) < 20.0:
        return v * 1000.0
    if label == "DAX" and 10.0 <= abs(v) < 100.0:
        return v * 1000.0
    return v


def signal_level_value(row: Dict[str, Any], field: str) -> Optional[float]:
    return normalize_level_for_instrument(row.get("instrument"), row.get(field))


def infer_instrument(top_text: str, full_text: str) -> Tuple[str, str]:
    combined = top_text + "\n" + full_text
    found = _known_instrument_from_text(combined)
    if found:
        return found
    for line in top_text.splitlines():
        clean = line.strip()
        if clean and len(clean) >= 3 and "tradingview" not in clean.lower():
            clean = re.split(r"\s+[·|]\s+", clean, maxsplit=1)[0].strip()
            return clean[:80], ""
    return "", ""


def parse_signal(full_text: str, top_text: str) -> Dict[str, Any]:
    # La fascia superiore ha priorità perché contiene la nuova tabella ed evita che
    # le etichette ripetute sul grafico interferiscano con E1/E2/T1/T2/T3/Stop.
    combined = top_text + "\n" + full_text
    direction_match = re.search(r"\b(LONG|SHORT)\b", top_text, flags=re.I) or re.search(r"\b(LONG|SHORT)\b", combined, flags=re.I)
    instrument, ticker = infer_instrument(top_text, full_text)
    table_meta = parse_table_metadata(top_text)
    full_meta = parse_table_metadata(full_text)
    if table_meta.get("setup_origin") == "—" and full_meta.get("setup_origin") != "—":
        table_meta["setup_origin"] = full_meta.get("setup_origin")
    if table_meta.get("setup_timeframe") == "—" and full_meta.get("setup_timeframe") != "—":
        table_meta["setup_timeframe"] = full_meta.get("setup_timeframe")
    if not table_meta.get("confirmations") and full_meta.get("confirmations"):
        table_meta["confirmations"] = full_meta.get("confirmations")

    shared_stop = extract_shared_stop_value(top_text) or extract_shared_stop_value(full_text)
    s1_value = extract_tag_value(top_text, "S1")
    s2_value = extract_tag_value(top_text, "S2")
    if shared_stop is not None:
        # Nel nuovo formato c'è un solo Stop comune ai due livelli di entry.
        if s1_value is None:
            s1_value = shared_stop
        if s2_value is None:
            s2_value = shared_stop

    parsed = {
        "valid_date": parse_date(top_text) or parse_date(combined),
        "instrument": instrument,
        "ticker": ticker,
        "direction": direction_match.group(1).upper() if direction_match else "",
        "e1": extract_tag_value(top_text, "E1") or extract_tag_value(combined, "E1"),
        "s1": s1_value if s1_value is not None else extract_tag_value(combined, "S1"),
        "e2": extract_tag_value(top_text, "E2") or extract_tag_value(combined, "E2"),
        "s2": s2_value if s2_value is not None else extract_tag_value(combined, "S2"),
        "t1": extract_tag_value(top_text, "T1") or extract_tag_value(combined, "T1"),
        "t2": extract_tag_value(top_text, "T2") or extract_tag_value(combined, "T2"),
        "t3": extract_tag_value(top_text, "T3") or extract_tag_value(combined, "T3"),
        "setup_origin": table_meta.get("setup_origin", "—"),
        "setup_timeframe": table_meta.get("setup_timeframe", "—"),
        "confirmations": table_meta.get("confirmations", []),
    }
    for field in ("e1", "s1", "e2", "s2", "t1", "t2", "t3"):
        parsed[field] = normalize_level_for_instrument(instrument, parsed.get(field))
    return parsed


# -----------------------------------------------------------------------------
# Supabase: database + storage persistente
# -----------------------------------------------------------------------------

def confirmations_list(value: Any) -> List[str]:
    if isinstance(value, list):
        parsed = [str(x) for x in value]
    elif isinstance(value, str) and value.strip():
        try:
            obj = __import__("json").loads(value)
            parsed = [str(x) for x in obj] if isinstance(obj, list) else []
        except Exception:
            parsed = []
    else:
        parsed = []

    aliases = {"FIBO": "Fibonacci", "Fibo": "Fibonacci", "DIV.": "Divergenze"}
    out: List[str] = []
    for item in parsed:
        name = aliases.get(item, item)
        # Bollinger, Price Action e News sono stati rimossi dalla metodologia.
        if name in CONFIRMATIONS and name not in out:
            out.append(name)
    return out


def upload_screenshot(uploaded_file) -> str:
    raw = uploaded_file.getvalue()
    digest = hashlib.sha1(raw).hexdigest()[:12]
    suffix = Path(uploaded_file.name).suffix.lower() or ".png"
    user_folder = current_role() or "unknown"
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
    actor_id = audit_user_id()
    if actor_id:
        payload["created_by"] = actor_id
        payload["updated_by"] = actor_id
    res = user_client().table("signals").insert(payload).execute()
    rows = res.data or []
    if not rows:
        raise RuntimeError("Il database non ha restituito il segnale appena salvato.")
    return int(rows[0]["id"])


def load_signals() -> pd.DataFrame:
    res = user_client().table("signals").select("*").order("valid_date", desc=True).order("id", desc=True).execute()
    rows = res.data or []
    df = pd.DataFrame(rows)
    if not df.empty and "instrument" in df.columns:
        df["instrument"] = df["instrument"].map(canonical_instrument_label)
    return df


def load_signal(signal_id: int) -> Optional[Dict[str, Any]]:
    res = user_client().table("signals").select("*").eq("id", int(signal_id)).limit(1).execute()
    rows = res.data or []
    return rows[0] if rows else None


def update_signal(signal_id: int, **kwargs) -> None:
    if not kwargs:
        return
    actor_id = audit_user_id()
    if actor_id:
        kwargs["updated_by"] = actor_id
    kwargs["updated_at"] = now_iso()
    user_client().table("signals").update(kwargs).eq("id", int(signal_id)).execute()


def delete_signal(signal_id: int) -> None:
    user_client().table("signals").delete().eq("id", int(signal_id)).execute()


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
    """Modifica del segnale in stile G. Slide Signal MV: il trade reale resta separato e facoltativo."""
    if not can_write():
        return

    sid = int(row["id"])
    current_conf = confirmations_list(row.get("confirmations"))
    existing_entry = _numeric_or_none(row.get("actual_entry"))
    existing_stop = _numeric_or_none(row.get("actual_stop"))
    has_real_trade = existing_entry is not None and existing_stop is not None
    has_trade_data = has_real_trade or existing_entry is not None or existing_stop is not None or bool(row.get("entry_time"))
    current_entry_dt = _local_datetime_from_db(row.get("entry_time")) if row.get("entry_time") else local_now()

    if str(key_prefix).startswith("dashboard_detail_"):
        st.markdown("#### Modifica segnale")

    # ------------------------------------------------------------------
    # Modifica del SEGNALE. Entry/Stop reali NON sono richiesti qui.
    # È lo stesso principio usato in G. Slide Signal MV: si può correggere
    # il setup senza dover dichiarare prematuramente un trade reale.
    # ------------------------------------------------------------------
    with st.form(f"{key_prefix}_edit_signal_{sid}"):
        c1, c2, c3 = st.columns(3)
        try:
            current_date = date.fromisoformat(str(row.get("valid_date")))
        except Exception:
            current_date = local_now().date()
        valid_date_edit = c1.date_input("Data di validità", value=current_date, key=f"{key_prefix}_date_{sid}")
        instrument_edit = c2.text_input(
            "Strumento", value=canonical_instrument_label(row.get("instrument")), key=f"{key_prefix}_instr_{sid}"
        )
        direction_edit = c3.selectbox(
            "Direzione", ["LONG", "SHORT"],
            index=_option_index(["LONG", "SHORT"], row.get("direction")),
            key=f"{key_prefix}_dir_{sid}",
        )
        ticker_edit = st.text_input(
            "Ticker Yahoo Finance", value=effective_yahoo_ticker(row), key=f"{key_prefix}_ticker_{sid}"
        )

        a1, a2, a3, a4 = st.columns(4)
        e1_edit = normalize_number(a1.text_input("E1 indicativa", fmt_num(signal_level_value(row, "e1")), key=f"{key_prefix}_e1_{sid}"))
        s1_edit = normalize_number(a2.text_input("S1 indicativo", fmt_num(signal_level_value(row, "s1")), key=f"{key_prefix}_s1_{sid}"))
        e2_edit = normalize_number(a3.text_input("E2 indicativa", fmt_num(signal_level_value(row, "e2")), key=f"{key_prefix}_e2_{sid}"))
        s2_edit = normalize_number(a4.text_input("S2 indicativo", fmt_num(signal_level_value(row, "s2")), key=f"{key_prefix}_s2_{sid}"))
        b1, b2, b3 = st.columns(3)
        t1_edit = normalize_number(b1.text_input("T1", fmt_num(signal_level_value(row, "t1")), key=f"{key_prefix}_t1_{sid}"))
        t2_edit = normalize_number(b2.text_input("T2", fmt_num(signal_level_value(row, "t2")), key=f"{key_prefix}_t2_{sid}"))
        t3_edit = normalize_number(b3.text_input("T3", fmt_num(signal_level_value(row, "t3")), key=f"{key_prefix}_t3_{sid}", help="Facoltativo. Se vuoto viene ignorato."))

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

        save_edit = st.form_submit_button("💾 Salva modifiche", type="primary", use_container_width=True)

    if save_edit:
        errors: List[str] = []
        if not instrument_edit.strip():
            errors.append("strumento")
        if t1_edit is None:
            errors.append("T1")
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
        # T3 è facoltativo: se non compilato viene ignorato. Se esisteva già, può essere svuotato.
        if t3_edit is not None or _numeric_or_none(row.get("t3")) is not None:
            updates["t3"] = t3_edit

        # Se esiste già un trade reale, una modifica a target/direzione/ticker
        # richiede il ricalcolo del monitoraggio, ma NON richiede di reinserire Entry/Stop.
        monitoring_changed = False
        if has_real_trade:
            monitoring_changed = (
                _num_changed(row.get("t1"), t1_edit)
                or _num_changed(row.get("t2"), t2_edit)
                or _num_changed(row.get("t3"), t3_edit)
                or str(row.get("direction") or "") != direction_edit
                or str(row.get("ticker") or "").strip() != ticker_edit.strip()
            )
        if monitoring_changed:
            updates.update({
                "status": "IN TRADE",
                "outcome": None,
                "t1_hit_time": None,
                "t2_hit_time": None,
                "stop_hit_time": None,
                "result_note": "Dati del segnale corretti; monitoraggio da ricalcolare",
                "last_check": None,
            })
            if t3_edit is not None or _numeric_or_none(row.get("t3")) is not None:
                updates["t3_hit_time"] = None

        try:
            update_signal(sid, **updates)
            success_message = (
                "Modifiche salvate. Il monitoraggio verrà ricalcolato con i nuovi dati."
                if monitoring_changed else "Modifiche salvate."
            )
            if str(key_prefix).startswith("dashboard_detail_"):
                st.session_state["dashboard_flash_message"] = success_message
                st.session_state["dashboard_table_version"] = int(st.session_state.get("dashboard_table_version", 0)) + 1
            else:
                st.session_state["edit_flash_message"] = success_message
            st.rerun()
        except Exception as e:
            msg = str(e)
            if "PGRST204" in msg and ("t3" in msg.lower() or "t3_hit_time" in msg.lower()):
                st.error("Per salvare T3 serve la migration Supabase V3.7 (colonne t3 e t3_hit_time). Se non vuoi usare T3, lascia semplicemente il campo T3 vuoto.")
            else:
                st.error(f"Modifica non riuscita: {e}")

    # ------------------------------------------------------------------
    # Trade reale separato: non blocca mai il salvataggio del setup.
    # Si apre/compila solo quando l'ingresso è realmente deciso.
    # ------------------------------------------------------------------
    with st.expander("Trade reale — compila solo quando entri", expanded=has_trade_data):
        st.caption("Entry e Stop reali sono facoltativi finché il setup resta in attesa. Compilali entrambi solo quando il trade viene realmente eseguito.")
        with st.form(f"{key_prefix}_real_trade_{sid}"):
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
            save_trade = st.form_submit_button(
                "💾 Registra / aggiorna trade reale", type="primary", use_container_width=True
            )

        if save_trade:
            if actual_entry_edit is None or actual_stop_edit is None:
                st.error("Per registrare il trade reale compila sia Entry effettiva sia Stop effettivo.")
            else:
                new_entry_dt = datetime.combine(entry_date_edit, entry_time_edit, tzinfo=LOCAL_TZ)
                trade_updates: Dict[str, Any] = {
                    "actual_entry": actual_entry_edit,
                    "actual_stop": actual_stop_edit,
                    "entry_time": new_entry_dt.isoformat(timespec="seconds"),
                    "status": "IN TRADE",
                    "outcome": None,
                    "t1_hit_time": None,
                    "t2_hit_time": None,
                    "stop_hit_time": None,
                    "result_note": "Trade reale registrato o corretto; monitoraggio da ricalcolare",
                    "last_check": None,
                }
                if t3_edit is not None or _numeric_or_none(row.get("t3")) is not None:
                    trade_updates["t3_hit_time"] = None
                try:
                    update_signal(sid, **trade_updates)
                    message = "Trade reale registrato. Il monitoraggio partirà dai dati effettivi."
                    if str(key_prefix).startswith("dashboard_detail_"):
                        st.session_state["dashboard_flash_message"] = message
                        st.session_state["dashboard_table_version"] = int(st.session_state.get("dashboard_table_version", 0)) + 1
                    else:
                        st.session_state["edit_flash_message"] = message
                    st.rerun()
                except Exception as e:
                    msg = str(e)
                    if "PGRST204" in msg and "t3_hit_time" in msg.lower():
                        st.error("Per salvare T3 serve la migration Supabase V3.7. Se non vuoi usare T3, lascia semplicemente il campo T3 vuoto.")
                    else:
                        st.error(f"Registrazione trade non riuscita: {e}")

    if not has_real_trade and str(row.get("status") or "") == "PUBBLICATO":
        st.divider()
        st.caption("Se la dinamica non offre un ingresso valido puoi chiudere il setup senza conteggiarlo come perdita.")
        c1, c2 = st.columns(2)
        if c1.button("⚪ NESSUN TRADE", key=f"{key_prefix}_no_trade_{sid}", use_container_width=True):
            update_signal(sid, status="NESSUN TRADE", outcome="NESSUN TRADE", result_note="Segnale non eseguito")
            if str(key_prefix).startswith("dashboard_detail_"):
                st.session_state["dashboard_table_version"] = int(st.session_state.get("dashboard_table_version", 0)) + 1
            st.rerun()
        if c2.button("⛔ SETUP ANNULLATO", key=f"{key_prefix}_cancel_{sid}", use_container_width=True):
            update_signal(sid, status="ANNULLATO", outcome="ANNULLATO", result_note="Setup annullato")
            if str(key_prefix).startswith("dashboard_detail_"):
                st.session_state["dashboard_table_version"] = int(st.session_state.get("dashboard_table_version", 0)) + 1
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
    """Ticker Yahoo effettivo, con correzione dei principali indici europei."""
    found = _known_instrument_from_text(row.get("instrument"))
    if found and found[0] in {"DAX", "EURO STOXX 50"}:
        return found[1]
    stored = str(row.get("ticker") or "").strip()
    if stored:
        return stored
    return found[1] if found else ""


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
    """Restituisce il prossimo target attivo (T1/T2/T3), distanza in punti e percentuale."""
    if current_price is None:
        return None, None, None
    status = str(row.get("status") or "")
    if status not in {"IN TRADE", "T1 RAGGIUNTO", "T2 RAGGIUNTO"}:
        return None, None, None

    if status == "T2 RAGGIUNTO":
        label = "T3"
        target = signal_level_value(row, "t3")
    elif status == "T1 RAGGIUNTO":
        label = "T2"
        target = signal_level_value(row, "t2")
    else:
        label = "T1"
        target = signal_level_value(row, "t1")

    target_value = _numeric_or_none(target)
    if target_value is None:
        return None, None, None
    try:
        price = float(current_price)
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
    status = str(row.get("status") or "")
    if status == "T1 RAGGIUNTO":
        return "T1 OK - T2 IN ATTESA"
    if status == "T2 RAGGIUNTO":
        return "T2 OK - T3 IN ATTESA"
    return status or "—"


def evaluate_trade(row: Dict[str, Any]) -> Dict[str, Optional[str]]:
    ticker = effective_yahoo_ticker(row)
    if not ticker or not row.get("entry_time") or row.get("actual_entry") is None or row.get("actual_stop") is None:
        return {"status": row.get("status"), "outcome": row.get("outcome"), "note": "Dati trade incompleti"}
    try:
        start_dt = datetime.fromisoformat(str(row["entry_time"]).replace("Z", "+00:00"))
    except Exception:
        return {"status": row.get("status"), "outcome": row.get("outcome"), "note": "Ora ingresso non valida"}

    df, interval = fetch_intraday(ticker, start_dt)
    if df.empty:
        return {"status": row.get("status"), "outcome": row.get("outcome"), "note": "Dati prezzo non disponibili"}

    # L'ultima chiusura della serie intraday è riutilizzata anche come prezzo corrente in UI.
    try:
        closes = df["Close"].dropna()
        if not closes.empty:
            market_ts = closes.index[-1]
            source = f"Yahoo Finance · ultimo dato {market_ts}"
            _store_market_quote(ticker, float(closes.iloc[-1]), local_now(), source)
    except Exception:
        pass

    direction = str(row["direction"]).upper()
    stop = float(row["actual_stop"])
    t1 = signal_level_value(row, "t1")
    t2 = signal_level_value(row, "t2")
    t3 = signal_level_value(row, "t3")
    t1_time = row.get("t1_hit_time")
    t2_time = row.get("t2_hit_time")
    t3_time = row.get("t3_hit_time")
    stop_time = row.get("stop_hit_time")
    t1_done = bool(t1_time)
    t2_done = bool(t2_time)
    t3_done = bool(t3_time)

    for ts, bar in df.iterrows():
        high, low = float(bar["High"]), float(bar["Low"])
        if direction == "LONG":
            hit_stop = low <= stop
            hit_t1 = t1 is not None and high >= t1 and not t1_done
            hit_t2 = t2 is not None and high >= t2 and not t2_done
            hit_t3 = t3 is not None and high >= t3 and not t3_done
        else:
            hit_stop = high >= stop
            hit_t1 = t1 is not None and low <= t1 and not t1_done
            hit_t2 = t2 is not None and low <= t2 and not t2_done
            hit_t3 = t3 is not None and low <= t3 and not t3_done

        if hit_stop and (hit_t1 or hit_t2 or hit_t3):
            if t2_done:
                ambiguous_outcome = "AMBIGUO DOPO T2"
            elif t1_done:
                ambiguous_outcome = "AMBIGUO DOPO T1"
            else:
                ambiguous_outcome = "AMBIGUO"
            return {
                "status": "AMBIGUO",
                "outcome": ambiguous_outcome,
                "t1_hit_time": t1_time,
                "t2_hit_time": t2_time,
                "t3_hit_time": t3_time,
                "stop_hit_time": stop_time,
                "note": f"Stop e target nella stessa barra {interval}; ordine non determinabile.",
            }

        if hit_t1:
            t1_done = True
            t1_time = ts.isoformat()
        if hit_t2:
            t2_done = True
            t2_time = ts.isoformat()
        if hit_t3:
            t3_done = True
            t3_time = ts.isoformat()
            return {
                "status": "CHIUSO", "outcome": "T3",
                "t1_hit_time": t1_time, "t2_hit_time": t2_time, "t3_hit_time": t3_time,
                "stop_hit_time": stop_time,
                "note": f"T3 raggiunto; controllo con barre {interval}.",
            }

        # Se T3 non è previsto, T2 resta il target finale come nelle versioni precedenti.
        if hit_t2 and t3 is None:
            return {
                "status": "CHIUSO", "outcome": "T2",
                "t1_hit_time": t1_time, "t2_hit_time": t2_time, "t3_hit_time": t3_time,
                "stop_hit_time": stop_time,
                "note": f"T2 raggiunto; controllo con barre {interval}.",
            }

        if hit_stop:
            stop_time = ts.isoformat()
            if t2_done:
                outcome = "T2 + STOP"
            elif t1_done:
                outcome = "T1 + STOP"
            else:
                outcome = "STOP"
            return {
                "status": "CHIUSO", "outcome": outcome,
                "t1_hit_time": t1_time, "t2_hit_time": t2_time, "t3_hit_time": t3_time,
                "stop_hit_time": stop_time,
                "note": f"Stop raggiunto; controllo con barre {interval}.",
            }

    if t2_done and t3 is not None:
        return {
            "status": "T2 RAGGIUNTO", "outcome": None,
            "t1_hit_time": t1_time, "t2_hit_time": t2_time, "t3_hit_time": t3_time,
            "stop_hit_time": stop_time,
            "note": f"T2 raggiunto; T3 ancora in attesa. Controllo con barre {interval}.",
        }
    if t1_done:
        return {
            "status": "T1 RAGGIUNTO", "outcome": None,
            "t1_hit_time": t1_time, "t2_hit_time": t2_time, "t3_hit_time": t3_time,
            "stop_hit_time": stop_time,
            "note": f"T1 raggiunto; T2 ancora in attesa. Controllo con barre {interval}.",
        }
    return {
        "status": "IN TRADE", "outcome": None,
        "t1_hit_time": t1_time, "t2_hit_time": t2_time, "t3_hit_time": t3_time,
        "stop_hit_time": stop_time,
        "note": f"T1 non ancora raggiunto; controllo con barre {interval}.",
    }


def update_all_open_trades() -> Tuple[int, List[str]]:
    df = load_signals()
    if df.empty:
        return 0, []
    df = df[df["status"].isin(["IN TRADE", "T1 RAGGIUNTO", "T2 RAGGIUNTO"])]
    updated = 0
    notes: List[str] = []
    for _, r in df.iterrows():
        row = load_signal(int(r["id"]))
        if row is None:
            continue
        try:
            res = evaluate_trade(row)
            update_kwargs = {
                "status": res.get("status") or row.get("status"),
                "outcome": res.get("outcome"),
                "t1_hit_time": res.get("t1_hit_time"),
                "t2_hit_time": res.get("t2_hit_time"),
                "stop_hit_time": res.get("stop_hit_time"),
                "result_note": res.get("note", ""),
                "last_check": now_iso(),
            }
            # Non tocchiamo t3_hit_time se questo trade non usa T3.
            # Evita errori PGRST204 sui database che non hanno ancora la migration T3.
            if _numeric_or_none(row.get("t3")) is not None:
                update_kwargs["t3_hit_time"] = res.get("t3_hit_time")
            update_signal(int(row["id"]), **update_kwargs)
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
    "T2 RAGGIUNTO": "TRADE ATTIVATO · T2",
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
    if "instrument" in out.columns:
        out["instrument"] = out["instrument"].map(canonical_instrument_label)
    for c in ["e1", "s1", "e2", "s2", "t1", "t2", "t3"]:
        if c in out.columns:
            out[c] = df.apply(
                lambda r: "—" if signal_level_value(r.to_dict(), c) is None else fmt_num(signal_level_value(r.to_dict(), c)),
                axis=1,
            )
    for c in ["actual_entry", "actual_stop"]:
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
    show_t3 = False
    if "t3" in df.columns:
        show_t3 = any(_numeric_or_none(v) is not None for v in df["t3"].tolist())
    cols = ["id", "valid_date", "instrument", "direction", "e1", "e2", "t1", "t2"]
    if show_t3:
        cols.append("t3")
    cols.extend(["setup_origin", "confirmations", "actual_entry", "actual_stop", "status", "outcome"])
    return out[[c for c in cols if c in out.columns]].rename(columns={
        "id": "ID", "valid_date": "Data", "instrument": "Strumento", "direction": "Dir.",
        "e1": "E1", "e2": "E2", "t1": "T1", "t2": "T2", "t3": "T3", "setup_origin": "Origine",
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
        elif status == "T2 RAGGIUNTO":
            if _numeric_or_none(raw.get("t3")) is not None:
                display.at[idx, "Stato"] = "T2 OK - T3 IN ATTESA"
                display.at[idx, "Esito"] = "—"
            else:
                display.at[idx, "Stato"] = "CHIUSO"
                display.at[idx, "Esito"] = "T2"
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
            if status in {"IN TRADE", "T1 RAGGIUNTO", "T2 RAGGIUNTO"}:
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

        # L'ID è il punto di apertura del dettaglio: lo rendiamo visivamente riconoscibile.
        set_style("ID", "color: #4da3ff; font-weight: 700;")

        status = str(raw.get("status") or "")
        outcome = str(raw.get("outcome") or "")

        # Evidenzia target/stop solo in base all'esito operativo conclusivo.
        # Evita falsi positivi causati da NaN/NaT nei timestamp del DataFrame.
        if status == "T2 RAGGIUNTO" or (status == "CHIUSO" and outcome in {"T2", "T3", "T2 + STOP"}):
            set_style("T2", "background-color: #0b7a3b; color: white; font-weight: 700;")
        if status == "CHIUSO" and outcome == "T3":
            set_style("T3", "background-color: #0b7a3b; color: white; font-weight: 700;")
        if status == "CHIUSO" and "STOP" in outcome:
            set_style("Stop reale", "background-color: #8b2f2f; color: white; font-weight: 700;")
        if status == "T1 RAGGIUNTO":
            css = "background-color: #1f6f3d; color: white; font-weight: 700;"
        elif status == "T2 RAGGIUNTO":
            css = "background-color: #0b7a3b; color: white; font-weight: 700;"
        elif status == "CHIUSO" and outcome in {"T2", "T3"}:
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
    active_statuses = {"PUBBLICATO", "IN TRADE", "T1 RAGGIUNTO", "T2 RAGGIUNTO"}
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


def _reset_new_signal_widget_state() -> None:
    """Azzera i widget del form Nuovo segnale prima di applicare un nuovo risultato OCR.

    Streamlit conserva i valori dei widget in session_state. Senza questo reset,
    dopo un redeploy o una nuova lettura dello stesso screenshot possono restare
    valori vecchi (per esempio E1 o checkbox conferme) anche se l'OCR nuovo è corretto.
    """
    prefixes = (
        "new_date_", "new_instrument_", "new_direction_", "new_ticker_",
        "new_e1_", "new_s1_", "new_e2_", "new_s2_",
        "new_t1_", "new_t2_", "new_t3_",
        "new_origin_", "new_reference_", "new_setup_tf_",
        "new_conf_", "new_notes_", "new_distinct_",
    )
    for key in list(st.session_state.keys()):
        if any(str(key).startswith(prefix) for prefix in prefixes):
            try:
                del st.session_state[key]
            except Exception:
                pass


def extract_signal_payload_from_image(img: Image.Image) -> Dict[str, Any]:
    """Esegue l'intera pipeline OCR sullo screenshot e restituisce i campi del segnale."""
    full_text, top_text = run_ocr(img)
    parsed = parse_signal(full_text, top_text)

    # Nuovo motore dedicato alla tabella: la individua ovunque sia posizionata,
    # legge righe/valori, X, RD e il box Timeframe adiacente.
    table_data = extract_signal_table_data(img)
    if table_data:
        for field in ("valid_date", "direction", "e1", "e2", "t1", "t2", "t3"):
            value = table_data.get(field)
            if value not in (None, ""):
                parsed[field] = value
        shared_stop = table_data.get("shared_stop")
        if shared_stop is not None:
            parsed["s1"] = shared_stop
            parsed["s2"] = shared_stop
        if table_data.get("setup_origin") not in (None, "", "—"):
            parsed["setup_origin"] = table_data["setup_origin"]
        if table_data.get("setup_timeframe") not in (None, "", "—"):
            parsed["setup_timeframe"] = table_data["setup_timeframe"]
        parsed["confirmations"] = list(table_data.get("confirmations") or [])

    chart_levels = extract_chart_levels_from_lines(img)
    for field in ("e1", "s1", "e2", "s2", "t1", "t2", "t3"):
        if parsed.get(field) is None and chart_levels.get(field) is not None:
            parsed[field] = normalize_level_for_instrument(parsed.get("instrument"), chart_levels[field])
        else:
            parsed[field] = normalize_level_for_instrument(parsed.get("instrument"), parsed.get(field))

    return {
        **parsed,
        "full_text": full_text,
        "top_text": top_text,
        "chart_levels": chart_levels,
        "table_data": table_data or {},
    }


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
        st.session_state["ocr_generation"] = 0

    img = Image.open(io.BytesIO(raw)).convert("RGB")
    st.image(img, caption=f"Anteprima · {uploaded.name}", use_container_width=True)

    if st.button("🔎 Leggi screenshot", type="primary"):
        try:
            with st.spinner("Lettura OCR in corso..."):
                ocr_payload = extract_signal_payload_from_image(img)
                # Prima di mostrare i nuovi valori OCR eliminiamo gli eventuali valori
                # vecchi dei widget. Questo evita casi in cui E1 o una conferma restano
                # quelli della lettura precedente nonostante l'OCR attuale sia corretto.
                _reset_new_signal_widget_state()
                st.session_state["ocr_data"] = ocr_payload
                st.session_state["ocr_error"] = None
                st.session_state["ocr_generation"] = int(st.session_state.get("ocr_generation", 0)) + 1
        except Exception as e:
            st.session_state["ocr_error"] = str(e)

    if st.session_state.get("ocr_error"):
        st.error(st.session_state["ocr_error"])
        st.caption("Puoi comunque proseguire inserendo i dati manualmente.")

    ocr = st.session_state.get("ocr_data") or {
        "valid_date": None, "instrument": "", "ticker": "", "direction": "",
        "e1": None, "s1": None, "e2": None, "s2": None, "t1": None, "t2": None, "t3": None,
        "setup_origin": "—", "setup_timeframe": "—", "confirmations": [],
        "full_text": "", "top_text": "", "chart_levels": {}, "table_data": {},
    }

    form_generation = int(st.session_state.get("ocr_generation", 0))
    form_suffix = f"{APP_VERSION.replace('.', '_')}_{file_hash[:12]}_{form_generation}"

    with st.form(f"signal_form_{form_suffix}"):
        st.markdown("#### 1. Segnale originale")
        c1, c2, c3 = st.columns(3)
        default_date = date.fromisoformat(ocr["valid_date"]) if ocr.get("valid_date") else local_now().date()
        valid_date = c1.date_input("Data di validità", value=default_date, key=f"new_date_{form_suffix}")
        instrument = c2.text_input("Strumento", value=ocr.get("instrument", ""), key=f"new_instrument_{form_suffix}")
        d_idx = 0 if ocr.get("direction") != "SHORT" else 1
        direction = c3.selectbox("Direzione", ["LONG", "SHORT"], index=d_idx, key=f"new_direction_{form_suffix}")
        ticker = st.text_input(
            "Ticker Yahoo Finance", value=ocr.get("ticker", ""),
            help="Esempio GOLD = GC=F, NASDAQ = NQ=F. Correggibile manualmente.",
            key=f"new_ticker_{form_suffix}",
        )

        a1, a2, a3, a4 = st.columns(4)
        e1 = normalize_number(a1.text_input("E1 indicativa", fmt_num(ocr.get("e1")), key=f"new_e1_{form_suffix}"))
        s1 = normalize_number(a2.text_input("S1 indicativo", fmt_num(ocr.get("s1")), key=f"new_s1_{form_suffix}"))
        e2 = normalize_number(a3.text_input("E2 indicativa", fmt_num(ocr.get("e2")), key=f"new_e2_{form_suffix}"))
        s2 = normalize_number(a4.text_input("S2 indicativo", fmt_num(ocr.get("s2")), key=f"new_s2_{form_suffix}"))
        b1, b2, b3 = st.columns(3)
        t1 = normalize_number(b1.text_input("T1", fmt_num(ocr.get("t1")), key=f"new_t1_{form_suffix}"))
        t2 = normalize_number(b2.text_input("T2", fmt_num(ocr.get("t2")), key=f"new_t2_{form_suffix}"))
        t3 = normalize_number(b3.text_input("T3", fmt_num(ocr.get("t3")), key=f"new_t3_{form_suffix}", help="Facoltativo. Se vuoto viene ignorato."))

        st.markdown("#### 2. Contesto del setup — facoltativo")
        c1, c2, c3 = st.columns(3)
        origin_default = str(ocr.get("setup_origin") or "—")
        origin_index = SETUP_ORIGINS.index(origin_default) if origin_default in SETUP_ORIGINS else 0
        setup_origin = c1.selectbox(
            "Origine del setup", SETUP_ORIGINS, index=origin_index,
            key=f"new_origin_{form_suffix}",
        )
        reference_area = c2.text_input("Livello / area Balance o svolta", placeholder="es. 4365–4398", key=f"new_reference_{form_suffix}")
        tf_default = str(ocr.get("setup_timeframe") or "—")
        tf_index = TIMEFRAMES.index(tf_default) if tf_default in TIMEFRAMES else 0
        setup_tf = c3.selectbox(
            "Timeframe del riferimento", TIMEFRAMES, index=tf_index,
            key=f"new_setup_tf_{form_suffix}",
        )
        st.markdown("**Conferme osservate — tutte facoltative**")
        cols = st.columns(4)
        confirmations: List[str] = []
        ocr_confirmations = confirmations_list(ocr.get("confirmations"))
        for i, name in enumerate(CONFIRMATIONS):
            if cols[i % 4].checkbox(
                name,
                value=name in ocr_confirmations,
                key=f"new_conf_{form_suffix}_{i}",
            ):
                confirmations.append(name)
        notes = st.text_area("Note / motivazione del setup", placeholder="Scrivi solo se serve. Campo facoltativo.", key=f"new_notes_{form_suffix}")
        distinct_signal = st.checkbox(
            "È un nuovo segnale distinto anche se esiste già lo stesso strumento/direzione nella stessa giornata",
            value=False,
            help="Lascia deselezionato normalmente. Serve solo quando la sala pubblica davvero più setup separati sullo stesso strumento nella stessa giornata.",
            key=f"new_distinct_{form_suffix}",
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
                payload = {
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
                }
                if t3 is not None:
                    payload["t3"] = t3
                signal_id = insert_signal(payload)
            st.success(f"Segnale #{signal_id} salvato.")
            st.session_state["ocr_hash"] = None
            st.session_state["ocr_data"] = None
        except Exception as e:
            if screenshot_path:
                remove_screenshot(screenshot_path)
            msg = str(e)
            if "PGRST204" in msg and ("t3" in msg.lower() or "t3_hit_time" in msg.lower()):
                st.error("Per salvare T3 serve la migration Supabase V3.7 (colonne t3 e t3_hit_time). Se non vuoi usare T3, lascia semplicemente il campo T3 vuoto.")
            else:
                st.error(f"Salvataggio non riuscito: {e}")

    if ocr.get("full_text"):
        with st.expander("Testo letto dall'OCR"):
            if ocr.get("chart_levels"):
                detected = " · ".join(f"{k.upper()} {fmt_num(v)}" for k, v in ocr["chart_levels"].items())
                st.caption(f"Livelli letti direttamente dalle linee/scala destra: {detected}")
            td = ocr.get("table_data") or {}
            if td:
                st.caption(
                    "Tabella rilevata automaticamente · "
                    f"X: {', '.join(td.get('checked_rows') or []) or 'nessuna'} · "
                    f"TF: {td.get('setup_timeframe') or '—'}"
                )
                if td.get("table_text"):
                    st.code(str(td.get("table_text")), language=None)
            st.code((ocr.get("top_text", "") + "\n---\n" + ocr.get("full_text", "")).strip())


def _set_saved_signal_flash(key_prefix: str, message: str) -> None:
    if str(key_prefix).startswith("dashboard_detail_"):
        st.session_state["dashboard_flash_message"] = message
        st.session_state["dashboard_table_version"] = int(st.session_state.get("dashboard_table_version", 0)) + 1
    else:
        st.session_state["edit_flash_message"] = message


def reread_signal_from_storage(signal_id: int) -> str:
    row = load_signal(int(signal_id))
    if not row:
        raise RuntimeError("Segnale non trovato.")

    storage_path = _optional_path(row.get("screenshot_path"))
    if not storage_path:
        raise RuntimeError("Questo segnale non ha uno screenshot originale salvato.")
    raw = download_screenshot(storage_path)
    if not raw:
        raise RuntimeError("Impossibile scaricare lo screenshot originale dallo Storage.")

    img = Image.open(io.BytesIO(raw)).convert("RGB")
    ocr = extract_signal_payload_from_image(img)

    updates: Dict[str, Any] = {
        "ocr_text": (ocr.get("top_text", "") + "\n" + ocr.get("full_text", "")).strip(),
    }

    # Aggiorna i campi del setup con priorità ai nuovi valori OCR, mantenendo i valori
    # esistenti solo quando l'OCR non riesce davvero a leggerli.
    if ocr.get("valid_date"):
        updates["valid_date"] = ocr["valid_date"]
    if str(ocr.get("instrument") or "").strip():
        updates["instrument"] = canonical_instrument_label(ocr.get("instrument"))
    if str(ocr.get("ticker") or "").strip():
        updates["ticker"] = str(ocr.get("ticker") or "").strip()
    if str(ocr.get("direction") or "").strip() in {"LONG", "SHORT"}:
        updates["direction"] = str(ocr.get("direction")).strip()

    for field in ("e1", "s1", "e2", "s2", "t1", "t2", "t3"):
        value = ocr.get(field)
        if value is not None:
            updates[field] = value

    if ocr.get("setup_origin") not in (None, "", "—"):
        updates["setup_origin"] = ocr["setup_origin"]
    if ocr.get("setup_timeframe") not in (None, "", "—"):
        updates["setup_timeframe"] = ocr["setup_timeframe"]
    confirmations = list(ocr.get("confirmations") or [])
    if confirmations:
        updates["confirmations"] = confirmations

    existing_entry = _numeric_or_none(row.get("actual_entry"))
    existing_stop = _numeric_or_none(row.get("actual_stop"))
    has_real_trade = existing_entry is not None and existing_stop is not None
    new_t1 = updates.get("t1", row.get("t1"))
    new_t2 = updates.get("t2", row.get("t2"))
    new_t3 = updates.get("t3", row.get("t3"))
    new_direction = str(updates.get("direction", row.get("direction") or ""))
    new_ticker = str(updates.get("ticker", row.get("ticker") or "")).strip()

    monitoring_changed = False
    if has_real_trade:
        monitoring_changed = (
            _num_changed(row.get("t1"), new_t1)
            or _num_changed(row.get("t2"), new_t2)
            or _num_changed(row.get("t3"), new_t3)
            or str(row.get("direction") or "") != new_direction
            or effective_yahoo_ticker(row).strip() != new_ticker.strip()
        )

    if monitoring_changed:
        updates.update({
            "status": "IN TRADE",
            "outcome": None,
            "t1_hit_time": None,
            "t2_hit_time": None,
            "stop_hit_time": None,
            "result_note": "Screenshot riletto; monitoraggio da ricalcolare",
            "last_check": None,
        })
        if new_t3 is not None or _numeric_or_none(row.get("t3")) is not None:
            updates["t3_hit_time"] = None

    update_signal(int(signal_id), **updates)
    return (
        "Screenshot riletto e dati aggiornati. Il monitoraggio verrà ricalcolato con i nuovi livelli."
        if monitoring_changed else
        "Screenshot riletto e dati aggiornati."
    )


def delete_signal_with_assets(signal_id: int) -> None:
    row = load_signal(int(signal_id))
    if not row:
        raise RuntimeError("Segnale non trovato.")

    for field in ("screenshot_path", "final_screenshot_path"):
        path = _optional_path(row.get(field))
        if path:
            try:
                remove_screenshot(path)
            except Exception:
                pass

    delete_signal(int(signal_id))


def render_saved_signal_actions(row: Dict[str, Any], key_prefix: str) -> None:
    if not can_write():
        return

    sid = int(row["id"])
    cols = st.columns(2 if is_admin() else 1)

    with cols[0]:
        if st.button("🔁 Rileggi screenshot", key=f"{key_prefix}_reread_{sid}", use_container_width=True):
            try:
                msg = reread_signal_from_storage(sid)
                _set_saved_signal_flash(key_prefix, msg)
                st.rerun()
            except Exception as e:
                st.error(f"Rilettura screenshot non riuscita: {e}")

    if is_admin():
        with cols[1]:
            confirm_delete = st.checkbox("Confermo eliminazione", key=f"{key_prefix}_confirm_delete_{sid}")
            if st.button(
                "🗑️ Elimina segnale",
                key=f"{key_prefix}_delete_{sid}",
                use_container_width=True,
                disabled=not confirm_delete,
            ):
                try:
                    delete_signal_with_assets(sid)
                    _set_saved_signal_flash(key_prefix, f"Segnale #{sid} eliminato.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Eliminazione non riuscita: {e}")


def _optional_path(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    s = str(value).strip()
    return "" if s.lower() in {"", "none", "nan", "nat"} else s


def dashboard_signal_detail(row: Dict[str, Any], quotes: Dict[str, float]) -> None:
    """Apre sotto la tabella il dettaglio completo quando si clicca la cella ID."""
    sid = int(row["id"])
    instrument = canonical_instrument_label(row.get("instrument"))
    direction = str(row.get("direction") or "")
    valid_date = str(row.get("valid_date") or "")

    st.divider()
    st.markdown(f"## #{sid} · {instrument} · {direction}")
    if valid_date:
        st.caption(f"Data segnale: {valid_date}")

    original_path = _optional_path(row.get("screenshot_path"))
    final_path = _optional_path(row.get("final_screenshot_path"))
    original_raw = download_screenshot(original_path) if original_path else None
    final_raw = download_screenshot(final_path) if final_path else None

    if original_raw and final_raw:
        img1, img2 = st.columns(2)
        with img1:
            st.markdown("#### Screenshot originale")
            st.image(original_raw, use_container_width=True)
        with img2:
            st.markdown("#### Screenshot finale")
            st.image(final_raw, use_container_width=True)
    elif original_raw:
        st.markdown("#### Screenshot originale")
        st.image(original_raw, use_container_width=True)
    elif original_path:
        st.warning("Lo screenshot originale risulta salvato, ma non è disponibile nello Storage.")

    if trade_is_concluded(row) and (can_write() or final_path):
        final_screenshot_button(row, key=f"dashboard_detail_final_{sid}", use_container_width=False)

    ticker = effective_yahoo_ticker(row)
    price = quotes.get(ticker) if ticker else None
    state = open_trade_status_label(row)
    if state == "PUBBLICATO":
        state = operational_status_label(state)
    outcome = row.get("outcome")
    try:
        if pd.isna(outcome):
            outcome = None
    except Exception:
        pass

    m1, m2, m3 = st.columns(3)
    m1.metric("Prezzo attuale", f"{float(price):.1f}" if price is not None else "—")
    m2.metric("Stato", state or "—")
    m3.metric("Esito", str(outcome) if outcome else "—")

    tv_url = tradingview_chart_url(row)
    if tv_url:
        st.link_button("📊 Apri TradingView", tv_url, use_container_width=False)

    if can_write():
        render_saved_signal_actions(row, key_prefix=f"dashboard_detail_{sid}")
        _edit_signal_body(row, key_prefix=f"dashboard_detail_{sid}")
    else:
        st.caption("Profilo in sola lettura: i dati del segnale non sono modificabili.")


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
        key=f"dashboard_signals_table_{int(st.session_state.get('dashboard_table_version', 0))}",
        on_select="rerun",
        selection_mode="single-cell",
        column_config={
            "ID": st.column_config.NumberColumn(
                "ID",
                help="Clicca sull'ID per aprire il dettaglio completo sotto la tabella",
                width="small",
            ),
            "TradingView": st.column_config.LinkColumn(
                "TV",
                help="Apri direttamente il grafico dello strumento su TradingView",
                display_text="📊 Apri",
                width="small",
            ),
        },
    )

    selected_cells = []
    try:
        selected_cells = list(table_event.selection.cells)
    except Exception:
        try:
            selected_cells = list(table_event.get("selection", {}).get("cells", []))
        except Exception:
            selected_cells = []

    if selected_cells:
        try:
            pos, column_name = selected_cells[0]
            pos = int(pos)
        except Exception:
            pos, column_name = -1, ""
        if column_name == "ID" and 0 <= pos < len(df):
            selected_raw = df.iloc[pos].to_dict()
            dashboard_signal_detail(selected_raw, quotes)

    st.download_button(
        "⬇️ Esporta storico Excel", data=excel_bytes(df),
        file_name=f"signal_tracker_{local_now().date().isoformat()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="dashboard_excel_download",
    )


def page_dashboard() -> None:
    st.subheader("Dashboard")
    flash_message = st.session_state.pop("dashboard_flash_message", None)
    if flash_message:
        st.success(flash_message)
    if can_write():
        auto_monitor = st.toggle(
            "Monitoraggio automatico trade aperti (ogni 60 secondi)",
            value=True,
            help="Attivo solo mentre questa Dashboard resta aperta. Controlla T1, T2, T3 e Stop usando i dati intraday disponibili da Yahoo Finance.",
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
    resolved_outcomes = ["T3", "T2", "T2 + STOP", "T1 + STOP", "STOP"]
    resolved = traded[traded["outcome"].isin(resolved_outcomes)].copy()
    if resolved.empty:
        st.info("Non ci sono ancora abbastanza trade risolti per statistiche operative affidabili.")
    else:
        resolved["win_t1"] = resolved["outcome"].isin(["T3", "T2", "T2 + STOP", "T1 + STOP"]).astype(int)
        resolved["t2_hit"] = resolved["outcome"].isin(["T3", "T2", "T2 + STOP"]).astype(int)
        resolved["t3_hit"] = (resolved["outcome"] == "T3").astype(int)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Trade risolti", len(resolved))
        c2.metric("T1 prima dello Stop", f"{resolved['win_t1'].mean()*100:.1f}%")
        c3.metric("T2 raggiunto", f"{resolved['t2_hit'].mean()*100:.1f}%")
        c4.metric("T3 raggiunto", f"{resolved['t3_hit'].mean()*100:.1f}%")

        st.markdown("#### Risultati per origine del setup")
        by_origin = resolved.groupby("setup_origin", dropna=False).agg(
            Trade=("id", "count"), WinRate_T1=("win_t1", "mean"), T2=("t2_hit", "mean"), T3=("t3_hit", "mean")
        ).reset_index()
        by_origin["WinRate_T1"] = (by_origin["WinRate_T1"] * 100).round(1)
        by_origin["T2"] = (by_origin["T2"] * 100).round(1)
        by_origin["T3"] = (by_origin["T3"] * 100).round(1)
        st.dataframe(by_origin, use_container_width=True, hide_index=True)

        st.markdown("#### Risultati per strumento")
        by_instr = resolved.groupby("instrument").agg(
            Trade=("id", "count"), WinRate_T1=("win_t1", "mean"), T2=("t2_hit", "mean"), T3=("t3_hit", "mean")
        ).reset_index().sort_values(["Trade", "WinRate_T1"], ascending=[False, False])
        by_instr["WinRate_T1"] = (by_instr["WinRate_T1"] * 100).round(1)
        by_instr["T2"] = (by_instr["T2"] * 100).round(1)
        by_instr["T3"] = (by_instr["T3"] * 100).round(1)
        st.dataframe(by_instr, use_container_width=True, hide_index=True)

        st.markdown("#### Conferme osservate")
        ex = explode_confirmations(resolved)
        if ex.empty:
            st.caption("Nessuna conferma facoltativa registrata nei trade risolti.")
        else:
            ex["win_t1"] = ex["outcome"].isin(["T3", "T2", "T2 + STOP", "T1 + STOP"]).astype(int)
            ex["t2_hit"] = ex["outcome"].isin(["T3", "T2", "T2 + STOP"]).astype(int)
            ex["t3_hit"] = (ex["outcome"] == "T3").astype(int)
            by_conf = ex.groupby("confirmation").agg(
                Presenze=("confirmation", "size"), WinRate_T1=("win_t1", "mean"), T2=("t2_hit", "mean"), T3=("t3_hit", "mean")
            ).reset_index().sort_values("Presenze", ascending=False)
            by_conf["WinRate_T1"] = (by_conf["WinRate_T1"] * 100).round(1)
            by_conf["T2"] = (by_conf["T2"] * 100).round(1)
            by_conf["T3"] = (by_conf["T3"] * 100).round(1)
            st.dataframe(by_conf, use_container_width=True, hide_index=True)

    st.markdown("#### Nota metodologica")
    st.caption(
        "Il Win Rate base considera vincente un trade in cui T1 viene raggiunto prima dello Stop. "
        "E1/E2 e S1/S2 restano livelli indicativi del segnale originale e non vengono usati come esecuzioni reali. "
        "I casi in cui stop e target ricadono nella stessa barra vengono marcati AMBIGUI invece di forzare un risultato."
    )


def page_archive() -> None:
    st.subheader("Archivio segnali")
    flash_message = st.session_state.pop("edit_flash_message", None)
    if flash_message:
        st.success(flash_message)
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
            render_saved_signal_actions(row, key_prefix=f"archive_detail_{sid}")
            edit_signal_panel(row, key_prefix="archive")





# -----------------------------------------------------------------------------
# Avvio app
# -----------------------------------------------------------------------------
st.set_page_config(page_title=f"{APP_NAME} {APP_VERSION}", page_icon="📊", layout="wide")

if not config_ready():
    st.title(f"📊 {APP_NAME} {APP_VERSION}")
    st.error("Configurazione incompleta nei Secrets di Streamlit.")
    st.code(
        '[supabase]\nurl = "https://TUO-PROGETTO.supabase.co"\nservice_role_key = "sb_secret_..."\n\n'
        '[access]\nadmin_password = "PASSWORD_AMMINISTRATORE"\ncollaborator_password = "PASSWORD_COLLABORATORE"',
        language="toml",
    )
    st.caption(
        "Le due password devono essere diverse. Non pubblicare mai service_role_key o le password nel repository GitHub: "
        "devono restare esclusivamente nei Secrets di Streamlit."
    )
    st.stop()

if not st.session_state.get("app_unlocked"):
    show_login()
    st.stop()

st.title(f"📊 {APP_NAME} {APP_VERSION}")
st.caption("Screenshot → segnale strutturato → trade reale → monitoraggio → statistiche")

role = current_role()
role_label = ROLE_LABELS.get(role, role)

with st.sidebar:
    st.markdown(f"### {APP_NAME}")
    st.caption(f"🔐 **{role_label}**")

    pages = ["Dashboard", "Carica nuovo segnale", "Statistiche", "Archivio"]
    page = st.radio("Sezione", pages)
    st.divider()
    if st.button("🚪 Esci", use_container_width=True):
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
except Exception as e:
    st.error(f"Errore applicazione: {e}")
    st.caption("Se l'errore riguarda autorizzazioni o tabelle mancanti, verifica la configurazione Supabase del progetto.")
