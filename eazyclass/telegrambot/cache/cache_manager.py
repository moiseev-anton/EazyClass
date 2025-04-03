class CacheManager:
    def __init__(self):
        self.faculties = {}
        self.teachers = {}

    def get_faculty(self, faculty_id: str) -> dict:
        """Возвращает данные факультета по ID."""
        return self.faculties.get(faculty_id, {})

    def get_course(self, faculty_id: str, course_id: str) -> dict:
        """Возвращает данные курса по ID факультета и курса."""
        faculty = self.get_faculty(faculty_id)
        return faculty.get("courses", {}).get(course_id, {})

    def get_group(self, faculty_id: str, course_id: str, group_id: int) -> dict:
        """Возвращает данные группы по ID факультета, курса и группы."""
        course = self.get_course(faculty_id, course_id)
        return next((g for g in course if g["id"] == group_id), {})

    def get_alphabet(self) -> list[str]:
        """Возвращает список букв (ключей) из teachers_cache."""
        return sorted(self.teachers.keys())

    def get_teachers_by_letter(self, letter: str) -> list[dict]:
        """Возвращает список учителей для заданной буквы."""
        return self.teachers.get(letter, [])

    def get_teacher(self, letter: str, teacher_id: int) -> dict:
        """Возвращает данные учителя по букве и ID."""
        teachers = self.get_teachers_by_letter(letter)
        return next((t for t in teachers if t["id"] == teacher_id), {})


cache_manager = CacheManager()

