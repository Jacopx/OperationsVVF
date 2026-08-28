# * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *
# *                         OperationsVVF by Jacopx                         *
# *                 https://github.com/Jacopx/OperationsVVF                 *
# * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * *

import os
import sys
import locale
import datetime as dt
import configparser
import xml.etree.ElementTree as ET
from typing import Optional
import re

import mysql.connector as mariadb

from operation import Operation
from starts import Start


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------


def _text(element: ET.Element, tag: str) -> Optional[str]:
    """Return stripped text of a child tag, or None if missing / empty."""
    node = element.find(tag)
    if node is None or not (node.text or "").strip():
        return None
    return node.text.strip()


# ---------------------------------------------------------------------------
# Typology normalisation
# ---------------------------------------------------------------------------

TYPOLOGY_RULES: list[tuple[str, str]] = [
    ("elettrici", "Incendio Cavi Elettrici"),
    ("incendio", "Incendio"),
    ("incendi", "Incendio"),
    ("sopralluogo", "Sopralluogo Tecnico"),
    ("verifica stabilit", "Sopralluogo Tecnico"),
    ("cedimento", "Sopralluogo Tecnico"),
    ("bonifica", "Bonifica"),
    ("nido", "Bonifica"),
    ("insetti", "Bonifica"),
    ("alberi", "Alberi Pericolanti"),
    ("albero", "Alberi Pericolanti"),
    ("animali", "Recupero Animali"),
    ("rettile", "Recupero Animali"),
    ("rettili", "Recupero Animali"),
    ("ostacoli", "Rimozione Ostacoli"),
    ("ingombro sede stradale", "Ingombro Sede Stradale"),
    ("lavaggio", "Lavaggio Strada"),
    ("gasolio", "Lavaggio Strada"),
    ("versamento", "Lavaggio Strada"),
    ("stradale", "Incidente Stradale"),
    ("assistenza", "Servizio Assistenza"),
    ("frane", "Dissesto Statico"),
    ("dissesto", "Dissesto Statico"),
    ("straripamenti", "Dissesto Statico"),
    ("voragine", "Dissesto Statico"),
    ("valanghe", "Dissesto Statico"),
    ("persona", "Soccorso Persone"),
    ("persone", "Soccorso Persone"),
    ("alienati", "Soccorso Persone"),
    ("ammalati", "Trasporto Persona"),
    ("finestre", "Apertura Alloggio"),
    ("alloggio", "Apertura Alloggio"),
    ("tegole", "Rimozione Pericolanti"),
    ("grondaie", "Rimozione Pericolanti"),
    ("grondaia", "Rimozione Pericolanti"),
    ("camini", "Rimozione Pericolanti"),
    ("cornicione", "Rimozione Pericolanti"),
    ("cornicioni", "Rimozione Pericolanti"),
    ("tetti", "Rimozione Pericolanti"),
    ("palo pericolante", "Rimozione Pericolanti"),
    ("ghiaccio pericolante", "Rimozione Pericolanti"),
    ("ascensori", "Ascensori Bloccati"),
    ("acqua", "Danni Acqua"),
    ("gas", "Fuga Gas"),
    ("fumo", "Fuoriuscita Fumo"),
    ("salme", "Recupero Salme"),
    ("intervento non + necessario", "Annullato"),
    ("necessario", "Annullato"),
    ("beni", "Recupero Oggetti"),
    ("merci", "Recupero Oggetti"),
    ("presidio", "Presidio Centrale"),
    ("cavi", "Danni Cavi Elettrici"),
    ("igienizzazione", "Igienizzazione"),
]


def typology_parse(raw: str) -> str:
    lower = raw.lower()
    for keyword, label in TYPOLOGY_RULES:
        if keyword in lower:
            return label
    return "Altro"


# ---------------------------------------------------------------------------
# Date / time helpers
# ---------------------------------------------------------------------------


def _parse_date(date_str: str) -> dt.date:
    return dt.datetime.strptime(date_str, "%d-%b-%y").date()


def _parse_time(time_str: str) -> dt.time:
    normalized = time_str.replace(".", ":").replace("/", ":")
    return dt.datetime.strptime(normalized, "%H:%M").time()


def _combine(base_date: dt.date, time_str: str, ref_seconds: int) -> dt.datetime:
    """Combine base_date with time_str, rolling to next day if time < ref."""
    t = _parse_time(time_str)
    t_sec = t.hour * 3600 + t.minute * 60
    actual_date = base_date + dt.timedelta(days=1) if t_sec < ref_seconds else base_date
    return dt.datetime.combine(actual_date, t)


# ---------------------------------------------------------------------------
# First pass: collect all distinct years present in the XML
# ---------------------------------------------------------------------------


def _collect_years(root: ET.Element, list_tag: str, op_tag: str) -> set[str]:
    """Scan all records and return the set of years found in DATA_INTERVENTO."""
    years: set[str] = set()
    for g in root.findall(f"{list_tag}/{op_tag}"):
        raw_date = _text(g, "DATA_INTERVENTO")
        if raw_date:
            try:
                years.add(str(_parse_date(raw_date).year))
            except ValueError:
                pass
    return years


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(xml_path: str) -> None:
    config = configparser.ConfigParser()
    config.read("config.ini")

    db = config["DEFAULT"]["DB"]
    usr = config["DEFAULT"]["USER"]
    pwd = config["DEFAULT"]["PWD"]
    host = config["DEFAULT"]["HOST"]
    port = config["DEFAULT"]["PORT"]

    # Italian locale for date parsing (GEN, FEB, ...)
    locale.setlocale(locale.LC_TIME, ("it", "UTF-8"))

    with open(xml_path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()

    # Strip control characters that make Oracle XML invalid
    raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", raw)

    root = ET.fromstring(raw)

    list_tag = "LIST_G_RICHIEDENTE"
    op_tag = "G_RICHIEDENTE"
    start_tag = "G_FLAG_ANNULLA"

    # --- First pass: discover all years in the file ----------------------------
    years_in_file = _collect_years(root, list_tag, op_tag)
    if not years_in_file:
        print("No valid dates found in file. Aborting.", file=sys.stderr)
        sys.exit(1)
    print(f"Years found in file: {sorted(years_in_file)}")

    conn = mariadb.connect(
        user=usr, password=pwd, host=host, port=int(port), database=db
    )
    cursor = conn.cursor()

    # Delete existing rows for every year present in the file
    for y in years_in_file:
        cursor.execute(f"DELETE FROM operations WHERE ID>=0 AND year='{y}'")
        cursor.execute(f"DELETE FROM starts     WHERE ID>=0 AND year='{y}'")
    conn.commit()

    ops_batch: list[tuple] = []
    starts_batch: list[tuple] = []
    parse_errors: list[str] = []

    # idx is now scoped per (year, opn) to avoid PK collisions across years.
    # We keep a separate counter per year.
    year_counters: dict[str, int] = {}

    for g in root.findall(f"{list_tag}/{op_tag}"):

        # --- Operation fields ---------------------------------------------------
        raw_date = _text(g, "DATA_INTERVENTO")
        raw_exit = _text(g, "ORA_USCITA")
        raw_close = _text(g, "ORA_CHIUSURA")
        raw_typology = _text(g, "TIPOLOGIA") or ""
        raw_x = _text(g, "X")
        raw_y = _text(g, "Y")
        loc = _text(g, "COMUNE_SIGLA_PROVINCIA")
        address = _text(g, "INDIRIZZO")
        opn = _text(g, "INTERVENTO")
        nom = _text(g, "NOMINATIVO")
        boss = _text(g, "CF_PROVA")
        caller = _text(g, "RICHIEDENTE")
        operator = _text(g, "NOMINATIVO")

        op = Operation(
            date=raw_date,
            exit=raw_exit,
            close=raw_close,
            typology=typology_parse(raw_typology),
            raw_x=raw_x,
            raw_y=raw_y,
            loc=loc,
            add=address,
            opn=opn,
            nom=nom,
            boss=boss,
            address=address,
            caller=caller,
            operator=operator
        )

        # --- Datetime computation -----------------------------------------------
        try:
            base_date = _parse_date(op.date)
        except (ValueError, TypeError) as e:
            parse_errors.append(f"op={op.opn} — invalid date {op.date!r}: {e}")
            continue

        # Derive year from the parsed date (not from filename)
        year = str(base_date.year)

        # Per-year sequential index (used as PK)
        idx = year_counters.get(year, 0)
        year_counters[year] = idx + 1

        print(
            f"[{year}/{idx}] {op.opn} | {op.date} | {op.exit}-{op.close} | {op.typology} | ({op.x},{op.y}) | {op.loc} | {op.boss} | {op.address} | {op.caller} | {op.operator}"
        )

        ref_sec = 0  # fallback
        dt_exit = dt_close = None

        if op.exit:
            try:
                t = _parse_time(op.exit)
                ref_sec = t.hour * 3600 + t.minute * 60
                dt_exit = dt.datetime.combine(base_date, t)
            except (ValueError, TypeError) as e:
                parse_errors.append(f"[{year}/{idx}] op={op.opn} — invalid exit time {op.exit!r}: {e}")

        if op.close and op.exit:
            try:
                dt_close = _combine(base_date, op.close, ref_sec)
            except (ValueError, TypeError) as e:
                parse_errors.append(f"[{year}/{idx}] op={op.opn} — invalid close time {op.close!r}: {e}")

        ops_batch.append(
            (
                idx,
                year,
                op.opn,
                base_date,
                dt_exit,
                dt_close,
                op.typology,
                op.x,
                op.y,
                op.loc,
                op.boss,
                op.address,
                op.caller,
                op.operator,
            )
        )

        # --- Starts -------------------------------------------------------------
        for j, g_flag in enumerate(g.findall(f".//{start_tag}")):
            vehicle = _text(g_flag, "SIGLA_MEZZO")
            s_date_raw = _text(g_flag, "DATA_SERVIZIO")
            s_exit = _text(g_flag, "ORA_USCITA1")
            s_inplace = _text(g_flag, "ORA_ARRIVO")
            s_back = _text(g_flag, "ORA_PARTENZA_LUOGO")
            s_nom = _text(g_flag, "CF_2")

            start = Start(
                id=j,
                op_id=idx,
                vehicle=vehicle,
                exit=s_exit,
                inplace=s_inplace,
                back=s_back,
                nom=s_nom,
            )

            dt_s_exit = dt_s_inplace = dt_s_back = None

            try:
                s_date = _parse_date(s_date_raw)
            except (ValueError, TypeError) as e:
                parse_errors.append(f"op={op.opn} — invalid start date {s_date_raw!r}: {e}")
                continue

            if start.exit:
                try:
                    dt_s_exit = _combine(s_date, start.exit, ref_sec)
                except (ValueError, TypeError) as e:
                    parse_errors.append(f"  [{year}/{idx}/{j}] vehicle={start.vehicle} — invalid exit time {start.exit!r}: {e}")
            if start.inplace:
                try:
                    dt_s_inplace = _combine(s_date, start.inplace, ref_sec)
                except (ValueError, TypeError) as e:
                    parse_errors.append(f"  [{year}/{idx}/{j}] vehicle={start.vehicle} — invalid inplace time {start.inplace!r}: {e}")
            if start.back:
                try:
                    dt_s_back = _combine(s_date, start.back, ref_sec)
                except (ValueError, TypeError) as e:
                    parse_errors.append(f"  [{year}/{idx}/{j}] vehicle={start.vehicle} — invalid back time {start.back!r}: {e}")

            print(
                f"  [{j}] {start.vehicle} | {dt_s_exit} | {dt_s_inplace} | {dt_s_back} | {start.nom}"
            )

            starts_batch.append(
                (
                    idx,
                    j,
                    year,
                    start.vehicle,
                    dt_s_exit,
                    dt_s_inplace,
                    dt_s_back,
                    start.nom,
                )
            )
        print()

    # --- Batch DB write ---------------------------------------------------------
    error_count = 0
    try:
        cursor.executemany(
            "INSERT INTO operations (ID, year, opn, date, dt_exit, dt_close, typology, x, y, loc, boss, address, caller, operator) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            ops_batch,
        )
        cursor.executemany(
            "INSERT INTO starts (OpID, ID, year, vehicle, exit_dt, inplace_dt, back_dt, boss) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            starts_batch,
        )
        conn.commit()
    except mariadb.Error as err:
        error_count += 1
        conn.rollback()
        print(f"[ERROR] Batch insert failed: {err}", file=sys.stderr)
    finally:
        conn.close()

    print(
        f"\nDone. Operations: {len(ops_batch)} | Starts: {len(starts_batch)} | Errors: {error_count}"
    )
    print(f"Years processed: { {y: year_counters[y] for y in sorted(year_counters)} }")

    if parse_errors:
        print(f"\n--- {len(parse_errors)} parse warning(s) (records skipped or fields set to NULL) ---", file=sys.stderr)
        for msg in parse_errors:
            print(f"  {msg}", file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python main.py <xml_path>")
        sys.exit(1)

    main(xml_path=sys.argv[1])