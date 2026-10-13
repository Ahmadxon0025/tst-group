# TST Group — Davlat imtiyozlari taxtasi

A Kanban board of the 63 state support measures relevant to TST Group (TST, GIT, Mirshikor, Ibrat). The accountant reviews each one, records his answer, and moves it between columns.

**Live:** https://ahmadxon0025.github.io/tst-group/

## Columns

| Column | Meaning |
|---|---|
| Yangi | Not reviewed yet |
| O'rganilmoqda | Checking the conditions |
| Bizga mos | We will use it |
| Jarayonda | Application filed, in progress |
| Bajarildi | Result received |
| Mos emas | Does not apply to us |

## How it works

- Drag a card to another column, or open it and tap the column name. On a phone, hold the card for a moment before dragging.
- Each card has:
  - **what the measure gives**, its legal basis with a link to the law, the conditions, which company it applies to, the accountant's task, and the deadline;
  - fields for his answer, companies, owner and deadline, plus an important flag.
- **Hisobot** builds a Telegram-ready status text grouped by column, with his notes.
- **Zaxira** gives a backup code holding the whole board. Loading the code on another device or browser shows the same board.
- **+ Vazifa** adds custom tasks.

## Where the data lives

Progress is saved in the browser that made the changes (`localStorage`, key `tst-imtiyoz-board-v1`). Nothing is sent to a server.

- Each browser and device keeps its own board.
- To share progress, use **Hisobot** for a readable summary or **Zaxira** for the full state.
- Clearing browser data erases the board, so take a Zaxira backup regularly.

## Updating the measures

All card content is in the `M` array inside `index.html`. Each entry has these fields:

| Field | Meaning |
|---|---|
| `n` | number |
| `cat` | area |
| `imp` | important |
| `due` | `YYYY-MM-DD` |
| `co` | companies |
| `t` | title |
| `s` | one-line summary |
| `b` | what it gives |
| `a` | legal basis |
| `u` | link |
| `c` | conditions |
| `k` | who it applies to |
| `v` | accountant's task |
| `m` | deadline / reliability |

Editing the text does not reset anyone's progress. Saved status and answers are keyed by the card number, so keep the numbers stable.

## Notes

- Legal texts were read on 10 Oct 2026. A lawyer must confirm each measure before it is applied.
- This repo and site are public and contain company-specific figures (debts, enforcement cases, VAT refund). The page carries `noindex`, but anyone with the link can read it.
- Drag-and-drop uses [SortableJS](https://github.com/SortableJS/Sortable) 1.15.2 from cdnjs. Without it, cards still move by tapping.

## Bo'z ta'minotchilari CRM (`crm.html`)

**Live:** https://ahmadxon0025.github.io/tst-group/crm.html

A call-tracking CRM for greige (bo'z) suppliers: 79 active weaving companies outside Namangan — registered under weaving codes 13201 cotton, 13202 wool, 13203 silk, 13209 other fabrics, plus 4 whose directory listings show woven fabric (Kogon Nur Textile, Qorako'l Kumush Kalava, Quva Tekstil, Ark Eko). Spinners, finishers, garment makers, traders and others are excluded, with the director and phone from the company register (orginfo.uz, data dated mostly May–June 2025) and the fabrics where a directory publishes them.

- **Moslik (fit):** A = publishes greige/bed-linen fabrics; B = registered cotton-fabric weaver (OKED 13201/13209); C = wool/silk weaver.
- Each company has a status (Yangi → Qo'ng'iroq qilindi / Javob yo'q → Narx olindi → Namuna / sinov → Ta'minotchi, or Mos emas), call fields (person, price $/m, width, MOQ, payment terms, next call date), notes and a dated history.
- **Nearest first:** pick a starting point (phone GPS, or Namangan/Toshkent/Buxoro/Samarqand/Marg'ilon/Andijon/Qo'qon/Urganch) and the list sorts by distance (≈ road km = straight line × 1.25). Coordinates are district or city centres taken from each registered address (`geo.py`), so companies in the same town show the same distance; "Xaritada" opens the real address in Yandex Maps.
- **Marshrut:** add companies from their card, then "Marshrut" orders them nearest-next from the starting point, with phones and map links, and copies the list for Telegram. The route is kept on that phone only.
- **Shared:** changes sync through the same Firebase database as the board (path `boards/tst-crm-7c1a9e`), one record per company, newest edit wins. Without a connection it keeps working locally (`localStorage`, key `tst-crm-taminotchi-v1`).
- **Hisobot** builds a Telegram summary; **Zaxira** gives a full backup code.
- To update the list: edit `suppliers.json`, then run `python3 build_crm.py` to rebuild `crm.html`.
- Registry phones are often the director's mobile or an old number; confirm on the call.
