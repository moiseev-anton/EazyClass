document.getElementById("add-form-row").addEventListener("click", function() {
    var formset = document.querySelector(".formset");
    var formCount = formset.querySelectorAll(".form-row").length;
    var newForm = formset.querySelector(".form-row").cloneNode(true);  // Копируем первую строку формы

    // Обновляем индексы в форме
    newForm.innerHTML = newForm.innerHTML.replace(/form-\d+/g, "form-" + formCount);
    formset.appendChild(newForm);  // Добавляем новую форму
});


