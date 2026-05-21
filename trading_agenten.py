"""
=============================================================
  TRADING AGENTEN SYSTEM
  Aktien: Palantir, Microsoft, Visa, McDonald's, Costco
  Sendet 3x täglich eine E-Mail mit Trading-Signalen
=============================================================

SETUP (einmalig, 5 Minuten):
1. Diese 3 Zeilen ausfüllen:
   - ANTHROPIC_KEY: von console.anthropic.com
   - ALPHAVANTAGE_KEY: neu erstellen auf alphavantage.co
   - TAVILY_KEY: neu erstellen auf tavily.com

2. Auf Railway.app:
   - Neues Projekt anlegen
   - Diese Datei hochladen
   - Die 3 Keys unter "Variables" eintragen
   - Cron Job einstellen: "0 8,13,18 * * 1-5"
     (läuft Mo-Fr um 08:00, 13:00, 18:00 Uhr)

3. E-Mail einrichten:
   - Gmail: Einstellungen → Sicherheit → App-Passwörter
   - Dort ein App-Passwort für "Mail" erstellen
   - Dieses Passwort in GMAIL_APP_PASSWORT eintragen
=============================================================
"""

import os
import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import urllib.request

# ============================================================
#  HIER DEINE DATEN EINTRAGEN
# ============================================================

ANTHROPIC_KEY      = "HIER_EINTRAGEN"
ALPHAVANTAGE_KEY   = "HIER_EINTRAGEN"
TAVILY_KEY         = "HIER_EINTRAGEN"

GMAIL_ADRESSE      = "HIER_EINTRAGEN"
GMAIL_APP_PASSWORT = "HIER_EINTRAGEN"   # App-Passwort, nicht dein normales!
EMPFAENGER_EMAIL   = "HIER_EINTRAGEN"       # Wohin die E-Mail geht

# ============================================================
#  DEINE 5 AKTIEN
# ============================================================

AKTIEN = {
    "PLTR":  "Palantir Technologies",
    "MSFT":  "Microsoft",
    "V":     "Visa",
    "MCD":   "McDonald's",
    "COST":  "Costco",
}

# ============================================================
#  HILFSFUNKTIONEN — nichts ändern nötig
# ============================================================

def api_anfrage(url, headers=None):
    """Einfache HTTP-Anfrage ohne externe Bibliotheken."""
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"fehler": str(e)}


def hole_kursdaten(ticker):
    """Holt Kursdaten + Fundamentaldaten von Alpha Vantage."""
    basis = "https://www.alphavantage.co/query"

    # Aktueller Kurs
    kurs_url = f"{basis}?function=GLOBAL_QUOTE&symbol={ticker}&apikey={ALPHAVANTAGE_KEY}"
    kurs = api_anfrage(kurs_url)

    # Übersicht (KGV, Marktkapitalisierung etc.)
    info_url = f"{basis}?function=OVERVIEW&symbol={ticker}&apikey={ALPHAVANTAGE_KEY}"
    info = api_anfrage(info_url)

    # Wochenchart für Trendanalyse
    chart_url = f"{basis}?function=TIME_SERIES_WEEKLY&symbol={ticker}&apikey={ALPHAVANTAGE_KEY}"
    chart = api_anfrage(chart_url)

    return {
        "kurs": kurs.get("Global Quote", {}),
        "info": info,
        "chart_vorhanden": "Weekly Time Series" in chart,
    }


def hole_nachrichten(aktienname):
    """Sucht aktuelle News und Social-Media-Stimmung via Tavily."""
    url = "https://api.tavily.com/search"
    daten = json.dumps({
        "api_key": TAVILY_KEY,
        "query": f"{aktienname} stock news analyst opinion 2025",
        "search_depth": "basic",
        "max_results": 5,
        "include_answer": True,
    }).encode()
    req = urllib.request.Request(url, data=daten,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            ergebnis = json.loads(r.read().decode())
            quellen = [f"- {q.get('title','')}: {q.get('content','')[:200]}"
                       for q in ergebnis.get("results", [])[:3]]
            return "\n".join(quellen) if quellen else "Keine aktuellen News gefunden."
    except Exception as e:
        return f"News-Abruf fehlgeschlagen: {e}"


def claude_anfrage(system_prompt, user_prompt):
    """Sendet eine Anfrage an die Claude API."""
    url = "https://api.anthropic.com/v1/messages"
    daten = json.dumps({
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 600,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }).encode()
    headers = {
        "x-api-key": ANTHROPIC_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    req = urllib.request.Request(url, data=daten, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            antwort = json.loads(r.read().decode())
            return antwort["content"][0]["text"]
    except Exception as e:
        return f"Claude-Fehler: {e}"


# ============================================================
#  DIE 5 AGENTEN
# ============================================================

def agent_fundamental(ticker, name, daten):
    system = (
        "Du bist ein erfahrener Fundamentalanalyst. "
        "Antworte immer auf Deutsch. Sei präzise und kurz."
    )
    info = daten.get("info", {})
    prompt = f"""
Analysiere {name} ({ticker}) anhand dieser Kennzahlen:
- KGV (P/E Ratio): {info.get('PERatio', 'n/a')}
- KUV (Price/Sales): {info.get('PriceToSalesRatioTTM', 'n/a')}
- Gewinnmarge: {info.get('ProfitMargin', 'n/a')}
- Umsatzwachstum (YoY): {info.get('RevenueGrowthYOY', 'n/a')}
- Eigenkapitalrendite: {info.get('ReturnOnEquityTTM', 'n/a')}
- 52-Wochen-Hoch: {info.get('52WeekHigh', 'n/a')}
- 52-Wochen-Tief: {info.get('52WeekLow', 'n/a')}
- Dividendenrendite: {info.get('DividendYield', 'n/a')}
- Analysten-Kursziel: {info.get('AnalystTargetPrice', 'n/a')}

Gib aus:
SIGNAL: [KAUFEN / HALTEN / VERKAUFEN]
KONFIDENZ: [0-100]%
BEGRÜNDUNG: (2 Sätze)
"""
    return claude_anfrage(system, prompt)


def agent_charttechnik(ticker, name, daten):
    system = (
        "Du bist ein technischer Analyst (Charttechnik). "
        "Antworte immer auf Deutsch. Sei präzise und kurz."
    )
    kurs = daten.get("kurs", {})
    prompt = f"""
Analysiere {name} ({ticker}) technisch:
- Aktueller Kurs: {kurs.get('05. price', 'n/a')}
- Veränderung heute: {kurs.get('10. change percent', 'n/a')}
- Handelsvolumen: {kurs.get('06. volume', 'n/a')}
- Tages-Hoch: {kurs.get('03. high', 'n/a')}
- Tages-Tief: {kurs.get('04. low', 'n/a')}
- Vorschlusskurs: {kurs.get('08. previous close', 'n/a')}

Analysiere: Trend, Momentum, mögliche Unterstützung/Widerstand.

Gib aus:
SIGNAL: [KAUFEN / HALTEN / VERKAUFEN]
KONFIDENZ: [0-100]%
BEGRÜNDUNG: (2 Sätze)
"""
    return claude_anfrage(system, prompt)


def agent_zyklen(ticker, name):
    system = (
        "Du bist ein Zyklenanalyst (Makroökonomie + Saisonalität). "
        "Antworte immer auf Deutsch. Sei präzise und kurz."
    )
    monat = datetime.now().month
    prompt = f"""
Analysiere {name} ({ticker}) aus Zyklen-Perspektive:
- Aktueller Monat: {monat}
- Beachte: Saisonale Muster für diese Aktie
- Beachte: Aktuelles Makroumfeld (Zinsen, Inflation, Konjunkturphase 2025)
- Beachte: Historische Monats-Performance im Monat {monat}

Gib aus:
SIGNAL: [KAUFEN / HALTEN / VERKAUFEN]
KONFIDENZ: [0-100]%
BEGRÜNDUNG: (2 Sätze)
"""
    return claude_anfrage(system, prompt)


def agent_marktdynamik(ticker, name, daten):
    system = (
        "Du bist ein Marktdynamik-Analyst. "
        "Antworte immer auf Deutsch. Sei präzise und kurz."
    )
    info = daten.get("info", {})
    prompt = f"""
Analysiere {name} ({ticker}) auf Marktdynamik:
- Beta (Volatilität vs. Markt): {info.get('Beta', 'n/a')}
- Institutionelle Beteiligung: {info.get('PercentInstitutions', 'n/a')}
- Short-Quote: {info.get('ShortPercentOutstandingShares', 'n/a')}
- Sektor: {info.get('Sector', 'n/a')}
- Industrie: {info.get('Industry', 'n/a')}
- Marktkapitalisierung: {info.get('MarketCapitalization', 'n/a')}

Analysiere: Sektor-Stärke, institutionelles Interesse, Short-Squeeze-Potenzial.

Gib aus:
SIGNAL: [KAUFEN / HALTEN / VERKAUFEN]
KONFIDENZ: [0-100]%
BEGRÜNDUNG: (2 Sätze)
"""
    return claude_anfrage(system, prompt)


def agent_sentiment(ticker, name, nachrichten):
    system = (
        "Du bist ein Sentiment-Analyst für Finanzmärkte. "
        "Antworte immer auf Deutsch. Sei präzise und kurz."
    )
    prompt = f"""
Analysiere das aktuelle Sentiment für {name} ({ticker}).

Aktuelle News und Berichte:
{nachrichten}

Bewerte: Stimmung der Medien, Analysten-Meinungen, mögliche Kursauslöser.

Gib aus:
SIGNAL: [KAUFEN / HALTEN / VERKAUFEN]
KONFIDENZ: [0-100]%
BEGRÜNDUNG: (2 Sätze)
"""
    return claude_anfrage(system, prompt)


# ============================================================
#  ORCHESTRATOR
# ============================================================

def orchestrator(ticker, name, ergebnisse):
    system = (
        "Du bist ein erfahrener Portfolio-Manager. "
        "Antworte immer auf Deutsch. Sei präzise."
    )
    prompt = f"""
Du hast 5 Analystenberichte für {name} ({ticker}) erhalten:

FUNDAMENTAL-ANALYSE:
{ergebnisse['fundamental']}

CHARTTECHNIK:
{ergebnisse['charttechnik']}

ZYKLEN-ANALYSE:
{ergebnisse['zyklen']}

MARKTDYNAMIK:
{ergebnisse['marktdynamik']}

SENTIMENT-ANALYSE:
{ergebnisse['sentiment']}

Erstelle eine ZUSAMMENFASSUNG im folgenden Format:

FINALES SIGNAL: [KAUFEN / HALTEN / VERKAUFEN]
GESAMT-KONFIDENZ: [0-100]%

EINSTIEG: [konkreter Hinweis wann einsteigen]
AUSSTIEG: [konkreter Hinweis wann aussteigen / Stop-Loss]

KURZFASSUNG (3 Sätze): Die wichtigsten Argumente für deine Entscheidung.
"""
    return claude_anfrage(system, prompt)


# ============================================================
#  ANALYSE EINER AKTIE
# ============================================================

def analysiere_aktie(ticker, name):
    print(f"  Analysiere {name} ({ticker})...")

    kursdaten  = hole_kursdaten(ticker)
    nachrichten = hole_nachrichten(name)

    ergebnisse = {
        "fundamental":  agent_fundamental(ticker, name, kursdaten),
        "charttechnik": agent_charttechnik(ticker, name, kursdaten),
        "zyklen":       agent_zyklen(ticker, name),
        "marktdynamik": agent_marktdynamik(ticker, name, kursdaten),
        "sentiment":    agent_sentiment(ticker, name, nachrichten),
    }

    finales_signal = orchestrator(ticker, name, ergebnisse)

    return {
        "ticker": ticker,
        "name": name,
        "kurs": kursdaten.get("kurs", {}).get("05. price", "n/a"),
        "veraenderung": kursdaten.get("kurs", {}).get("10. change percent", "n/a"),
        "signal": finales_signal,
        "details": ergebnisse,
    }


# ============================================================
#  E-MAIL ERSTELLEN UND SENDEN
# ============================================================

def erstelle_email_inhalt(alle_analysen):
    uhrzeit = datetime.now().strftime("%d.%m.%Y %H:%M")

    # Betreff: Wichtigstes Signal hervorheben
    signale_kurz = []
    for a in alle_analysen:
        signal_text = a["signal"]
        if "KAUFEN" in signal_text:
            signale_kurz.append(f"{a['ticker']} KAUFEN")
        elif "VERKAUFEN" in signal_text:
            signale_kurz.append(f"{a['ticker']} VERKAUFEN")

    betreff = f"Trading-Signale {uhrzeit}"
    if signale_kurz:
        betreff += " — " + " | ".join(signale_kurz[:2])

    # E-Mail-Text
    text = f"""
TRADING SIGNAL REPORT
{uhrzeit}
{"=" * 50}

"""
    for a in alle_analysen:
        text += f"""
{a['name']} ({a['ticker']})
Kurs: {a['kurs']} USD  |  Heute: {a['veraenderung']}
{"-" * 40}
{a['signal']}

"""

    text += """
{"=" * 50}
WICHTIGER HINWEIS:
Dies sind KI-generierte Analysen — kein Finanzberatung.
Triff eigene Entscheidungen und setze immer Stop-Loss Orders.
{"=" * 50}
"""
    return betreff, text


def sende_email(betreff, inhalt):
    msg = MIMEMultipart()
    msg["From"]    = GMAIL_ADRESSE
    msg["To"]      = EMPFAENGER_EMAIL
    msg["Subject"] = betreff
    msg.attach(MIMEText(inhalt, "plain", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADRESSE, GMAIL_APP_PASSWORT)
            server.send_message(msg)
        print("E-Mail erfolgreich gesendet!")
        return True
    except Exception as e:
        print(f"E-Mail-Fehler: {e}")
        return False


# ============================================================
#  HAUPTPROGRAMM
# ============================================================

def main():
    print(f"\nTrading-Agenten gestartet — {datetime.now().strftime('%d.%m.%Y %H:%M')}")
    print("=" * 50)

    alle_analysen = []

    for ticker, name in AKTIEN.items():
        try:
            analyse = analysiere_aktie(ticker, name)
            alle_analysen.append(analyse)
        except Exception as e:
            print(f"  Fehler bei {name}: {e}")

    print("\nErstelle E-Mail...")
    betreff, inhalt = erstelle_email_inhalt(alle_analysen)
    sende_email(betreff, inhalt)

    print("Fertig!\n")


if __name__ == "__main__":
    main()
