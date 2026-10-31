# The Latin → Cyrillic rules (Python side; static/translit.js mirrors them — checked in a browser test).
import pytest

from core.translit import to_cyrillic


@pytest.mark.parametrize("latin,cyr", [
    ("Vazifa qo'shish", "Вазифа қўшиш"),
    ("Bajarildi", "Бажарилди"),
    ("Kechikkan", "Кечиккан"),
    ("Mening vazifalarim", "Менинг вазифаларим"),
    ("Yangi vazifa", "Янги вазифа"),
    ("Ertaga", "Эртага"),
    ("bo'yicha", "бўйича"),
    ("G'alla", "Ғалла"),
    ("Shanba", "Шанба"),
    ("Chorshanba", "Чоршанба"),
    ("Payshanba", "Пайшанба"),
    ("Yakshanba", "Якшанба"),
    ("Juma", "Жума"),
    ("ma'lumotnomasi", "маълумотномаси"),
    ("Hafta", "Ҳафта"),
    ("SHTAB", "ШТАБ"),
    ("Ali aka", "Али ака"),
    ("24.04 grafik", "24.04 график"),
    ("Abdulla aka", "Абдулла ака"),
    ("30-oktabr – 5-noyabr", "30-октябрь – 5-ноябрь"),
    ("Oktabr – Noyabr 2026", "Октябрь – Ноябрь 2026"),
    ("2-noy", "2-ноя"),
    ("Kechikkan: 3 kun", "Кечиккан: 3 кун"),
])
def test_to_cyrillic(latin, cyr):
    assert to_cyrillic(latin) == cyr
