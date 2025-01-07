/**
 * Инициализация скрипта после загрузки DOM.
 */
document.addEventListener("DOMContentLoaded", function () {
    const MAX_RETRIES = 50; // Максимальное число попыток подключить Наблюдателя нажатия "Добавить Timing"
    let attempts = 0;

    // Ищем контейнер с формами
    const formContainer = document.querySelector("div.tabular.inline-related.last-related > fieldset.module");
    if (!formContainer) {
        console.error("Контейнер формы Timings не найден");
        return;
    }

    // Инициализация логики обновления и обработки чекбоксов
    updateDisabledWeekdays(formContainer)
    addEventListenersToCheckboxes(formContainer)
    checkLinkExists();


    /**
     * Проверяет существование ссылки "Добавить Timing" в контейнере.
     * Если ссылка найдена, запускается установка Наблюдателя нажатия на ссылку "Добавить Timing".
     */
    function checkLinkExists() {
        attempts++;
        const addRowLink = formContainer.querySelector("tr.add-row a");
        if (addRowLink) {
            initializeScript(addRowLink);
        } else if (attempts < MAX_RETRIES) {
            requestAnimationFrame(checkLinkExists);
        } else {
        }
    }

    /**
     * Инициализирует логику скрипта при нажатии на ссылку "Добавить строку".
     * @param {HTMLElement} addRowLink - Ссылка для добавления новой строки.
     */
    function initializeScript(addRowLink) {
        addRowLink.addEventListener("click", () => {
            updateDisabledWeekdays(formContainer)
            addEventListenersToCheckboxes(formContainer)
        });
    }


});

/**
 * Обновляет состояние чекбоксов на основе выбранных значений.
 * Если день недели уже выбран, остальные чекбоксы с этим значением блокируются.
 * @param {HTMLElement} formContainer - Контейнер с формами.
 */
function updateDisabledWeekdays(formContainer) {
    let checkboxes = formContainer.querySelectorAll("input[type='checkbox'][name*='weekdays']");
    let selectedDays = new Set();

    // Собираем выбранные дни недели
    checkboxes.forEach(checkbox => {
        if (checkbox.checked) selectedDays.add(checkbox.value);
    });

    // Активация/деактивация чекбоксов
    checkboxes.forEach(checkbox => {
        checkbox.disabled = !checkbox.checked && selectedDays.has(checkbox.value);
    });
}

/**
 * Добавляет обработчики событий "change" для всех чекбоксов в строках формы.
 * При изменении состояния чекбокса обновляется их доступность.
 * @param {HTMLElement} formContainer - Контейнер с формами.
 */
function addEventListenersToCheckboxes(formContainer) {
    const checkboxes = formContainer.querySelectorAll('tr.form-row:not(.empty-form) input[type="checkbox"]');
    checkboxes.forEach(checkbox => {
        // Убедимся, что обработчик не добавлен повторно
        if (!checkbox.hasListener) {
            checkbox.addEventListener("change", () => updateDisabledWeekdays(formContainer));
            checkbox.hasListener = true;
        }
    });
}
