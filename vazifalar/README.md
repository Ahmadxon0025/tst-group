# TST Vazifalar

A lean NAZORAT instance: tasks only. It reuses nazorat-erp's CORE patterns (no-delete base, append-only
history, audit log, role policy from CONFIG). It shares no data with any other deployment.

## What is here
- `/`: the Hafta page. A Kechikkan column plus 7 days, the ‹ Bugun › arrows, the Kim filter (rahbar only) and + Vazifa (rahbar only).
- `/mening/`: Mening vazifalarim. Sections: Kechikkan, Bugun, Keyingi, Bajarilgan (7 kun).
- `/vazifa/<id>/`: the task card. Bajarildi / Qayta ochish, Izoh, change Muddat (rahbar), Bekor qilish with a reason (rahbar), and Tarix.
- `/shtab/`: the Monday Shtab page. Each person's overdue tasks, tasks due this week, and the number done last week. Can be printed.
- Hand a task to someone else, plus an optional company label (TST, GIT, Mirshikor, Ibrat, Guruh) with a filter.
- Each person chooses Latin or Cyrillic (`/yozuv/`). The Cyrillic rules are in `core/translit.py` (bot) and `static/translit.js` (pages), which are kept the same.
- On a phone the days stack vertically. Past empty days are hidden.

## Rules (guard tests in tests/test_guards.py)
- Nothing is deleted. A task is cancelled with a reason.
- Every change becomes a VazifaEvent (append-only) and an AuditLog row, in one transaction.
- Roles: `bosh` sees and manages everything. A `menejer` gives tasks to anyone; he sees tasks given to him and tasks he gave, and he manages the tasks he gave. A `xodim` (for later) sees and closes only his own tasks.
- Time comes from the server, in Asia/Tashkent.

## People
The people are not in the code. On the server they live in `people.json` next to `manage.py` (git-ignored), in the format of `people.example.json`.

## Server
`scripts/install.sh` (one-time, Ubuntu 24.04) and `scripts/deploy.sh` (updates; refuses on failing tests).

## Run locally
1. `pip install -r requirements.txt`
2. `DJANGO_DEBUG=1 python manage.py migrate`
3. Copy `people.example.json` to `people.json`, then `DJANGO_DEBUG=1 python manage.py seed_people`. Each one-time password is printed once on the console.
4. `DJANGO_DEBUG=1 python manage.py runserver`
5. Tests: `python -m pytest`

## TST-specific values
All of them are in `config/values.py`: people, roles, wording, bot times. Nothing TST-specific lives in the code.

## Telegram bot
Linking by one-time code from the "Telegram" page; notices (given, handed over, done, comment, date change, cancel);
08:00 list, 18:00 reminder, next-day "late" notice to the giver, Monday 09:00 summary to the bosh;
/bugun /hafta /kechikkan /yangi; Bajarildi and Izoh buttons; nightly database copy to the bosh's Telegram.
