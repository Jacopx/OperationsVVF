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
    return dt.datetime.strptime(time_str.replace(".", ":"), "%H:%M").time()


def _combine(base_date: dt.date, time_str: str, ref_seconds: int) -> dt.datetime:
    """Combine base_date with time_str, rolling to next day if time < ref."""
    t = _parse_time(time_str)
    t_sec = t.hour * 3600 + t.minute * 60
    actual_date = base_date + dt.timedelta(days=1) if t_sec < ref_seconds else base_date
    return dt.datetime.combine(actual_date, t)


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

    year = os.path.splitext(os.path.basename(xml_path))[0]

    # Italian locale for date parsing (GEN, FEB, ...)
    locale.setlocale(locale.LC_TIME, ("it", "UTF-8"))

    with open(xml_path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()

    # Strip control characters that make Oracle XML invalid
    raw = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", raw)

    root = ET.fromstring(raw)

    # Pre-2020 XML uses different container tag names
    if year < "2020":
        list_tag = "LIST_G_1"
        op_tag = "G_1"
        start_tag = "G_INTERVENTO1"
    else:
        list_tag = "LIST_G_RICHIEDENTE"
        op_tag = "G_RICHIEDENTE"
        start_tag = "G_FLAG_ANNULLA"

    cursor = None
    conn = None
    conn = mariadb.connect(
        user=usr, password=pwd, host=host, port=int(port), database=db
    )
    cursor = conn.cursor()
    cursor.execute(f"DELETE FROM Operations WHERE ID>=0 AND year='{year}'")
    cursor.execute(f"DELETE FROM Starts     WHERE ID>=0 AND year='{year}'")
    conn.commit()

    ops_batch: list[tuple] = []
    starts_batch: list[tuple] = []

    for idx, g in enumerate(root.findall(f"{list_tag}/{op_tag}")):

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
        address = _text(g, "INDIRIZZO")
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

        print(
            f"[{idx}] {op.opn} | {op.date} | {op.exit}-{op.close} | {op.typology} | ({op.x},{op.y}) | {op.loc} | {op.boss} | {op.address} | {op.caller} | {op.operator}"
        )

        # --- Datetime computation -----------------------------------------------
        base_date = _parse_date(op.date)
        ref_sec = 0  # fallback

        dt_exit = dt_close = None

        if op.exit:
            t = _parse_time(op.exit)
            ref_sec = t.hour * 3600 + t.minute * 60
            dt_exit = dt.datetime.combine(base_date, t)

        if op.close and op.exit:
            dt_close = _combine(base_date, op.close, ref_sec)

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
                op.operator
            )
        )

        # --- Starts -------------------------------------------------------------
        for j, g_flag in enumerate(g.findall(f".//{start_tag}")):
            vehicle = _text(g_flag, "SIGLA_MEZZO")
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

            if start.exit:
                dt_s_exit = _combine(base_date, start.exit, ref_sec)
            if start.inplace:
                dt_s_inplace = _combine(base_date, start.inplace, ref_sec)
            if start.back:
                dt_s_back = _combine(base_date, start.back, ref_sec)

            print(
                f"  [{j}] {start.vehicle} | {start.exit} | {start.inplace} | {start.back} | {start.nom}"
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
            "INSERT INTO Operations (ID, year, opn, date, dt_exit, dt_close, typology, x, y, loc, boss, address, caller, operator) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            ops_batch,
        )
        cursor.executemany(
            "INSERT INTO Starts (OpID, ID, year, vehicle, exit_dt, inplace_dt, back_dt, boss) "
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


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python main.py <absolute_xml_path>")
        sys.exit(1)

    main(xml_path=sys.argv[1])