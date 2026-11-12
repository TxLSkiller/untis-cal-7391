import sys
import toml
import requests
from datetime import datetime, timedelta
from ics import Calendar, Event
from zoneinfo import ZoneInfo

config = toml.load(sys.argv[1])["user"]
server = config["server"]
school = config["school"]
username = config["username"]
password = config["password"]

s = requests.Session()
s.headers.update({"User-Agent": "Mozilla/5.0"})

# 1. Login in WebUntis
login_url = f"https://{server}/WebUntis/jsonrpc.do?school={school}"
res = s.post(login_url, json={
    "id": "1", "method": "authenticate",
    "params": {"user": username, "password": password, "client": "web"},
    "jsonrpc": "2.0"
}).json()

if "error" in res:
    raise Exception(f"Login fehlgeschlagen: {res['error']}")

person_id = res["result"]["personId"]
person_type = res["result"]["personType"]

# 2. Aktuellen Wochenplan inklusive Vertretungen & Veranstaltungen abrufen
cal = Calendar()
tz = ZoneInfo("Europe/Berlin")
today = datetime.now(tz).date()

# Aktuelle Woche und nächste Woche abrufen
for week_offset in:
    target_date = (today + timedelta(days=week_offset)).strftime("%Y-%m-%d")
    tt_url = f"https://{server}/WebUntis/api/public/timetable/weekly/data?elementType={person_type}&elementId={person_id}&date={target_date}&formatId=1"
    data = s.get(tt_url).json()

    result = data.get("data", {}).get("result", {})
    elements = {e["id"]: e for e in result.get("data", {}).get("elements", [])}
    periods = result.get("data", {}).get("elementPeriods", {}).get(str(person_id), [])

    for p in periods:
        # Ausgefallene Stunden überspringen
        if p.get("cellState") == "CANCEL":
            continue

        date_str = str(p["date"])
        start_str = f"{p['startTime']:04d}"
        end_str = f"{p['endTime']:04d}"

        dt_start = datetime.strptime(f"{date_str}{start_str}", "%Y%m%d%H%M").replace(tzinfo=tz)
        dt_end = datetime.strptime(f"{date_str}{end_str}", "%Y%m%d%H%M").replace(tzinfo=tz)

        # Fächer, Räume und Veranstaltungstexte sammeln
        subjects = []
        rooms = []
        for el in p.get("elements", []):
            el_info = elements.get(el["id"], {})
            name = el_info.get("name", "")
            if el["type"] == 3 and name:
                subjects.append(name)
            elif el["type"] == 4 and name:
                rooms.append(name)

        title = ", ".join(subjects) if subjects else (p.get("lessonText") or p.get("substText") or "Veranstaltung")
        if p.get("cellState") == "SUBSTITUTION":
            title = f"Vertretung: {title}"

        e = Event()
        e.name = title
        e.begin = dt_start
        e.end = dt_end
        if rooms:
            e.location = ", ".join(rooms)
        desc_parts = [x for x in [p.get("lessonText"), p.get("substText"), p.get("info")] if x]
        if desc_parts:
            e.description = " | ".join(desc_parts)
        e.uid = f"{p['id']}-{date_str}-{start_str}@webuntis-sync"
        cal.events.add(e)

with open("webuntis-timetable.ics", "w", encoding="utf-8") as f:
    f.writelines(cal.serialize_iter())
