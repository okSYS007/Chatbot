from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from app.config import AppConfig, load_config, save_admin_user_ids, save_reputation_reactions
from app.setup_wizard import run_setup_wizard
from app.storage import JsonStorage


class AdminPanel:
    def __init__(self, root: tk.Tk, config: AppConfig):
        self.root = root
        self.config = config
        self.bot_process: subprocess.Popen | None = None

        self.root.title("Lenormand Group Bot")
        self.root.geometry("860x520")
        self.root.minsize(760, 420)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.status_var = tk.StringVar(value="Бот остановлен")

        self._build_layout()
        self.refresh_users()
        self.root.after(400, self._launch_bot_process)

    def _build_layout(self) -> None:
        toolbar = ttk.Frame(self.root, padding=10)
        toolbar.pack(fill=tk.X)

        ttk.Button(toolbar, text="Обновить", command=self.refresh_users).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Начислить репутацию", command=self.add_reputation).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(toolbar, text="Списать кристаллы", command=self.spend_crystals).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(toolbar, text="Реакции", command=self.edit_reactions).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(toolbar, text="Добавить админа", command=self.add_admin).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(toolbar, text="Перезапустить бота", command=self.relaunch_bot).pack(side=tk.LEFT, padx=(18, 0))

        ttk.Label(toolbar, textvariable=self.status_var).pack(side=tk.RIGHT)

        columns = ("user_id", "name", "username", "reputation", "messages", "subscription")
        self.users = ttk.Treeview(self.root, columns=columns, show="headings")
        self.users.heading("user_id", text="User ID")
        self.users.heading("name", text="Имя")
        self.users.heading("username", text="Username")
        self.users.heading("reputation", text="Репутация")
        self.users.heading("messages", text="Сообщения")
        self.users.heading("subscription", text="Подписка")

        self.users.column("user_id", width=120, anchor=tk.W)
        self.users.column("name", width=220, anchor=tk.W)
        self.users.column("username", width=150, anchor=tk.W)
        self.users.column("reputation", width=100, anchor=tk.CENTER)
        self.users.column("messages", width=90, anchor=tk.CENTER)
        self.users.column("subscription", width=100, anchor=tk.CENTER)

        self.users.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        footer = ttk.Label(
            self.root,
            text="В списке только пользователи, которых бот уже видел. Закрытие окна останавливает бота.",
            padding=(10, 0, 10, 10),
        )
        footer.pack(fill=tk.X)

    def storage(self) -> JsonStorage:
        return JsonStorage(self.config.storage.path)

    def admin_id(self) -> int:
        return next(iter(self.config.admins.user_ids), 0)

    def selected_user_id(self) -> int | None:
        selected = self.users.selection()
        if not selected:
            return None
        values = self.users.item(selected[0], "values")
        return int(values[0]) if values else None

    def ask_user_id(self) -> int | None:
        selected = self.selected_user_id()
        if selected:
            return selected
        return simpledialog.askinteger("User ID", "Введите Telegram user_id:", parent=self.root)

    def refresh_users(self) -> None:
        for row in self.users.get_children():
            self.users.delete(row)

        state = self.storage().snapshot()
        users = list(state.get("users", {}).values())
        users.sort(key=lambda item: int(item.get("reputation") or 0), reverse=True)

        for user in users:
            user_id = int(user.get("user_id") or 0)
            username = user.get("username") or ""
            if username and not username.startswith("@"):
                username = f"@{username}"
            self.users.insert(
                "",
                tk.END,
                values=(
                    user_id,
                    user.get("display_name") or user_id,
                    username,
                    int(user.get("reputation") or 0),
                    int(user.get("message_count") or 0),
                    "да" if user.get("subscription_active") else "нет",
                ),
            )

    def bot_command(self) -> list[str]:
        if getattr(sys, "frozen", False):
            return [sys.executable, "--bot-only"]
        return [sys.executable, str(Path("main.py")), "--bot-only"]

    def _launch_bot_process(self) -> None:
        if self.bot_process and self.bot_process.poll() is None:
            self.status_var.set("Бот работает")
            return

        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.bot_process = subprocess.Popen(
            self.bot_command(),
            cwd=Path.cwd(),
            creationflags=flags,
        )
        self.status_var.set("Бот работает")

    def _terminate_bot_process(self) -> None:
        if not self.bot_process or self.bot_process.poll() is not None:
            self.status_var.set("Бот остановлен")
            return

        self.bot_process.terminate()
        try:
            self.bot_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.bot_process.kill()
            self.bot_process.wait(timeout=5)
        self.status_var.set("Бот остановлен")

    def relaunch_bot(self) -> None:
        self._terminate_bot_process()
        self._launch_bot_process()

    def add_reputation(self) -> None:
        user_id = self.ask_user_id()
        if not user_id:
            return
        amount = simpledialog.askinteger("Начислить репутацию", "Сколько очков начислить:", parent=self.root, minvalue=1)
        if not amount:
            return
        reason = simpledialog.askstring("Причина", "Причина:", parent=self.root) or "manual_admin_add"

        ok, balance = self.storage().add_reputation(user_id, amount, self.admin_id(), reason)
        if not ok:
            messagebox.showerror("Начислить репутацию", f"Не удалось начислить репутацию. Баланс: {balance}")
            return
        self.refresh_users()
        messagebox.showinfo("Начислить репутацию", f"Начислено: {amount}. Новый баланс: {balance}")

    def spend_crystals(self) -> None:
        user_id = self.ask_user_id()
        if not user_id:
            return
        amount = simpledialog.askinteger("Списать кристаллы", "Сколько очков списать:", parent=self.root, minvalue=1)
        if not amount:
            return
        reason = simpledialog.askstring("Причина", "Причина:", parent=self.root) or "crystal_exchange"

        ok, balance = self.storage().spend_reputation(user_id, amount, self.admin_id(), reason)
        if not ok:
            messagebox.showerror("Списать кристаллы", f"Не удалось списать очки. Баланс: {balance}")
            return
        self.refresh_users()
        messagebox.showinfo("Списать кристаллы", f"Списано: {amount}. Новый баланс: {balance}")

    def add_admin(self) -> None:
        user_id = self.ask_user_id()
        if not user_id:
            return

        fresh_config = load_config()
        admins = set(fresh_config.admins.user_ids)
        if user_id in admins:
            messagebox.showinfo("Админы", "Этот user_id уже есть в админском списке.")
            return

        admins.add(user_id)
        save_admin_user_ids(admins)
        self.config = load_config()
        self.relaunch_bot()
        messagebox.showinfo(
            "Админы",
            f"User ID {user_id} добавлен в админский список. Бот перезапущен.",
        )

    def edit_reactions(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("Репутационные реакции")
        window.geometry("320x360")
        window.transient(self.root)
        window.grab_set()

        frame = ttk.Frame(window, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Белый список реакций").pack(anchor=tk.W)
        reactions = tk.Listbox(frame, height=8)
        reactions.pack(fill=tk.BOTH, expand=True, pady=(6, 8))
        for reaction in self.config.reputation.positive_reactions:
            reactions.insert(tk.END, reaction)

        entry = ttk.Entry(frame)
        entry.pack(fill=tk.X)

        buttons = ttk.Frame(frame)
        buttons.pack(fill=tk.X, pady=(8, 0))

        def add_reaction() -> None:
            reaction = entry.get().strip()
            if not reaction:
                return
            current = set(reactions.get(0, tk.END))
            if reaction not in current:
                reactions.insert(tk.END, reaction)
            entry.delete(0, tk.END)

        def remove_reaction() -> None:
            for index in reversed(reactions.curselection()):
                reactions.delete(index)

        def save_reactions() -> None:
            values = [str(value).strip() for value in reactions.get(0, tk.END) if str(value).strip()]
            if not values:
                messagebox.showerror("Реакции", "В списке должна быть хотя бы одна реакция.", parent=window)
                return
            save_reputation_reactions(values)
            self.config = load_config()
            window.destroy()
            self.relaunch_bot()
            messagebox.showinfo("Реакции", "Список реакций сохранен, бот перезапущен.")

        ttk.Button(buttons, text="Добавить", command=add_reaction).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Удалить", command=remove_reaction).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(buttons, text="Сохранить", command=save_reactions).pack(side=tk.RIGHT)

    def close(self) -> None:
        self._terminate_bot_process()
        self.root.destroy()


def run_admin_panel() -> None:
    try:
        config = load_config()
    except Exception:
        run_setup_wizard()
        config = load_config()

    config.storage.path.parent.mkdir(parents=True, exist_ok=True)
    config.logging.path.parent.mkdir(parents=True, exist_ok=True)

    root = tk.Tk()
    AdminPanel(root, config)
    root.mainloop()
