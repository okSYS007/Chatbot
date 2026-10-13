from __future__ import annotations

import logging
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from app.config import load_config, parse_daily_card, save_daily_card
from app.card_content import read_card_text, scan_card_folder
from app.message_parts import split_telegram_text
from app.welcome import get_welcome_templates, validate_welcome_templates


def _save_with_bot_stopped(panel, callback) -> None:
    was_running = bool(panel.bot_process and panel.bot_process.poll() is None)
    panel._terminate_bot_process()
    try:
        callback()
        panel.config = load_config()
    finally:
        if was_running:
            panel._launch_bot_process()


def edit_welcomes(panel) -> None:
    window = tk.Toplevel(panel.root)
    window.title("Случайные приветствия")
    window.geometry("650x420")
    window.transient(panel.root)
    window.grab_set()
    frame = ttk.Frame(window, padding=12)
    frame.pack(fill=tk.BOTH, expand=True)
    ttk.Label(frame, text="Одно приветствие на строку. Бот случайно выбирает один вариант.").pack(anchor=tk.W)
    ttk.Label(frame, text="Подстановки: {name}, {username}, {user_id}, {group}").pack(anchor=tk.W, pady=(4, 8))
    editor = tk.Text(frame, wrap=tk.WORD, height=12)
    editor.pack(fill=tk.BOTH, expand=True)
    editor.insert("1.0", "\n".join(get_welcome_templates(load_config(), panel.storage())))

    def save() -> None:
        values, error = validate_welcome_templates(editor.get("1.0", "end-1c").splitlines())
        if error:
            messagebox.showerror("Приветствия", error, parent=window)
            return
        try:
            _save_with_bot_stopped(panel, lambda: panel.storage().set_settings({"welcome_texts": values}))
        except (OSError, ValueError) as exc:
            messagebox.showerror("Приветствия", f"Не удалось сохранить: {exc}", parent=window)
            return
        logging.getLogger(__name__).info("Welcome templates changed in local panel: count=%s", len(values))
        window.destroy()

    ttk.Button(frame, text="Сохранить", command=save).pack(anchor=tk.E, pady=(8, 0))


def edit_daily_card(panel) -> None:
    from app.card_matching import build_match_catalog, match_pattern, validate_patterns
    from app.daily_card import DailyCardService

    config = load_config().daily_card
    window = tk.Toplevel(panel.root)
    window.title("Карта дня")
    window.geometry("850x650")
    window.minsize(800, 620)
    window.transient(panel.root)
    window.grab_set()
    frame = ttk.Frame(window, padding=12)
    frame.pack(fill=tk.BOTH, expand=True)
    enabled = tk.BooleanVar(value=config.enabled)
    ttk.Checkbutton(frame, text="Публиковать карту каждый день", variable=enabled).pack(anchor=tk.W, pady=(0, 8))
    notebook = ttk.Notebook(frame)
    notebook.pack(fill=tk.BOTH, expand=True)
    content = ttk.Frame(notebook, padding=12)
    schedule = ttk.Frame(notebook, padding=12)
    notebook.add(content, text="Папки и шаблоны")
    notebook.add(schedule, text="Расписание")
    content.columnconfigure(1, weight=1)
    content.rowconfigure(3, weight=1)
    schedule.columnconfigure(1, weight=1)
    fields = {}

    def browse(key, title):
        selected = filedialog.askdirectory(parent=window, title=title)
        if selected:
            fields[key].set(selected)

    for row, (key, label, value) in enumerate([
        ("images_folder", "Папка картинок", config.images_folder or Path("cards/images")),
        ("texts_folder", "Папка текстов", config.texts_folder or Path("cards/texts")),
    ]):
        ttk.Label(content, text=label).grid(row=row, column=0, sticky=tk.W, padx=(0, 8), pady=6)
        fields[key] = tk.StringVar(value=str(value))
        ttk.Entry(content, textvariable=fields[key]).grid(row=row, column=1, sticky=tk.EW)
        ttk.Button(content, text="Выбрать…", command=lambda k=key, t=label: browse(k, t)).grid(row=row, column=2, padx=(6, 0))

    ttk.Label(content, text="Шаблон должен встречаться в имени картинки и текста. Например: 8 пентаклей.",
              wraplength=740).grid(row=2, column=0, columnspan=3, sticky=tk.W, pady=(8, 6))
    table_frame = ttk.Frame(content)
    table_frame.grid(row=3, column=0, columnspan=3, sticky=tk.NSEW)
    table_frame.columnconfigure(0, weight=1)
    table_frame.rowconfigure(0, weight=1)
    table = ttk.Treeview(table_frame, columns=("pattern", "images", "texts"), show="headings", height=8)
    for key, label, width in [("pattern", "Шаблон", 440), ("images", "Картинок", 110), ("texts", "Текстов", 110)]:
        table.heading(key, text=label)
        table.column(key, width=width, minwidth=80, stretch=(key == "pattern"), anchor=tk.W if key == "pattern" else tk.CENTER)
    table.grid(row=0, column=0, sticky=tk.NSEW)
    scrollbar = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=table.yview)
    scrollbar.grid(row=0, column=1, sticky=tk.NS)
    table.configure(yscrollcommand=scrollbar.set)
    for pattern in config.patterns:
        table.insert("", tk.END, values=(pattern, "—", "—"))

    entry_value = tk.StringVar()
    editor = ttk.Frame(content)
    editor.grid(row=4, column=0, columnspan=3, sticky=tk.EW, pady=(8, 0))
    editor.columnconfigure(0, weight=1)
    entry = ttk.Entry(editor, textvariable=entry_value)
    entry.grid(row=0, column=0, sticky=tk.EW, padx=(0, 8))

    def patterns():
        return [table.set(item, "pattern") for item in table.get_children()]

    def clear_counts(*_):
        for item in table.get_children():
            table.set(item, "images", "—")
            table.set(item, "texts", "—")

    def update_pattern(replace_selected=False):
        selected = table.selection()
        if replace_selected and len(selected) != 1:
            messagebox.showerror("Шаблоны", "Выберите одну строку для изменения.", parent=window)
            return
        values = patterns()
        try:
            value = validate_patterns([entry_value.get()])[0]
            if replace_selected:
                values[list(table.get_children()).index(selected[0])] = value
            else:
                values.append(value)
            validate_patterns(values)
        except ValueError as exc:
            messagebox.showerror("Шаблоны", str(exc), parent=window)
            return
        if replace_selected:
            table.set(selected[0], "pattern", value)
        else:
            table.insert("", tk.END, values=(value, "—", "—"))
        clear_counts()
        entry_value.set("")
        entry.focus_set()

    def remove_patterns():
        for item in table.selection():
            table.delete(item)
        entry_value.set("")
        clear_counts()

    def select_pattern(_event):
        selected = table.selection()
        if len(selected) == 1:
            entry_value.set(table.set(selected[0], "pattern"))

    table.bind("<<TreeviewSelect>>", select_pattern)
    ttk.Button(editor, text="Добавить", command=update_pattern).grid(row=0, column=1, padx=3)
    ttk.Button(editor, text="Изменить", command=lambda: update_pattern(True)).grid(row=0, column=2, padx=3)
    ttk.Button(editor, text="Удалить", command=remove_patterns).grid(row=0, column=3, padx=3)
    for key in ("images_folder", "texts_folder"):
        fields[key].trace_add("write", clear_counts)
    explanation = (
        "Регистр, лишние пробелы и знак _ не влияют на поиск. Вложенные папки учитываются.\n"
        "Картинки: JPG/PNG. Тексты: TXT/DOCX. Из подходящих картинок и текстов выбираются случайные.\n"
        "Без совпадения или при неоднозначном имени файл пропускается. Длинный текст отправляется частями."
    )
    if not config.uses_patterns:
        explanation += "\nСтарый режим работает до сохранения: для перехода укажите обе папки и добавьте шаблоны."
    ttk.Label(content, text=explanation, wraplength=740).grid(row=5, column=0, columnspan=3, sticky=tk.W, pady=(10, 0))

    for row, (key, label, value) in enumerate([
        ("time", "Время (ЧЧ:ММ)", config.time),
        ("timezone", "Часовой пояс", config.timezone),
        ("chat_id", "ID чата", str(config.chat_id or "")),
        ("message_thread_id", "ID темы (необязательно)", str(config.message_thread_id or "")),
    ]):
        ttk.Label(schedule, text=label).grid(row=row, column=0, sticky=tk.W, pady=8, padx=(0, 12))
        fields[key] = tk.StringVar(value=value)
        widget = ttk.Combobox(schedule, textvariable=fields[key], values=("Europe/Kyiv", "Europe/Budapest", "UTC")) if key == "timezone" else ttk.Entry(schedule, textvariable=fields[key])
        widget.grid(row=row, column=1, sticky=tk.EW)
    ttk.Label(schedule, text=(
        "Для выбора чата и темы отправьте /daily_card_here в нужной теме Telegram.\n\n"
        "Публикация ежедневная. Часовой пояс учитывает летнее время.\n"
        "Компьютер и бот должны работать. Если время уже прошло, сегодняшняя карта\n"
        "будет отправлена после включения. Повторная публикация за день блокируется."
    ), wraplength=700).grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=14)

    def inspect_folders():
        checked_patterns = validate_patterns(patterns())
        if not checked_patterns:
            raise ValueError("Добавьте хотя бы один шаблон, например «8 пентаклей».")
        folders = []
        for key, label in [("images_folder", "картинок"), ("texts_folder", "текстов")]:
            path = fields[key].get().strip()
            if not path or not Path(path).is_dir():
                raise ValueError(f"Выберите существующую папку {label}.")
            folders.append(Path(path))
        image_files = scan_card_folder(folders[0])
        text_files = scan_card_folder(folders[1])
        catalog = build_match_catalog(image_files.images, text_files.texts, checked_patterns)
        counts = {pattern: [0, 0] for pattern in checked_patterns}
        for index, paths in enumerate([image_files.images, text_files.texts]):
            for path in paths:
                try:
                    pattern = match_pattern(path.stem, checked_patterns)
                except ValueError:
                    continue
                if pattern:
                    counts[pattern][index] += 1
        for item, pattern in zip(table.get_children(), checked_patterns):
            table.item(item, values=(pattern, *counts[pattern]))
        details = f"Картинок: {len(image_files.images)}. Текстов: {len(text_files.texts)}.\nГотовых к публикации картинок: {len(catalog.pairs)}."
        for label, paths in [
            ("Картинки без шаблона", catalog.unmatched_images),
            ("Картинки с несколькими шаблонами", catalog.ambiguous_images),
            ("Картинки без подходящего текста", catalog.missing_text_images),
            ("Тексты без шаблона", catalog.unmatched_texts),
            ("Тексты с несколькими шаблонами", catalog.ambiguous_texts),
            ("Старые .doc (сохраните как .docx)", text_files.unsupported_texts),
        ]:
            if paths:
                details += f"\n\n{label}: {len(paths)}\n" + "\n".join(p.name for p in paths[:3])
                if len(paths) > 3:
                    details += "\n…"
        if not catalog.pairs:
            raise ValueError(details + "\n\nНет подходящих пар. Проверьте имена файлов и шаблоны.")
        errors = []
        for pair in catalog.pairs:
            try:
                with DailyCardService._open_photo(pair.image):
                    pass
            except (OSError, ValueError) as exc:
                errors.append(f"{pair.image.name}: {exc}")
        for path in sorted({p for pair in catalog.pairs for p in pair.texts}):
            try:
                split_telegram_text(read_card_text(path))
            except (OSError, ValueError) as exc:
                errors.append(f"{path.name}: {exc}")
        if errors:
            raise ValueError(f"Ошибок чтения: {len(errors)}\n" + "\n".join(errors[:5]))
        return details

    def check_folders():
        try:
            details = inspect_folders()
            messagebox.showinfo("Проверка папок", details + "\n\nВ Telegram ничего не отправлено.", parent=window)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Проверка папок", str(exc), parent=window)

    def save():
        values = {key: value.get().strip() for key, value in fields.items()}
        values.update(enabled=enabled.get(), patterns=patterns())
        try:
            validated = parse_daily_card(values)
            if validated.enabled:
                inspect_folders()
            _save_with_bot_stopped(panel, lambda: save_daily_card(values))
        except (OSError, ValueError) as exc:
            messagebox.showerror("Карта дня", str(exc), parent=window)
            return
        logging.getLogger(__name__).info("Daily card settings changed in local panel")
        window.destroy()

    buttons = ttk.Frame(frame)
    buttons.pack(fill=tk.X, pady=(10, 0))
    ttk.Button(buttons, text="Проверить папки", command=check_folders).pack(side=tk.LEFT)
    ttk.Button(buttons, text="Сохранить", command=save).pack(side=tk.RIGHT)
