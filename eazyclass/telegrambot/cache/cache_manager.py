

class CacheManager:
    def __init__(self):
        self.faculties = {}
        self.teachers = {}

    def get_faculty(self, faculty_id: str) -> dict:
        """Возвращает данные факультета по ID."""
        return self.faculties.get(faculty_id, {})

    def get_faculty_courses(self, faculty_id) -> dict:
        """Возвращает данные всех курсов по ID факультета."""
        return self.get_faculty(faculty_id).get("courses", {})

    def get_course(self, faculty_id: str, course: str) -> dict:
        """Возвращает данные курса по ID факультета и курсу."""
        return self.get_faculty_courses(faculty_id).get(course, {})

    def get_group(self, faculty_id: str, course_id: str, group_id: str) -> dict:
        """Возвращает данные группы по ID факультета, курса и группы."""
        course = self.get_course(faculty_id, course_id)
        return course.get(group_id, {})

    def get_alphabet(self) -> list[str]:
        """Возвращает список букв (ключей) из teachers_cache."""
        return sorted(self.teachers.keys())

    def get_teachers_by_letter(self, letter: str) -> dict[str, dict]:
        """Возвращает список учителей для заданной буквы."""
        return self.teachers.get(letter, {})

    def get_teacher(self, letter: str, teacher_id: str) -> dict[str, dict]:
        """Возвращает данные учителя по букве и ID."""
        teachers = self.get_teachers_by_letter(letter)
        return teachers.get(teacher_id, {})


cache_manager = CacheManager()

