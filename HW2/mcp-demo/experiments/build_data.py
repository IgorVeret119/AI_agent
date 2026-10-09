"""Freeze the benchmark before observing model predictions."""
import asyncio
import datetime as dt
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from server import server

ROUTING_RULE = (
    "Choose the most specific applicable tool. A known class entry identifier uses the single-entry getter. "
    "All classes in one classroom uses the classroom listing. All classes on one weekday without a course filter "
    "uses the weekday listing. A course filter, combined course/day filters, or a general listing uses schedule search. "
    "The user refers to the current synthetic course schedule snapshot schedule-v1 unless explicitly stated otherwise."
)

NEAR = [
    ("exam_search", "Search the synthetic examination timetable by course and exam date; returns exams, not ordinary classes."),
    ("exam_get", "Get one examination by examination identifier from the exam timetable."),
    ("exam_day", "List every examination on one weekday in the examination timetable."),
    ("exam_room", "List examinations in a classroom; excludes regular course classes."),
    ("consultation_search", "Search teacher office-hour appointments by course and weekday."),
    ("consultation_get", "Get one teacher consultation appointment by appointment identifier."),
    ("consultation_day", "List teacher consultations and office hours on a weekday."),
    ("consultation_room", "List office-hour consultation slots in a classroom."),
    ("teacher_schedule_search", "Search a specific teacher's teaching workload by teacher and weekday."),
    ("teacher_schedule_get", "Get a teacher workload entry by workload identifier."),
    ("archive_schedule_search", "Search historical course schedule snapshots from previous semesters."),
    ("archive_schedule_get", "Read one archived schedule entry using an archive record identifier."),
    ("archive_schedule_day", "List all historical course classes on a weekday in an archived semester."),
    ("archive_schedule_room", "List historical classes held in a classroom during a previous semester."),
    ("schedule_create", "Create a new class in the synthetic course schedule; modifies the timetable."),
    ("schedule_update", "Change the time, weekday or classroom of an existing class entry."),
    ("schedule_delete", "Delete a class entry from the synthetic course timetable."),
    ("schedule_export", "Export the complete course timetable to an ICS calendar file."),
    ("schedule_conflicts", "Detect overlapping classroom bookings and conflicting class times."),
    ("room_availability", "Find free classroom time slots; returns availability rather than scheduled classes."),
    ("room_details", "Read classroom capacity, facilities and building address by room number."),
    ("course_details", "Read a course syllabus and prerequisites by course identifier; contains no class times."),
    ("course_enroll", "Enroll a student in a course; changes the enrollment roster."),
    ("calendar_search", "Search a student's personal calendar appointments by date and title."),
    ("calendar_get", "Read one personal calendar event using an event identifier."),
    ("calendar_day", "List personal calendar appointments on a date, including non-course events."),
    ("schedule_bus", "Search campus shuttle bus departure times by stop and weekday."),
    ("schedule_notifications", "Configure reminders about upcoming classes; changes notification settings."),
]

FAR_DOMAINS = {
    "weather": ["city weather forecasts", "weather observations", "precipitation alerts", "air quality readings"],
    "files": ["local file names", "file contents", "directory listings", "file metadata"],
    "issues": ["software issue tickets", "issue details", "issue comments", "issue labels"],
    "mail": ["email messages", "email contents", "mail folders", "email attachments"],
    "finance": ["stock quotes", "historical market prices", "exchange rates", "company fundamentals"],
    "music": ["music tracks", "album metadata", "artist biographies", "playlists"],
    "recipes": ["cooking recipes", "recipe ingredients", "nutrition information", "cooking techniques"],
    "books": ["library books", "book editions", "author biographies", "book reviews"],
    "maps": ["street addresses", "walking directions", "geographic coordinates", "nearby landmarks"],
    "inventory": ["warehouse products", "product stock levels", "warehouse locations", "shipment records"],
    "support": ["customer support cases", "support case details", "support case messages", "customer contact profiles"],
    "analytics": ["website traffic events", "traffic metrics", "conversion funnels", "audience segments"],
    "git": ["source code commits", "repository branches", "commit changes", "repository tags"],
    "images": ["image asset names", "image dimensions", "image color palettes", "image copyright metadata"],
    "travel": ["hotel listings", "hotel room types", "flight routes", "airport information"],
    "fitness": ["exercise routines", "exercise descriptions", "workout records", "equipment specifications"],
    "devices": ["network device records", "device firmware versions", "device status readings", "device configuration backups"],
}

QUERIES = [
    ("schedule_search", "Найди занятия курса agents в текущем учебном расписании."),
    ("schedule_search", "Покажи все занятия курса python из снимка schedule-v1."),
    ("schedule_search", "Какие пары по databases стоят в расписании?"),
    ("schedule_search", "Найди занятия agents, которые проходят в среду."),
    ("schedule_search", "Проверь расписание курса python на вторник."),
    ("schedule_search", "Выведи все записи текущего расписания без фильтров."),
    ("schedule_search", "Нужен поиск пар по курсу agents и дню monday."),
    ("schedule_search", "Есть ли у databases занятия в понедельник?"),
    ("schedule_get", "Открой занятие с идентификатором agents-mon."),
    ("schedule_get", "Получить одну запись расписания: python-tue."),
    ("schedule_get", "Покажи подробности занятия databases-wed из schedule-v1."),
    ("schedule_get", "Мне нужна конкретная пара agents-wed, её id уже известен."),
    ("schedule_get", "Прочитай запись agents-mon без поиска других занятий."),
    ("schedule_get", "У меня есть entry_id python-tue. Покажи соответствующее занятие."),
    ("schedule_get", "По ключу databases-wed получить занятие текущего расписания."),
    ("schedule_get", "Верни подробную запись пары agents-wed по её идентификатору."),
    ("schedule_day", "Выведи все учебные пары в понедельник, независимо от курса."),
    ("schedule_day", "Какие занятия текущего расписания проходят во вторник? Нужны все курсы."),
    ("schedule_day", "Покажи полное расписание учебных занятий на среду."),
    ("schedule_day", "Мне нужен список всех пар на monday из schedule-v1."),
    ("schedule_day", "Собери все занятия вторника, без фильтра по предмету."),
    ("schedule_day", "Что стоит в учебном расписании на wednesday по всем курсам?"),
    ("schedule_day", "Список обычных учебных занятий понедельника целиком."),
    ("schedule_room", "Какие учебные пары запланированы в аудитории 314?"),
    ("schedule_room", "Покажи занятия в кабинете 210 из текущего расписания."),
    ("schedule_room", "Все запланированные занятия аудитории 115."),
    ("schedule_room", "Нужен список пар, проходящих в комнате 314, по всем дням."),
    ("schedule_room", "Что за учебные занятия стоят для аудитории 210 в schedule-v1?"),
    ("schedule_room", "Перечисли пары в кабинете 115 без проверки свободных мест."),
    ("schedule_room", "Для аудитории 314 получи запланированные занятия всех курсов."),
]


def write(name, value):
    (ROOT / "data").mkdir(exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    (ROOT / "data" / name).write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode()).hexdigest()


def main():
    tools = [{"name": t.name, "description": t.description, "input_schema": t.input_schema, "source": "project:server.py", "near": False, "target": True} for t in asyncio.run(server.list_tools())]
    near = [{"name": n, "description": d, "source": "synthetic:hand-authored", "near": True, "target": False} for n, d in NEAR]
    far = [{"name": f"{domain}_{action}", "description": f"Retrieve {subject} for the {domain} domain.", "source": "synthetic:hand-authored-template", "near": False, "target": False} for domain, subjects in FAR_DOMAINS.items() for action, subject in zip(("search", "get", "list", "inspect"), subjects)]
    rng = random.Random(20261009)
    rng.shuffle(near)
    rng.shuffle(far)
    distractors = []
    for i, tool in enumerate(near):
        distractors.append(tool)
        distractors.extend(far[i * 2:i * 2 + 2])
    distractors.extend(far[len(near) * 2:])
    tools.extend(distractors)
    queries = [{"id": f"q{i+1:02}", "text": text, "gold": gold, "rubric": ROUTING_RULE} for i, (gold, text) in enumerate(QUERIES)]
    tasks = []
    weekdays = {"agents": 0, "python": 1, "databases": 2}
    for i in range(20):
        course = ("agents", "python", "databases")[i % 3]
        start = dt.date(2026, 10, 12) + dt.timedelta(days=weekdays[course] + 7 * (i // 3))
        end = start + dt.timedelta(days=7)
        tasks.append({"id": f"t{i+1:02}", "course": course, "start_date": start.isoformat(), "end_date": end.isoformat(), "schedule_handle": "schedule-v1", "text": f"Найди хотя бы одно занятие курса {course} между {start} и {end} включительно. Начни с date={start}. Верни найденные entry_id и date; используй только данные инструмента."})
    assert len(tools) == 100 and len({t["name"] for t in tools}) == 100
    hashes = {"tools.json": write("tools.json", tools), "queries.json": write("queries.json", queries), "loop_tasks.json": write("loop_tasks.json", tasks)}
    manifest = {"seed": 20261009, "tool_count": 100, "targets": 4, "synthetic_distractors": 96, "near_distractors": 28, "queries": 30, "loop_tasks": 20, "routing_rule": ROUTING_RULE, "pool_sizes": [5, 20, 50, 100], "nested_pool_names": {str(n): [t["name"] for t in tools[:n]] for n in (5, 20, 50, 100)}, "sha256": hashes}
    write("dataset-manifest.json", manifest)
    print(json.dumps({k: manifest[k] for k in ("tool_count", "near_distractors", "queries", "loop_tasks")}, indent=2))


if __name__ == "__main__":
    main()
