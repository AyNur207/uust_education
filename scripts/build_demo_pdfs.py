"""Optional asset generation, requires PyMuPDF. Not needed to run the site."""
from pathlib import Path
import pymupdf as fitz

from seed import DEMO_MATERIALS

ROOT = Path(__file__).resolve().parents[1]
FONT = Path("C:/Windows/Fonts/arial.ttf")
OUT = ROOT / "static" / "demo"

EXAMPLES = {
    1: "01  Что такое массив\n\nМассив — набор элементов одного типа, расположенных в памяти последовательно. Индексация начинается с нуля.\n\nint a[5] = {2, 4, 6, 8, 10};\nfor (int i = 0; i < 5; i++) {\n    cout << a[i] << \" \";\n}\n\n02  Цикл for\n\nИспользуй цикл, когда известно количество повторений. На каждом шаге изменяется значение счётчика.\n\nВажно: последний индекс массива из n элементов равен n − 1.",
    2: "Матрица — прямоугольная таблица чисел.\n\nДля матрицы 2 × 2 определитель равен ad − bc.\n\nПример: определитель [[2, 1], [3, 4]] равен 2 × 4 − 1 × 3 = 5.\n\nЗадание: найди определитель [[3, 2], [1, 5]]. Ответ: 13.",
    3: "Present Simple: I study every day. — Я учусь каждый день.\n\nPresent Continuous: I am studying now. — Я сейчас учусь.\n\nPast Simple: I studied yesterday. — Я учился вчера.\n\nFuture Simple: I will study tomorrow. — Я буду учиться завтра.\n\nОбрати внимание на слова every day, now, yesterday и tomorrow.",
    4: "Двоичный поиск работает с отсортированными данными.\n\n1. Найди середину диапазона.\n2. Сравни средний элемент с искомым.\n3. Оставь подходящую половину.\n4. Повторяй, пока диапазон не станет пустым.\n\nСложность: O(log n).\n\nЗадание: найди 9 в массиве [1, 3, 5, 7, 9, 11].",
    5: "Число a называется пределом последовательности, если для любого ε > 0 существует N, такое что при n > N выполняется |x_n − a| < ε.\n\nПример: x_n = 1/n стремится к нулю. Достаточно выбрать N > 1/ε.\n\nЗадание: найди предел (2n + 1)/n. Ответ: 2.",
    6: "Переменные: const name = 'Студент';\n\nФункция: function square(x) { return x * x; }\n\nВызов: console.log(square(5)); // 25\n\nСобытие: button.addEventListener('click', handler);\n\nЗадание: напиши функцию, возвращающую сумму двух чисел.",
    8: "education — образование\nstudent — студент\nsubject — предмет\nlecture — лекция\nassignment — задание\nexam — экзамен\n\nПример: My favourite subject is computer science.\n\nЗадание: расскажи о своём любимом предмете в трёх предложениях.",
    9: "1721 — провозглашение Российской империи.\n\n1861 — отмена крепостного права.\n\n1905–1907 — первая российская революция.\n\n1917 — прекращение существования монархии.\n\nЗадание: объясни, как реформы 1860-х годов повлияли на общество.",
    10: "Государство — организация публичной власти на определённой территории.\n\nОсновные признаки: территория, население, публичная власть, суверенитет и система права.\n\nЦивилизационный подход рассматривает исторические общества с учётом культуры, религии и традиций.\n\nЗадание: сравни понятия «общество» и «государство».",
    11: "Информационная технология — совокупность методов и средств сбора, хранения, обработки и передачи информации.\n\nКомпоненты: данные, программное обеспечение, оборудование, сети и люди.\n\nПример: библиотечная система хранит сведения о книгах и помогает найти нужное издание.\n\nЗадание: опиши компоненты каталога учебных материалов.",
    12: "Вопросы для самопроверки\n\n1. Чем данные отличаются от информации?\n2. Какие устройства хранят данные?\n3. Для чего нужна база данных?\n4. Что такое информационная система?\n5. Какие операции можно выполнять с информацией?\n\nПопробуй ответить своими словами и привести пример.",
}


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    for i, row in enumerate(DEMO_MATERIALS, 1):
        if i not in EXAMPLES:
            continue
        doc = fitz.open()
        for n in range(12 if i == 1 else 1):
            page = doc.new_page(width=595, height=842)
            page.insert_font(fontname="InterFallback", fontfile=str(FONT))
            page.draw_rect(fitz.Rect(0,0,595,842), color=None, fill=(1,1,1))
            page.insert_text((48,48), "Лучше СДО · ДЕМОНСТРАЦИОННЫЙ ПРИМЕР", fontname="InterFallback", fontsize=9, color=(.39,.25,.82))
            page.insert_textbox(fitz.Rect(48,85,547,170), row[0], fontname="InterFallback", fontsize=25, color=(.14,.14,.22))
            text = EXAMPLES[i] if n == 0 else f"Практика · страница {n+1}\n\nЗадание {n}: создай массив из {n+3} целых чисел.\n\n1. Выведи все элементы массива.\n2. Найди сумму элементов.\n3. Найди наибольший элемент.\n4. Подсчитай количество положительных чисел.\n\nПроверь программу на нулях, отрицательных и одинаковых значениях."
            remaining = page.insert_textbox(fitz.Rect(48,190,547,720), text, fontname="InterFallback", fontsize=13, lineheight=1.5, color=(.25,.24,.33))
            if remaining < 0:
                raise RuntimeError(f"Text overflow in demo {i}, page {n+1}")
            page.insert_text((48,785), f"Учебный пример, не оригинальный файл из макета · {n+1}", fontname="InterFallback", fontsize=9, color=(.45,.44,.53))
        doc.subset_fonts()
        doc.save(OUT / f"{i}.pdf", garbage=4, deflate=True)
        doc.close()
    print(f"Built {len(EXAMPLES)} demo PDFs in {OUT}")


if __name__ == "__main__":
    build()
