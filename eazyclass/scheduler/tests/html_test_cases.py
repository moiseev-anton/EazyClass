valid_html = """
<body>
<table>
    <tbody>
        <tr>
        <td align="center" colspan="5"><p align="center" class="shadow"><b>Название группы</b></p>
        <a href="view.php?id=00312" class="modernsmall">Обновить</a>
        <a href="grupp.php" class="modernsmall">Список групп</a>
        </td>
        </tr>

        <tr class="shadow"><td colspan="5" align="center">08.12.2024 - Воскресенье</td></tr>
        
        <tr class="shadow"><td colspan="5" align="center">09.12.2024 - Понедельник</td></tr>
        <tr>
            <td>Пара</td><td>Предмет</td><td>Аудитория</td><td>Преподаватель</td><td>Подгруппа</td>
        </tr>

        <tr class="shadow">
            <td>1</td><td>Математика</td><td>А101</td><td>Иванов И.И.</td><td></td>
        </tr>

        <tr class="shadow">
            <td>2</td><td>Геометрия</td><td></td><td>Петров П.П.</td><td>1</td>
        </tr>

        <tr class="shadow"><td colspan="5" align="center">10.12.2024 - Вторник</td></tr>

        <tr class="shadow"><td colspan="5" align="center">11.12.2024 - Среда</td></tr>
        <tr class="shadow">
            <td>2</td><td>Информатика</td><td>А102</td><td>Иванов И.И.</td><td>2</td>
        </tr>
        <tr class="shadow">
            <td>3</td><td>Химия</td><td>А102</td><td>Петров П.П.</td><td></td>
        </tr>

        <tr class="shadow"><td colspan="5" align="center">12.12.2024 - Четверг</td></tr>

        <tr class="shadow">
            <td>1</td><td>Инженерная графика</td><td>А102</td><td>Петров П.П.</td><td></td>
        </tr>
        <tr class="shadow">
            <td>3</td><td>Инженерная графика</td><td>А102</td><td>Петров П.П.</td><td></td>
        </tr>
        <tr class="shadow">
            <td>4</td><td></td><td></td><td></td><td></td>
        </tr>
        

        <tr class="shadow"><td colspan="5" align="center">13.12.2024 - Пятница</td></tr>
        <tr class="shadow"><td colspan="5" align="center">14.12.2024 - Суббота</td></tr>
    </tbody>
</table>
</body>
"""

expected_valid_result = [
    {'classroom_title': 'А101',
     'date': '09.12.2024',
     'lesson_number': '1',
     'subgroup': '',
     'subject_title': 'Математика',
     'teacher_fullname': 'Иванов И.И.'},

    {'classroom_title': '',
     'date': '09.12.2024',
     'lesson_number': '2',
     'subgroup': '1',
     'subject_title': 'Геометрия',
     'teacher_fullname': 'Петров П.П.'},

    {'classroom_title': 'А102',
     'date': '11.12.2024',
     'lesson_number': '2',
     'subgroup': '2',
     'subject_title': 'Информатика',
     'teacher_fullname': 'Иванов И.И.'},

    {'classroom_title': 'А102',
     'date': '11.12.2024',
     'lesson_number': '3',
     'subgroup': '',
     'subject_title': 'Химия',
     'teacher_fullname': 'Петров П.П.'},

    {'classroom_title': 'А102',
     'date': '12.12.2024',
     'lesson_number': '1',
     'subgroup': '',
     'subject_title': 'Инженерная графика',
     'teacher_fullname': 'Петров П.П.'},

    {'classroom_title': 'А102',
     'date': '12.12.2024',
     'lesson_number': '3',
     'subgroup': '',
     'subject_title': 'Инженерная графика',
     'teacher_fullname': 'Петров П.П.'},

    {'classroom_title': '',
     'date': '12.12.2024',
     'lesson_number': '4',
     'subgroup': '',
     'subject_title': '',
     'teacher_fullname': ''}
]

#-----------------------------------

empty_shedule = """
<body>
<table>
    <tbody>
        <tr>
        <td align="center" colspan="5"><p><b>Название группы</b></p></td>
        </tr>

        <tr class="shadow"><td colspan="5" align="center">08.12.2024 - Воскресенье</td></tr>
        <tr class="shadow"><td colspan="5" align="center">09.12.2024 - Понедельник</td></tr>
        <tr class="shadow"><td colspan="5" align="center">10.12.2024 - Вторник</td></tr>
        <tr class="shadow"><td colspan="5" align="center">11.12.2024 - Среда</td></tr>
        <tr class="shadow"><td colspan="5" align="center">12.12.2024 - Четверг</td></tr>
        <tr class="shadow"><td colspan="5" align="center">13.12.2024 - Пятница</td></tr>
        <tr class="shadow"><td colspan="5" align="center">14.12.2024 - Суббота</td></tr>
    </tbody>
</table>
</body>
"""

html_test_cases = [
    (valid_html, expected_valid_result),
    (empty_shedule, []),
    ('', []),
]

#==========================================

html_missed_first_date_row = """
<body>
<table>
    <tbody>
        <tr>
        <td align="center" colspan="5"><p><b>Название группы</b></p></td>
        </tr>

        <tr class="shadow">
            <td>1</td><td>Математика</td><td>А101</td><td>Иванов И.И.</td><td></td>
        </tr>

        <tr class="shadow"><td colspan="5" align="center">11.12.2024 - Среда</td></tr>
        <tr class="shadow">
            <td>2</td><td>Информатика</td><td>А102</td><td>Иванов И.И.</td><td>2</td>
        </tr>
    </tbody>
</table>
</body>
"""

equal_lesson_numbers_for_one_date = """
<body>
<table>
    <tbody>

        <tr class="shadow"><td colspan="5" align="center">09.12.2024 - Понедельник</td></tr>

        <tr class="shadow">
            <td>2</td><td>Геометрия</td><td></td><td>Петров П.П.</td><td>1</td>
        </tr>

        <tr class="shadow">
            <td>2</td><td>Информатика</td><td>А102</td><td>Иванов И.И.</td><td>2</td>
        </tr>
    </tbody>
</table>
</body>
"""

invalid_lesson_order = """
<body>
<table>
    <tbody>
        <tr class="shadow"><td colspan="5" align="center">09.12.2024 - Понедельник</td></tr>

        <tr class="shadow">
            <td>2</td><td>Геометрия</td><td></td><td>Петров П.П.</td><td>1</td>
        </tr>

        <tr class="shadow">
            <td>1</td><td>Информатика</td><td>А102</td><td>Иванов И.И.</td><td>2</td>
        </tr>
    </tbody>
</table>
</body>
"""

missed_cell_in_date_row = """
<body>
<table>
    <tbody>
        <tr class="shadow"></tr>

        <tr class="shadow">
            <td>2</td><td>Петров П.П.</td><td>1</td>
        </tr>
    </tbody>
</table>
</body>
"""

missed_cells_in_lesson_row = """
<body>
<table>
    <tbody>
        <tr class="shadow"><td colspan="5" align="center">09.12.2024 - Понедельник</td></tr>

        <tr class="shadow">
            <td>2</td><td>Петров П.П.</td><td>1</td>
        </tr>
    </tbody>
</table>
</body>
"""

invalid_date = """
<body>
<table>
    <tbody>
        <tr class="shadow"><td colspan="5" align="center">09-12-2024 - Понедельник</td></tr>

        <tr class="shadow">
            <td>1</td><td>Информатика</td><td>А102</td><td>Иванов И.И.</td><td>2</td>
        </tr>
    </tbody>
</table>
</body>
"""

not_numeric_lesson_number = """
<body>
<table>
    <tbody>
        <tr class="shadow"><td colspan="5" align="center">09.12.2024 - Понедельник</td></tr>

        <tr class="shadow">
            <td> </td><td>Информатика</td><td>А102</td><td>Иванов И.И.</td><td>2</td>
        </tr>
    </tbody>
</table>
</body>
"""

invalid_html_test_cases = [
    html_missed_first_date_row,
    equal_lesson_numbers_for_one_date,
    invalid_lesson_order,
    missed_cell_in_date_row,
    missed_cells_in_lesson_row,
    invalid_date,
    not_numeric_lesson_number,
]
