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
