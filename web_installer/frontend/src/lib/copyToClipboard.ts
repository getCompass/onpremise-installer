// функция для копирования текста в буфер обмена
export function copyToClipboard(text: string): void {

    // создание нового текстового поля (невидимого)
    const tempElement = document.createElement("textarea");

    // устанавливаем значение, которое нужно скопировать
    tempElement.value = text;

    // стилизуем, чтобы он был "невидимым" и не влиял на layout страницы
    tempElement.style.position = "fixed";
    tempElement.style.top = "0";
    tempElement.style.left = "-9999px";
    tempElement.setAttribute("readonly", "");  // предотвращение отображения клавиатуры на мобильных устройствах

    // добавление элемента в документ
    document.body.appendChild(tempElement);

    // выбор текста внутри элемента
    tempElement.select();
    tempElement.setSelectionRange(0, 99999);  // Для мобильных устройств

    // копирование текста в буфер обмена
    document.execCommand("copy");

    // удаление временного элемента из документа
    document.body.removeChild(tempElement);
}