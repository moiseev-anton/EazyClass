import logging

from bs4 import BeautifulSoup

from scheduler.fetched_data_sync.dto import FacultyData, GroupData

logger = logging.getLogger(__name__)


def parse_faculties_page(html_content: bytes) -> list[FacultyData]:
    """Парсит HTML и возвращает список факультетов с их группами."""
    soup = BeautifulSoup(html_content, "lxml")
    faculties: list[FacultyData] = []

    faculty_blocks = soup.find_all("p", class_="shadow")
    for block in faculty_blocks:
        group_tags = block.find_next_sibling("p").find_all("a")
        faculty = FacultyData(
            title=block.text,
            groups=[GroupData(title=tag.text, endpoint=tag["href"]) for tag in group_tags],
        )

        if faculty.groups:
            faculties.append(faculty)
            logger.debug(f"Факультет: {faculty.title}, групп: {len(faculty.groups)}")

    return faculties
