# G. Signal Tracker V1.0

App Streamlit per trasformare screenshot dei segnali Telegram/TradingView in uno storico strutturato e verificabile.

## Logica adottata

- E1/E2 e S1/S2 sono **livelli indicativi del segnale originale**, non esecuzioni automatiche.
- Il trade reale viene registrato con **Entry effettiva + Stop effettivo + data/ora ingresso**.
- Se non si crea un ingresso valido: **NESSUN TRADE** o **SETUP ANNULLATO**.
- Contesto facoltativo: Balance / Punto di svolta / entrambi, area/livello, timeframe.
- Conferme facoltative: Medie mobili, M4, Stocastico/TDI, Bollinger, Supertrend, Price Action, Altro.
- L'app monitora T1/T2/Stop usando dati Yahoo Finance e marca **AMBIGUO** se target e stop sono presenti nella stessa barra e l'ordine non è ricostruibile.
- Il **Win Rate base** considera vincente un trade in cui T1 viene raggiunto prima dello Stop.

## Avvio locale

1. Apri il terminale nella cartella del progetto.
2. Installa i pacchetti:

```bash
python -m pip install -r requirements.txt
```

3. Installa **Tesseract OCR** su Windows. Normalmente viene rilevato automaticamente se installato in:
   `C:\Program Files\Tesseract-OCR\tesseract.exe`
4. Avvia:

```bash
python -m streamlit run app.py
```

## Streamlit Community Cloud

Carica nella repository almeno:

- `app.py`
- `requirements.txt`
- `packages.txt`

`packages.txt` installa Tesseract nel container Linux di Streamlit Cloud.

### Attenzione alla persistenza

La V1 salva dati e screenshot nel filesystem locale:

- `data/signals.db`
- `data/screenshots/`

In locale è una soluzione stabile. Su Streamlit Community Cloud il filesystem può essere ricreato durante restart/deploy, quindi per un uso condiviso definitivo è consigliato passare nella V2 a un database persistente (Supabase/PostgreSQL o equivalente).

## Screenshot di prova

Con lo screenshot GOLD del 03/09/2026 il parser è progettato per riconoscere:

- Strumento: GOLD FUTURES / `GC=F`
- Data: 03/09/2026
- LONG
- E1 4445.6 / S1 4408
- E2 4398.2 / S2 4348
- T1 4494.3
- T2 4584.0

Tutti i campi OCR restano comunque modificabili prima del salvataggio.
