



"""
Memorize - Complete Offline Flashcard Learning System
Multiple Choice Mode - Works completely offline
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import random
from datetime import datetime, timedelta
import os
import csv
import sys

try:
    import openpyxl

    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

DATA_VERSION = "8.0"

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_DIR = os.path.join(BASE_DIR, "memorize_data")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)


# ===== DATA MODELS =====

class FlashCard:
    def __init__(self, front, back, hint=""):
        self.front = front
        self.back = back
        self.hint = hint
        self.level = 0
        self.reps = 0
        self.lapses = 0
        self.ease_factor = 2.5
        self.next_review = datetime.now().isoformat()
        self.reviews = 0
        self.correct_streak = 0
        self.ignored = False

    @property
    def status(self):
        if self.ignored:
            return "ignored"
        if self.level == 0:
            return "new"
        if self.level < 4:
            return "learning"
        if self.level < 7:
            return "review"
        return "mastered"

    def is_due(self):
        if self.ignored:
            return False
        if self.level == 0:
            return True
        return datetime.fromisoformat(self.next_review) <= datetime.now()

    def reset(self):
        self.level = 0
        self.reps = 0
        self.lapses = 0
        self.ease_factor = 2.5
        self.next_review = datetime.now().isoformat()
        self.reviews = 0
        self.correct_streak = 0
        self.ignored = False

    def already_known(self):
        self.level = 3
        intervals = [0, 0.167, 0.5, 1, 3, 7, 30, 90, 180, 365]
        self.next_review = (datetime.now() + timedelta(days=intervals[self.level])).isoformat()

    def to_dict(self):
        return {
            "front": self.front, "back": self.back, "hint": self.hint,
            "level": self.level, "reps": self.reps, "lapses": self.lapses,
            "ease_factor": self.ease_factor, "next_review": self.next_review,
            "reviews": self.reviews, "correct_streak": self.correct_streak,
            "ignored": self.ignored
        }

    @classmethod
    def from_dict(cls, d):
        card = cls(d["front"], d["back"], d.get("hint", ""))
        card.level = d.get("level", 0)
        card.reps = d.get("reps", 0)
        card.lapses = d.get("lapses", 0)
        card.ease_factor = d.get("ease_factor", 2.5)
        card.next_review = d.get("next_review", datetime.now().isoformat())
        card.reviews = d.get("reviews", 0)
        card.correct_streak = d.get("correct_streak", 0)
        card.ignored = d.get("ignored", False)
        return card


class Deck:
    def __init__(self, name):
        self.name = name
        self.cards = []

    def add_card(self, card):
        self.cards.append(card)

    def get_new(self):
        return [c for c in self.cards if c.status == "new" and not c.ignored]

    def get_learning(self):
        """Get learning cards that are DUE for review"""
        return [c for c in self.cards if c.status == "learning" and c.is_due() and not c.ignored]

    def get_all_learning(self):
        """Get ALL learning cards (for stats count only)"""
        return [c for c in self.cards if c.status == "learning" and not c.ignored]

    def get_due(self):
        return [c for c in self.cards if
                c.status in ("learning", "review", "mastered") and c.is_due() and not c.ignored]

    def stats(self):
        return {
            "new": len(self.get_new()),
            "learning": len(self.get_all_learning()),
            "due": len(self.get_due()),
            "mastered": len([c for c in self.cards if c.status == "mastered" and not c.ignored]),
            "ignored": sum(1 for c in self.cards if c.ignored),
            "total": len(self.cards)
        }

    def reset_all(self):
        for c in self.cards:
            c.reset()

    def to_dict(self):
        return {"name": self.name, "cards": [c.to_dict() for c in self.cards]}

    @classmethod
    def from_dict(cls, d):
        deck = cls(d["name"])
        for cd in d.get("cards", []):
            deck.cards.append(FlashCard.from_dict(cd))
        return deck


class Course:
    def __init__(self, name):
        self.name = name
        self.decks = []
        self.words_per_session = 10
        self.review_words_per_session = 10

    def add_deck(self, deck):
        self.decks.append(deck)

    def total_cards(self):
        return sum(len(d.cards) for d in self.decks)

    def stats(self):
        result = {"new": 0, "learning": 0, "due": 0, "mastered": 0, "ignored": 0, "total": 0}
        for d in self.decks:
            s = d.stats()
            for k in result:
                result[k] += s[k]
        return result

    def reset_all(self):
        for d in self.decks:
            d.reset_all()

    def to_dict(self):
        return {
            "name": self.name,
            "words_per_session": self.words_per_session,
            "review_words_per_session": self.review_words_per_session,
            "decks": [d.to_dict() for d in self.decks]
        }

    @classmethod
    def from_dict(cls, d):
        course = cls(d["name"])
        course.words_per_session = d.get("words_per_session", 10)
        course.review_words_per_session = d.get("review_words_per_session", 10)
        for dd in d.get("decks", []):
            course.decks.append(Deck.from_dict(dd))
        return course


# ===== DATA MANAGER =====

class DataManager:
    def __init__(self):
        self.file = os.path.join(DATA_DIR, "courses.json")

    def load(self):
        if not os.path.exists(self.file):
            return []
        with open(self.file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return [Course.from_dict(c) for c in data.get("courses", [])]

    def save(self, courses):
        with open(self.file, 'w', encoding='utf-8') as f:
            json.dump({"version": DATA_VERSION, "courses": [c.to_dict() for c in courses]},
                      f, indent=2, ensure_ascii=False)

    def backup(self):
        import shutil
        if os.path.exists(self.file):
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.copy2(self.file, os.path.join(BACKUP_DIR, f"backup_{ts}.json"))

    def import_cards(self, filename):
        cards = []
        try:
            if filename.lower().endswith(('.xlsx', '.xls')):
                if not HAS_OPENPYXL:
                    return None, "Install openpyxl: pip install openpyxl"
                wb = openpyxl.load_workbook(filename, read_only=True)
                ws = wb.active
                rows = list(ws.iter_rows(values_only=True))
                wb.close()
                start = 1 if rows and 'ront' in str(rows[0][0]).lower() else 0
                for row in rows[start:]:
                    if len(row) >= 2 and row[0] and row[1]:
                        cards.append(FlashCard(str(row[0]).strip(), str(row[1]).strip(),
                                               str(row[2]).strip() if len(row) > 2 and row[2] else ""))
            else:
                with open(filename, 'r', encoding='utf-8') as f:
                    delim = '\t' if '\t' in f.read(1024) else ','
                    f.seek(0)
                    reader = csv.reader(f, delimiter=delim)
                    rows = list(reader)
                    start = 1 if rows and 'ront' in rows[0][0].lower() else 0
                    for row in rows[start:]:
                        if len(row) >= 2 and row[0].strip() and row[1].strip():
                            cards.append(FlashCard(row[0].strip(), row[1].strip(),
                                                   row[2].strip() if len(row) > 2 else ""))
            return cards, None
        except Exception as e:
            return None, str(e)


# ===== MAIN APPLICATION =====

class MemorizeApp:
    BG = "#0f172a"
    CARD_BG = "#1e293b"
    ACCENT = "#3b82f6"
    GREEN = "#22c55e"
    RED = "#ef4444"
    ORANGE = "#f59e0b"
    PURPLE = "#8b5cf6"
    TEXT = "#f8fafc"
    MUTED = "#94a3b8"
    BORDER = "#334155"

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Memorize - Flashcard Learning")
        self.root.geometry("1000x680")
        self.root.configure(bg=self.BG)

        self.dm = DataManager()
        self.courses = self.dm.load()
        self.current_course = None
        self.study_cards = []
        self.current_idx = 0
        self.correct_count = 0

        self._setup_ui()
        self._show_courses()

    def _setup_ui(self):
        header = tk.Frame(self.root, bg=self.BG, height=65)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        tk.Label(header, text="📚 Memorize", font=('Segoe UI', 22, 'bold'),
                 bg=self.BG, fg=self.ACCENT).pack(side=tk.LEFT, padx=30, pady=12)

        self.header_right = tk.Frame(header, bg=self.BG)
        self.header_right.pack(side=tk.RIGHT, padx=30, pady=12)

        self.content = tk.Frame(self.root, bg=self.BG)
        self.content.pack(fill=tk.BOTH, expand=True)

    def _clear(self):
        for w in self.content.winfo_children():
            w.destroy()

    def _update_header(self):
        for w in self.header_right.winfo_children():
            w.destroy()
        total = sum(c.total_cards() for c in self.courses)
        tk.Label(self.header_right, text=f"{len(self.courses)} courses · {total} words",
                 font=('Segoe UI', 10), bg=self.BG, fg=self.MUTED).pack()

    # ===== COURSES SCREEN =====

    def _show_courses(self):

        self._clear()
        self._update_header()
        self.current_course = None

        title_frame = tk.Frame(self.content, bg=self.BG)
        title_frame.pack(fill=tk.X, padx=40, pady=(40, 20))

        tk.Label(title_frame, text="My Courses", font=('Segoe UI', 28, 'bold'),
                 bg=self.BG, fg=self.TEXT).pack(side=tk.LEFT)

        tk.Button(title_frame, text="+ New Course", command=self._create_course_dialog,
                  bg=self.ACCENT, fg='white', font=('Segoe UI', 11, 'bold'),
                  padx=20, pady=10, cursor='hand2', relief='flat', borderwidth=0).pack(side=tk.RIGHT)

        if not self.courses:
            empty = tk.Frame(self.content, bg=self.BG)
            empty.pack(expand=True)
            tk.Label(empty, text="📚", font=('Segoe UI', 60), bg=self.BG).pack()
            tk.Label(empty, text="No courses yet", font=('Segoe UI', 20),
                     bg=self.BG, fg=self.MUTED).pack(pady=10)
            return

        # Scrollable canvas for courses
        canvas = tk.Canvas(self.content, bg=self.BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.content, orient="vertical", command=canvas.yview)
        courses_frame = tk.Frame(canvas, bg=self.BG)

        courses_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=courses_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        def on_conf(event):
            canvas.itemconfig("all", width=event.width)

        canvas.bind("<Configure>", on_conf)

        canvas.pack(side="left", fill="both", expand=True, padx=30)
        scrollbar.pack(side="right", fill="y", padx=(0, 10))

        # Mouse wheel scrolling
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", on_mousewheel)

        for course in self.courses:
            s = course.stats()

            card = tk.Frame(courses_frame, bg=self.CARD_BG, padx=25, pady=20)
            card.pack(fill=tk.X, pady=8)

            row1 = tk.Frame(card, bg=self.CARD_BG)
            row1.pack(fill=tk.X)

            tk.Label(row1, text=course.name, font=('Segoe UI', 18, 'bold'),
                     bg=self.CARD_BG, fg=self.TEXT).pack(side=tk.LEFT)

            btn_group = tk.Frame(row1, bg=self.CARD_BG)
            btn_group.pack(side=tk.RIGHT)

            tk.Button(btn_group, text="⚙️", font=('Segoe UI', 14),
                      command=lambda c=course: self._settings_dialog(c),
                      bg=self.CARD_BG, fg=self.MUTED, cursor='hand2',
                      relief='flat', borderwidth=0).pack(side=tk.LEFT, padx=2)

            tk.Button(btn_group, text="🔄", font=('Segoe UI', 14),
                      command=lambda c=course: self._restart_course(c),
                      bg=self.CARD_BG, fg=self.MUTED, cursor='hand2',
                      relief='flat', borderwidth=0).pack(side=tk.LEFT, padx=2)

            tk.Button(btn_group, text="🗑️", font=('Segoe UI', 14),
                      command=lambda c=course: self._delete_course(c),
                      bg=self.CARD_BG, fg=self.MUTED, cursor='hand2',
                      relief='flat', borderwidth=0).pack(side=tk.LEFT, padx=2)

            row2 = tk.Frame(card, bg=self.CARD_BG)
            row2.pack(fill=tk.X, pady=(12, 8))

            stat_items = [
                (f"🆕 {s['new']} new", self.ACCENT),
                (f"📖 {s['learning']} learned", self.ORANGE),
                (f"🔄 {s['due']} review", self.RED),
                (f"⭐ {s['mastered']} mastered", self.GREEN),
            ]
            for text, color in stat_items:
                tk.Label(row2, text=text, font=('Segoe UI', 10),
                         bg=self.CARD_BG, fg=color).pack(side=tk.LEFT, padx=(0, 20))

            row3 = tk.Frame(card, bg=self.CARD_BG)
            row3.pack(fill=tk.X, pady=(8, 0))

            if s['new'] > 0:
                tk.Button(row3, text=f"📖 Learn New ({s['new']})",
                          command=lambda c=course: self._start_session(c, "new"),
                          bg=self.ACCENT, fg='white', font=('Segoe UI', 10, 'bold'),
                          padx=18, pady=8, cursor='hand2', relief='flat', borderwidth=0
                          ).pack(side=tk.LEFT, padx=(0, 8))

            tk.Button(row3, text=f"🔄 Review ({s['due']})",
                      command=lambda c=course: self._start_session(c, "due"),
                      bg=self.RED, fg='white', font=('Segoe UI', 10, 'bold'),
                      padx=18, pady=8, cursor='hand2', relief='flat', borderwidth=0
                      ).pack(side=tk.LEFT, padx=(0, 8))

            if s['learning'] > 0:
                tk.Label(row3, text=f"📖 {s['learning']} in progress",
                         font=('Segoe UI', 10), bg=self.CARD_BG, fg=self.ORANGE
                         ).pack(side=tk.LEFT, padx=(0, 8))

            tk.Button(row3, text="📂 Manage",
                      command=lambda c=course: self._manage_course(c),
                      bg=self.CARD_BG, fg=self.TEXT, font=('Segoe UI', 10),
                      padx=18, pady=8, cursor='hand2', relief='flat', borderwidth=0
                      ).pack(side=tk.RIGHT)

    # ===== CREATE COURSE =====

    def _create_course_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Create New Course")
        dialog.geometry("800x650")
        dialog.configure(bg=self.CARD_BG)
        dialog.transient(self.root)
        dialog.grab_set()

        x = self.root.winfo_rootx() + (self.root.winfo_width() - 800) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - 650) // 2
        dialog.geometry(f"+{x}+{y}")

        # Course name
        tk.Label(dialog, text="Course Name", font=('Segoe UI', 13, 'bold'),
                 bg=self.CARD_BG, fg=self.TEXT).pack(anchor='w', padx=20, pady=(15, 5))
        name_entry = tk.Entry(dialog, font=('Segoe UI', 14), bg=self.BG, fg=self.TEXT,
                              insertbackground=self.TEXT, relief='flat')
        name_entry.pack(fill=tk.X, padx=20, pady=5, ipady=5)
        name_entry.focus()

        # Table section
        tk.Label(dialog, text="📝 Add Words", font=('Segoe UI', 12, 'bold'),
                 bg=self.CARD_BG, fg=self.TEXT).pack(anchor='w', padx=20, pady=(15, 5))

        tk.Label(dialog, text="Fill in the table below. Click '+ Add Row' for more rows.",
                 font=('Segoe UI', 9), bg=self.CARD_BG, fg=self.MUTED).pack(anchor='w', padx=20, pady=(0, 5))

        # Column headers
        col_frame = tk.Frame(dialog, bg=self.CARD_BG)
        col_frame.pack(fill=tk.X, padx=20, pady=(5, 0))

        tk.Label(col_frame, text="#", font=('Segoe UI', 9, 'bold'), bg=self.CARD_BG,
                 fg=self.MUTED, width=4).pack(side=tk.LEFT)
        tk.Label(col_frame, text="Front (Question/Word)", font=('Segoe UI', 9, 'bold'),
                 bg=self.CARD_BG, fg=self.ACCENT, width=28, anchor='w').pack(side=tk.LEFT, padx=(5, 5))
        tk.Label(col_frame, text="Back (Answer/Translation)", font=('Segoe UI', 9, 'bold'),
                 bg=self.CARD_BG, fg=self.GREEN, width=28, anchor='w').pack(side=tk.LEFT, padx=(0, 5))
        tk.Label(col_frame, text="Hint (optional)", font=('Segoe UI', 9, 'bold'),
                 bg=self.CARD_BG, fg=self.MUTED, width=15, anchor='w').pack(side=tk.LEFT)

        # Scrollable table
        canvas = tk.Canvas(dialog, bg=self.CARD_BG, highlightthickness=0, height=250)
        scrollbar = ttk.Scrollbar(dialog, orient="vertical", command=canvas.yview)
        rows_frame = tk.Frame(canvas, bg=self.CARD_BG)

        rows_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=rows_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill=tk.BOTH, expand=True, padx=(20, 0), pady=10)
        scrollbar.pack(side="right", fill=tk.Y, padx=(0, 20), pady=10)

        rows = []

        def add_row(front="", back="", hint=""):
            row_num = len(rows) + 1

            row_frame = tk.Frame(rows_frame, bg=self.CARD_BG)
            row_frame.pack(fill=tk.X, pady=1)

            tk.Label(row_frame, text=str(row_num), font=('Segoe UI', 10),
                     bg=self.CARD_BG, fg=self.MUTED, width=4).pack(side=tk.LEFT)

            front_entry = tk.Entry(row_frame, font=('Segoe UI', 10), bg=self.BG, fg=self.TEXT,
                                   insertbackground=self.TEXT, relief='flat', width=28)
            front_entry.pack(side=tk.LEFT, padx=(5, 5))
            if front:
                front_entry.insert(0, front)

            back_entry = tk.Entry(row_frame, font=('Segoe UI', 10), bg=self.BG, fg=self.TEXT,
                                  insertbackground=self.TEXT, relief='flat', width=28)
            back_entry.pack(side=tk.LEFT, padx=(0, 5))
            if back:
                back_entry.insert(0, back)

            hint_entry = tk.Entry(row_frame, font=('Segoe UI', 10), bg=self.BG, fg=self.TEXT,
                                  insertbackground=self.TEXT, relief='flat', width=15)
            hint_entry.pack(side=tk.LEFT)
            if hint:
                hint_entry.insert(0, hint)

            del_btn = tk.Button(row_frame, text="✕", font=('Segoe UI', 9),
                                bg=self.CARD_BG, fg=self.RED, cursor='hand2',
                                relief='flat', borderwidth=0)
            del_btn.pack(side=tk.RIGHT, padx=(5, 0))

            row_data = {
                "frame": row_frame,
                "front": front_entry,
                "back": back_entry,
                "hint": hint_entry,
                "del_btn": del_btn
            }
            rows.append(row_data)

            del_btn.config(command=lambda r=row_data: delete_row(r))
            update_row_numbers()
            canvas.yview_moveto(1.0)
            front_entry.focus_set()

        def delete_row(row_data):
            row_data["frame"].destroy()
            rows.remove(row_data)
            update_row_numbers()

        def update_row_numbers():
            for i, row in enumerate(rows):
                for widget in row["frame"].winfo_children():
                    if isinstance(widget, tk.Label) and widget.cget("width") == 4:
                        widget.config(text=str(i + 1))

        # Add initial rows
        for _ in range(8):
            add_row()

        # Add Row button
        add_btn_frame = tk.Frame(dialog, bg=self.CARD_BG)
        add_btn_frame.pack(fill=tk.X, padx=20, pady=5)

        tk.Button(add_btn_frame, text="+ Add Row", command=add_row,
                  bg=self.ACCENT, fg='white', font=('Segoe UI', 10, 'bold'),
                  padx=15, pady=6, cursor='hand2', relief='flat', borderwidth=0
                  ).pack(side=tk.LEFT)

        tk.Label(add_btn_frame, text="(or press Tab in last Hint field)",
                 font=('Segoe UI', 8), bg=self.CARD_BG, fg=self.MUTED).pack(side=tk.LEFT, padx=10)

        # Count label
        count_label = tk.Label(add_btn_frame, text="Words: 0", font=('Segoe UI', 10, 'bold'),
                               bg=self.CARD_BG, fg=self.ACCENT)
        count_label.pack(side=tk.RIGHT)

        def update_count():
            count = sum(1 for r in rows if r["front"].get().strip() and r["back"].get().strip())
            count_label.config(text=f"Words: {count}")

        # OR divider
        sep_frame = tk.Frame(dialog, bg=self.CARD_BG)
        sep_frame.pack(fill=tk.X, padx=20, pady=5)
        tk.Frame(sep_frame, bg=self.MUTED, height=1).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(sep_frame, text="  OR Import File  ", font=('Segoe UI', 10),
                 bg=self.CARD_BG, fg=self.MUTED).pack(side=tk.LEFT)
        tk.Frame(sep_frame, bg=self.MUTED, height=1).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Import section
        import_frame = tk.Frame(dialog, bg=self.CARD_BG)
        import_frame.pack(fill=tk.X, padx=20, pady=5)

        file_var = tk.StringVar()
        file_label = tk.Label(import_frame, text="No file selected",
                              font=('Segoe UI', 10), bg=self.BG, fg=self.MUTED,
                              anchor='w', padx=10, pady=6)
        file_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        def browse_file():
            fn = filedialog.askopenfilename(filetypes=[("CSV/Excel", "*.csv *.xlsx *.xls")])
            if fn:
                file_var.set(fn)
                file_label.config(text=f"✅ {os.path.basename(fn)}", fg=self.GREEN)
                cards, _ = self.dm.import_cards(fn)
                if cards:
                    for card in cards:
                        add_row(card.front, card.back, card.hint)
                    update_count()

        tk.Button(import_frame, text="Browse...", command=browse_file,
                  bg=self.ACCENT, fg='white', font=('Segoe UI', 10),
                  padx=12, pady=6, cursor='hand2', relief='flat', borderwidth=0
                  ).pack(side=tk.RIGHT)

        # Create button
        bottom_frame = tk.Frame(dialog, bg=self.CARD_BG)
        bottom_frame.pack(fill=tk.X, padx=20, pady=15)

        def create():
            name = name_entry.get().strip()
            if not name:
                messagebox.showwarning("Error", "Enter a course name!", parent=dialog)
                return

            all_cards = []
            for row in rows:
                front = row["front"].get().strip()
                back = row["back"].get().strip()
                if front and back:
                    hint = row["hint"].get().strip()
                    all_cards.append(FlashCard(front, back, hint))

            if not all_cards:
                messagebox.showwarning("Error", "Add at least one word!", parent=dialog)
                return

            course = Course(name)
            deck = Deck("Main")
            for c in all_cards:
                deck.add_card(c)
            course.add_deck(deck)

            self.courses.append(course)
            self.dm.backup()
            self.dm.save(self.courses)
            self._update_header()
            dialog.destroy()
            self._show_courses()

        tk.Button(bottom_frame, text="✅ Create Course", command=create,
                  bg=self.GREEN, fg='white', font=('Segoe UI', 13, 'bold'),
                  padx=30, pady=12, cursor='hand2', relief='flat').pack(side=tk.RIGHT, padx=5)

        tk.Button(bottom_frame, text="Cancel", command=dialog.destroy,
                  bg=self.CARD_BG, fg=self.MUTED, font=('Segoe UI', 11),
                  cursor='hand2', relief='flat', borderwidth=0).pack(side=tk.RIGHT, padx=5)

        # Tab in last hint adds new row
        def on_tab(event):
            if rows and event.widget == rows[-1]["hint"]:
                add_row()
                return "break"
        for row in rows:
            row["hint"].bind('<Tab>', on_tab)

    # ===== SETTINGS =====

    def _settings_dialog(self, course):
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Settings - {course.name}")
        dialog.geometry("450x350")
        dialog.configure(bg=self.CARD_BG)
        dialog.transient(self.root)
        dialog.grab_set()

        x = self.root.winfo_rootx() + (self.root.winfo_width() - 450) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - 350) // 2
        dialog.geometry(f"+{x}+{y}")

        tk.Label(dialog, text=f"⚙️ {course.name}", font=('Segoe UI', 18, 'bold'),
                 bg=self.CARD_BG, fg=self.TEXT).pack(pady=20)

        # Words per LEARNING session
        tk.Label(dialog, text="📖 New words per Learn session:", font=('Segoe UI', 12, 'bold'),
                 bg=self.CARD_BG, fg=self.ACCENT).pack(anchor='w', padx=40, pady=(15, 5))

        words_var = tk.IntVar(value=course.words_per_session)
        wf = tk.Frame(dialog, bg=self.CARD_BG)
        wf.pack(fill=tk.X, padx=40)
        for v in [5, 10, 20, 50]:
            tk.Radiobutton(wf, text=str(v), variable=words_var, value=v,
                           bg=self.CARD_BG, fg=self.TEXT, selectcolor=self.CARD_BG,
                           font=('Segoe UI', 11)).pack(side=tk.LEFT, padx=10)

        # Words per REVIEW session
        tk.Label(dialog, text="🔄 Words per Review session:", font=('Segoe UI', 12, 'bold'),
                 bg=self.CARD_BG, fg=self.RED).pack(anchor='w', padx=40, pady=(15, 5))

        review_var = tk.IntVar(value=course.review_words_per_session)
        rf = tk.Frame(dialog, bg=self.CARD_BG)
        rf.pack(fill=tk.X, padx=40)
        for v in [5, 10, 20, 50]:
            tk.Radiobutton(rf, text=str(v), variable=review_var, value=v,
                           bg=self.CARD_BG, fg=self.TEXT, selectcolor=self.CARD_BG,
                           font=('Segoe UI', 11)).pack(side=tk.LEFT, padx=10)

        def save():
            course.words_per_session = words_var.get()
            course.review_words_per_session = review_var.get()
            self.dm.save(self.courses)
            dialog.destroy()
            self._show_courses()

        tk.Button(dialog, text="💾 Save", command=save,
                  bg=self.GREEN, fg='white', font=('Segoe UI', 12, 'bold'),
                  padx=30, pady=10, cursor='hand2', relief='flat',
                  borderwidth=0).pack(pady=25)

    # ===== RESTART / DELETE =====

    def _restart_course(self, course):
        if messagebox.askyesno("Restart", f"Reset ALL progress in '{course.name}'?\n\n"
                                          "All words go back to New. This cannot be undone!"):
            course.reset_all()
            self.dm.save(self.courses)
            self._show_courses()

    def _delete_course(self, course):
        if messagebox.askyesno("Delete", f"Delete '{course.name}' permanently?"):
            self.courses.remove(course)
            self.dm.save(self.courses)
            self._update_header()
            self._show_courses()

    # ===== MANAGE COURSE =====

    def _manage_course(self, course):
        self._clear()
        self.current_course = course
        s = course.stats()

        header = tk.Frame(self.content, bg=self.BG)
        header.pack(fill=tk.X, padx=40, pady=(30, 15))

        tk.Label(header, text=f"📂 {course.name}", font=('Segoe UI', 22, 'bold'),
                 bg=self.BG, fg=self.TEXT).pack(side=tk.LEFT)

        # Button group on the right
        hdr_btns = tk.Frame(header, bg=self.BG)
        hdr_btns.pack(side=tk.RIGHT)

        tk.Button(hdr_btns, text="+ Add Words", command=lambda: self._add_words_dialog(course),
                  bg=self.GREEN, fg='white', font=('Segoe UI', 11, 'bold'),
                  padx=18, pady=8, cursor='hand2', relief='flat', borderwidth=0
                  ).pack(side=tk.LEFT, padx=5)

        tk.Button(hdr_btns, text="← Back to Courses",
                  command=self._show_courses,
                  bg=self.CARD_BG, fg=self.TEXT, font=('Segoe UI', 10),
                  padx=12, pady=5, cursor='hand2', relief='flat').pack(side=tk.LEFT)

        stats_card = tk.Frame(self.content, bg=self.CARD_BG, padx=20, pady=15)
        stats_card.pack(fill=tk.X, padx=40, pady=(0, 15))

        grid = tk.Frame(stats_card, bg=self.CARD_BG)
        grid.pack()

        items = [("New", s['new'], self.ACCENT), ("Learning", s['learning'], self.ORANGE),
                 ("Review", s['due'], self.RED), ("Mastered", s['mastered'], self.GREEN),
                 ("Ignored", s['ignored'], self.MUTED), ("Total", s['total'], self.TEXT)]

        for i, (label, value, color) in enumerate(items):
            f = tk.Frame(grid, bg=self.CARD_BG)
            f.grid(row=0, column=i, padx=10, pady=3)
            tk.Label(f, text=label, font=('Segoe UI', 8), bg=self.CARD_BG, fg=self.MUTED).pack()
            tk.Label(f, text=str(value), font=('Segoe UI', 16, 'bold'), bg=self.CARD_BG, fg=color).pack()

        all_cards = []
        for deck in course.decks:
            all_cards.extend(deck.cards)

        if not all_cards:
            tk.Label(self.content, text="No words yet", font=('Segoe UI', 14),
                     bg=self.BG, fg=self.MUTED).pack(expand=True)
            return

        # Filter buttons - clean and consistent
        btn_row = tk.Frame(self.content, bg=self.BG)
        btn_row.pack(fill=tk.X, padx=40, pady=10)

        tk.Label(btn_row, text="View words:", font=('Segoe UI', 11, 'bold'),
                 bg=self.BG, fg=self.TEXT).pack(side=tk.LEFT, padx=(0, 10))

        # Create a container for all filter buttons
        filter_container = tk.Frame(btn_row, bg=self.CARD_BG, relief='solid', borderwidth=1)
        filter_container.pack(side=tk.LEFT)

        categories = [
            ("All", "all"),
            ("New", "new"),
            ("Learning", "learning"),
            ("Review", "review"),
            ("Mastered", "mastered"),
            ("Ignored", "ignored"),
        ]

        for i, (text, status) in enumerate(categories):
            btn = tk.Button(filter_container, text=text,
                            command=lambda s=status: self._view_words_paginated(all_cards, s),
                            font=('Segoe UI', 10, 'bold'),
                            bg=self.CARD_BG,
                            fg=self.TEXT,
                            padx=12, pady=5, cursor='hand2',
                            relief='flat', borderwidth=0)
            btn.pack(side=tk.LEFT)

            # Add separator between buttons
            if i < len(categories) - 1:
                tk.Label(filter_container, text="|", font=('Segoe UI', 10),
                         bg=self.CARD_BG, fg=self.MUTED).pack(side=tk.LEFT)

        # Create a frame for the word list that we can clear later
        self.words_frame = tk.Frame(self.content, bg=self.BG)
        self.words_frame.pack(fill=tk.BOTH, expand=True)

        # Show all words in the words_frame
        self._show_words_in_frame(all_cards, "all")

    def _show_words_in_frame(self, all_cards, filter_status="all", page=0):
        """Display words in the words_frame instead of clearing everything"""
        # Clear only the words frame, not the whole screen
        for w in self.words_frame.winfo_children():
            w.destroy()

        if filter_status == "all":
            display = all_cards
        elif filter_status == "new":
            display = [c for c in all_cards if c.status == "new" and not c.ignored]
        elif filter_status == "learning":
            display = [c for c in all_cards if c.status == "learning" and not c.ignored]
        elif filter_status == "review":
            display = [c for c in all_cards if c.status == "review" and not c.ignored]
        elif filter_status == "mastered":
            display = [c for c in all_cards if c.status == "mastered" and not c.ignored]
        elif filter_status == "ignored":
            display = [c for c in all_cards if c.ignored]
        else:
            display = all_cards

        PAGE_SIZE = 50
        total = len(display)
        total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        start = page * PAGE_SIZE
        end = min(start + PAGE_SIZE, total)
        page_cards = display[start:end]

        # Filter info header
        info_frame = tk.Frame(self.words_frame, bg=self.BG)
        info_frame.pack(fill=tk.X, pady=(0, 10))

        filter_name = filter_status.title()
        tk.Label(info_frame, text=f"Showing: {filter_name} Words ({total})",
                 font=('Segoe UI', 12, 'bold'),
                 bg=self.BG, fg=self.ACCENT).pack(side=tk.LEFT)

        tk.Label(info_frame, text=f"Page {page + 1}/{total_pages}",
                 font=('Segoe UI', 10), bg=self.BG, fg=self.MUTED).pack(side=tk.RIGHT)

        # Page navigation
        if total_pages > 1:
            page_bar = tk.Frame(self.words_frame, bg=self.BG)
            page_bar.pack(fill=tk.X, pady=5)

            if page > 0:
                tk.Button(page_bar, text="◀ Previous",
                          command=lambda: self._show_words_in_frame(all_cards, filter_status, page - 1),
                          bg=self.CARD_BG, fg=self.TEXT, cursor='hand2', relief='flat'
                          ).pack(side=tk.LEFT, padx=2)

            tk.Label(page_bar, text=f"Page {page + 1} of {total_pages}",
                     font=('Segoe UI', 9), bg=self.BG, fg=self.MUTED).pack(side=tk.LEFT, padx=10)

            if page < total_pages - 1:
                tk.Button(page_bar, text="Next ▶",
                          command=lambda: self._show_words_in_frame(all_cards, filter_status, page + 1),
                          bg=self.CARD_BG, fg=self.TEXT, cursor='hand2', relief='flat'
                          ).pack(side=tk.LEFT, padx=2)

        # Scrollable word list
        canvas = tk.Canvas(self.words_frame, bg=self.BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.words_frame, orient="vertical", command=canvas.yview)
        wf = tk.Frame(canvas, bg=self.BG)

        wf.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=wf, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig("all", width=e.width))

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", on_mousewheel)

        if not page_cards:
            tk.Label(wf, text="No words", font=('Segoe UI', 14), bg=self.BG, fg=self.MUTED).pack(pady=40)

        for i, card in enumerate(page_cards):
            actual_idx = start + i

            if card.ignored:
                icon, color = "🗑️", self.MUTED
            elif card.status == "new":
                icon, color = "🆕", self.ACCENT
            elif card.status == "learning":
                icon, color = "📖", self.ORANGE
            elif card.status == "review":
                icon, color = "🔄", self.RED
            else:
                icon, color = "⭐", self.GREEN

            cf = tk.Frame(wf, bg=self.CARD_BG, padx=15, pady=8)
            cf.pack(fill=tk.X, pady=2)

            tk.Label(cf, text=icon, font=('Segoe UI', 12), bg=self.CARD_BG).pack(side=tk.LEFT, padx=(0, 10))

            info = tk.Frame(cf, bg=self.CARD_BG)
            info.pack(side=tk.LEFT, fill=tk.X, expand=True)

            tk.Label(info, text=f"{actual_idx + 1}. {card.front}", font=('Segoe UI', 11, 'bold'),
                     bg=self.CARD_BG, fg=self.TEXT).pack(anchor='w')
            tk.Label(info, text=card.back, font=('Segoe UI', 9), bg=self.CARD_BG, fg=self.MUTED).pack(anchor='w')

            # Action buttons
            af = tk.Frame(cf, bg=self.CARD_BG)
            af.pack(side=tk.RIGHT)

            tk.Button(af, text="✏️ Edit",
                      command=lambda c=card: self._edit_word_in_manage(c, all_cards, filter_status, page),
                      bg=self.ACCENT, fg='white', font=('Segoe UI', 8), padx=8,
                      cursor='hand2', relief='flat', borderwidth=0).pack(side=tk.LEFT, padx=2)

            tk.Button(af, text="🗑️ Delete",
                      command=lambda c=card: self._delete_word_in_manage(c, all_cards, filter_status, page),
                      bg=self.RED, fg='white', font=('Segoe UI', 8), padx=8,
                      cursor='hand2', relief='flat', borderwidth=0).pack(side=tk.LEFT, padx=2)

            if card.ignored:
                tk.Button(af, text="Restore", command=lambda c=card: self._toggle_ignore_simple(c),
                          bg=self.ORANGE, fg='white', font=('Segoe UI', 8), padx=5,
                          cursor='hand2', relief='flat', borderwidth=0).pack(side=tk.LEFT, padx=2)
            else:
                tk.Button(af, text="Ignore", command=lambda c=card: self._toggle_ignore_simple(c),
                          bg=self.MUTED, fg='white', font=('Segoe UI', 8), padx=5,
                          cursor='hand2', relief='flat', borderwidth=0).pack(side=tk.LEFT, padx=2)

            tk.Button(af, text="Reset", command=lambda c=card: self._reset_word_simple(c),
                      bg=self.ORANGE, fg='white', font=('Segoe UI', 8), padx=5,
                      cursor='hand2', relief='flat', borderwidth=0).pack(side=tk.LEFT, padx=2)

    def _view_words_paginated(self, all_cards, filter_status="all", page=0):
        self._clear()

        if filter_status == "all":
            display = all_cards
        elif filter_status == "new":
            display = [c for c in all_cards if c.status == "new" and not c.ignored]
        elif filter_status == "learning":
            display = [c for c in all_cards if c.status == "learning" and not c.ignored]
        elif filter_status == "review":
            display = [c for c in all_cards if c.status == "review" and not c.ignored]
        elif filter_status == "mastered":
            display = [c for c in all_cards if c.status == "mastered" and not c.ignored]
        elif filter_status == "ignored":
            display = [c for c in all_cards if c.ignored]
        else:
            display = all_cards

        PAGE_SIZE = 50
        total = len(display)
        total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        start = page * PAGE_SIZE
        end = min(start + PAGE_SIZE, total)
        page_cards = display[start:end]

        header = tk.Frame(self.content, bg=self.BG)
        header.pack(fill=tk.X, padx=40, pady=(20, 10))

        filter_name = filter_status.title()
        tk.Label(header, text=f"📝 {filter_name} Words ({total})", font=('Segoe UI', 18, 'bold'),
                 bg=self.BG, fg=self.TEXT).pack(side=tk.LEFT)

        tk.Button(header, text="← Back to Course",
                  command=lambda: self._manage_course(self.current_course),
                  bg=self.CARD_BG, fg=self.TEXT, font=('Segoe UI', 10),
                  padx=12, pady=5, cursor='hand2', relief='flat').pack(side=tk.RIGHT)

        # Filter buttons - clean and consistent
        filter_frame = tk.Frame(self.content, bg=self.BG)
        filter_frame.pack(fill=tk.X, padx=40, pady=10)

        filters = [("All", "all"), ("New", "new"), ("Learning", "learning"),
                   ("Review", "review"), ("Mastered", "mastered"), ("Ignored", "ignored")]

        # Create a container frame with subtle border
        filter_container = tk.Frame(filter_frame, bg=self.CARD_BG, relief='solid', borderwidth=1)
        filter_container.pack()

        for text, status in filters:
            # Choose color - accent for active, muted for inactive
            text_color = self.ACCENT if filter_status == status else self.MUTED
            font_style = ('Segoe UI', 10, 'bold' if filter_status == status else 'normal')

            btn = tk.Button(filter_container, text=text,
                            command=lambda s=status: self._view_words_paginated(all_cards, s, 0),
                            font=font_style,
                            bg=self.CARD_BG,
                            fg=text_color,
                            padx=15, pady=6, cursor='hand2',
                            relief='flat', borderwidth=0)

            btn.pack(side=tk.LEFT)

            # Add separator except after last button
            if status != filters[-1][1]:
                tk.Label(filter_container, text="|", font=('Segoe UI', 10),
                         bg=self.CARD_BG, fg=self.MUTED).pack(side=tk.LEFT)

        # Page info on the right
        tk.Label(filter_frame, text=f"Page {page + 1}/{total_pages}",
                 font=('Segoe UI', 10), bg=self.BG, fg=self.MUTED).pack(side=tk.RIGHT)

        # Page navigation bar
        if total_pages > 1:
            page_bar = tk.Frame(self.content, bg=self.BG)
            page_bar.pack(fill=tk.X, padx=40, pady=3)

            if page > 0:
                tk.Button(page_bar, text="«", command=lambda: self._view_words_paginated(all_cards, filter_status, 0),
                          font=('Segoe UI', 9), bg=self.CARD_BG, fg=self.TEXT, cursor='hand2', relief='flat',
                          borderwidth=0).pack(side=tk.LEFT, padx=1)
                tk.Button(page_bar, text="‹",
                          command=lambda: self._view_words_paginated(all_cards, filter_status, page - 1),
                          font=('Segoe UI', 9), bg=self.CARD_BG, fg=self.TEXT, cursor='hand2', relief='flat',
                          borderwidth=0).pack(side=tk.LEFT, padx=1)

            sp = max(0, page - 7)
            ep = min(total_pages, sp + 15)
            for p in range(sp, ep):
                bg = self.ACCENT if p == page else self.CARD_BG
                fg = 'white' if p == page else self.TEXT
                tk.Button(page_bar, text=str(p + 1),
                          command=lambda pp=p: self._view_words_paginated(all_cards, filter_status, pp),
                          font=('Segoe UI', 9), bg=bg, fg=fg, width=3, cursor='hand2', relief='flat',
                          borderwidth=0).pack(side=tk.LEFT, padx=1)

            if page < total_pages - 1:
                tk.Button(page_bar, text="›",
                          command=lambda: self._view_words_paginated(all_cards, filter_status, page + 1),
                          font=('Segoe UI', 9), bg=self.CARD_BG, fg=self.TEXT, cursor='hand2', relief='flat',
                          borderwidth=0).pack(side=tk.LEFT, padx=1)
                tk.Button(page_bar, text="»",
                          command=lambda: self._view_words_paginated(all_cards, filter_status, total_pages - 1),
                          font=('Segoe UI', 9), bg=self.CARD_BG, fg=self.TEXT, cursor='hand2', relief='flat',
                          borderwidth=0).pack(side=tk.LEFT, padx=1)

        # Scrollable word list
        canvas = tk.Canvas(self.content, bg=self.BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.content, orient="vertical", command=canvas.yview)
        wf = tk.Frame(canvas, bg=self.BG)

        wf.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=wf, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind("<Configure>", lambda e: canvas.itemconfig("all", width=e.width))

        canvas.pack(side="left", fill="both", expand=True, padx=40)
        scrollbar.pack(side="right", fill="y")

        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", on_mousewheel)

        if not page_cards:
            tk.Label(wf, text="No words", font=('Segoe UI', 14), bg=self.BG, fg=self.MUTED).pack(pady=40)

        for i, card in enumerate(page_cards):
            actual_idx = start + i

            if card.ignored:
                icon, color = "🗑️", self.MUTED
            elif card.status == "new":
                icon, color = "🆕", self.ACCENT
            elif card.status == "learning":
                icon, color = "📖", self.ORANGE
            elif card.status == "review":
                icon, color = "🔄", self.RED
            else:
                icon, color = "⭐", self.GREEN

            cf = tk.Frame(wf, bg=self.CARD_BG, padx=15, pady=8)
            cf.pack(fill=tk.X, pady=2)

            tk.Label(cf, text=icon, font=('Segoe UI', 12), bg=self.CARD_BG).pack(side=tk.LEFT, padx=(0, 10))

            info = tk.Frame(cf, bg=self.CARD_BG)
            info.pack(side=tk.LEFT, fill=tk.X, expand=True)

            tk.Label(info, text=f"{actual_idx + 1}. {card.front}", font=('Segoe UI', 11, 'bold'),
                     bg=self.CARD_BG, fg=self.TEXT).pack(anchor='w')
            tk.Label(info, text=card.back, font=('Segoe UI', 9), bg=self.CARD_BG, fg=self.MUTED).pack(anchor='w')

            # Show review time for non-new, non-ignored words
            if card.level > 0 and not card.ignored:
                try:
                    nd = datetime.fromisoformat(card.next_review)
                    now = datetime.now()
                    diff = nd - now

                    if diff.total_seconds() <= 0:
                        time_text = "🔴 Due now"
                        time_color = self.RED
                    else:
                        days = diff.days
                        hours = diff.seconds // 3600
                        minutes = (diff.seconds % 3600) // 60

                        if days > 0:
                            time_text = f"⏳ Review in {days}d {hours}h"
                        elif hours > 0:
                            time_text = f"⏳ Review in {hours}h {minutes}m"
                        else:
                            time_text = f"⏳ Review in {minutes}m"
                        time_color = self.MUTED

                    tk.Label(info, text=time_text, font=('Segoe UI', 8),
                             bg=self.CARD_BG, fg=time_color).pack(anchor='w')
                except:
                    pass
            elif card.level == 0 and not card.ignored:
                tk.Label(info, text="🆕 Not yet learned", font=('Segoe UI', 8),
                         bg=self.CARD_BG, fg=self.ACCENT).pack(anchor='w')

            # Action buttons frame
            af = tk.Frame(cf, bg=self.CARD_BG)
            af.pack(side=tk.RIGHT)

            # EDIT button
            tk.Button(af, text="✏️ Edit",
                      command=lambda c=card: self._edit_word_in_manage(c, all_cards, filter_status, page),
                      bg=self.ACCENT, fg='white', font=('Segoe UI', 8), padx=8,
                      cursor='hand2', relief='flat', borderwidth=0).pack(side=tk.LEFT, padx=2)

            # DELETE button
            tk.Button(af, text="🗑️ Delete",
                      command=lambda c=card: self._delete_word_in_manage(c, all_cards, filter_status, page),
                      bg=self.RED, fg='white', font=('Segoe UI', 8), padx=8,
                      cursor='hand2', relief='flat', borderwidth=0).pack(side=tk.LEFT, padx=2)

            if card.ignored:
                tk.Button(af, text="Restore", command=lambda c=card: self._toggle_ignore_simple(c),
                          bg=self.ORANGE, fg='white', font=('Segoe UI', 8), padx=5,
                          cursor='hand2', relief='flat', borderwidth=0).pack(side=tk.LEFT, padx=2)
            else:
                tk.Button(af, text="Ignore", command=lambda c=card: self._toggle_ignore_simple(c),
                          bg=self.MUTED, fg='white', font=('Segoe UI', 8), padx=5,
                          cursor='hand2', relief='flat', borderwidth=0).pack(side=tk.LEFT, padx=2)

            tk.Button(af, text="Reset", command=lambda c=card: self._reset_word_simple(c),
                      bg=self.ORANGE, fg='white', font=('Segoe UI', 8), padx=5,
                      cursor='hand2', relief='flat', borderwidth=0).pack(side=tk.LEFT, padx=2)

    def _toggle_ignore_simple(self, card):
        card.ignored = not card.ignored
        self.dm.save(self.courses)
        self._show_courses()

    def _reset_word_simple(self, card):
        if messagebox.askyesno("Reset", f"Reset '{card.front}' to New?"):
            card.reset()
            self.dm.save(self.courses)
            self._show_courses()

    def _edit_word_in_manage(self, card, all_cards, filter_status, page):
        """Edit a word from the manage view"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Edit Word")
        dialog.geometry("500x400")
        dialog.configure(bg=self.CARD_BG)
        dialog.transient(self.root)
        dialog.grab_set()

        x = self.root.winfo_rootx() + (self.root.winfo_width() - 500) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - 400) // 2
        dialog.geometry(f"+{x}+{y}")

        tk.Label(dialog, text="✏️ Edit Word", font=('Segoe UI', 16, 'bold'),
                 bg=self.CARD_BG, fg=self.TEXT).pack(pady=15)

        tk.Label(dialog, text="Front (Question/Word):", font=('Segoe UI', 11),
                 bg=self.CARD_BG, fg=self.MUTED).pack(anchor='w', padx=30)
        front_entry = tk.Entry(dialog, font=('Segoe UI', 13), bg=self.BG, fg=self.TEXT,
                               insertbackground=self.TEXT, relief='flat')
        front_entry.insert(0, card.front)
        front_entry.pack(fill=tk.X, padx=30, pady=5, ipady=3)
        front_entry.focus()
        front_entry.select_range(0, tk.END)

        tk.Label(dialog, text="Back (Answer/Translation):", font=('Segoe UI', 11),
                 bg=self.CARD_BG, fg=self.MUTED).pack(anchor='w', padx=30, pady=(10, 0))
        back_entry = tk.Entry(dialog, font=('Segoe UI', 13), bg=self.BG, fg=self.TEXT,
                              insertbackground=self.TEXT, relief='flat')
        back_entry.insert(0, card.back)
        back_entry.pack(fill=tk.X, padx=30, pady=5, ipady=3)

        tk.Label(dialog, text="Hint (optional):", font=('Segoe UI', 11),
                 bg=self.CARD_BG, fg=self.MUTED).pack(anchor='w', padx=30, pady=(10, 0))
        hint_entry = tk.Entry(dialog, font=('Segoe UI', 13), bg=self.BG, fg=self.TEXT,
                              insertbackground=self.TEXT, relief='flat')
        hint_entry.insert(0, card.hint)
        hint_entry.pack(fill=tk.X, padx=30, pady=5, ipady=3)

        def save():
            f = front_entry.get().strip()
            b = back_entry.get().strip()
            h = hint_entry.get().strip()

            if not f or not b:
                messagebox.showwarning("Required", "Front and Back are required!", parent=dialog)
                return

            card.front = f
            card.back = b
            card.hint = h

            self.dm.save(self.courses)
            dialog.destroy()

            # Refresh the view
            new_all_cards = []
            for deck in self.current_course.decks:
                new_all_cards.extend(deck.cards)
            self._view_words_paginated(new_all_cards, filter_status, page)

        btn_frame = tk.Frame(dialog, bg=self.CARD_BG)
        btn_frame.pack(pady=20)

        tk.Button(btn_frame, text="💾 Save Changes", command=save,
                  bg=self.GREEN, fg='white', font=('Segoe UI', 11, 'bold'),
                  padx=20, pady=8, cursor='hand2', relief='flat').pack(side=tk.LEFT, padx=5)

        tk.Button(btn_frame, text="Cancel", command=dialog.destroy,
                  bg=self.MUTED, fg='white', font=('Segoe UI', 11),
                  padx=20, pady=8, cursor='hand2', relief='flat').pack(side=tk.LEFT, padx=5)

    def _delete_word_in_manage(self, card, all_cards, filter_status, page):
        """Delete a word from the manage view"""
        if messagebox.askyesno("Delete Word", f"Delete '{card.front}' permanently?\n\nThis cannot be undone!"):
            # Find and remove the card from its deck
            for course in self.courses:
                if course == self.current_course:
                    for deck in course.decks:
                        if card in deck.cards:
                            deck.cards.remove(card)
                            break
                    break

            self.dm.save(self.courses)

            # Refresh the view with updated card list
            new_all_cards = []
            for deck in self.current_course.decks:
                new_all_cards.extend(deck.cards)

            self._view_words_paginated(new_all_cards, filter_status, page)

    # ===== MULTIPLE CHOICE STUDY =====

    def _start_session(self, course, card_type):
        cards = []
        for deck in course.decks:
            if card_type == "new":
                cards = deck.get_new()
                limit = course.words_per_session
            elif card_type == "due":
                cards = deck.get_due()
                limit = course.review_words_per_session
            elif card_type == "learning":
                cards = deck.get_learning()
                limit = course.words_per_session

        random.shuffle(cards)
        cards = cards[:limit]

        if not cards:
            messagebox.showinfo("Done!", f"No {card_type} cards!")
            return

        self.current_course = course
        self.study_cards = cards
        self.current_idx = 0
        self.correct_count = 0

        self._show_mc_question()

    def _show_mc_question(self):
        self._clear()

        if self.current_idx >= len(self.study_cards):
            self._show_results()
            return

        card = self.study_cards[self.current_idx]
        course = self.current_course

        bar_frame = tk.Frame(self.content, bg=self.BG)
        bar_frame.pack(fill=tk.X, padx=40, pady=(30, 20))

        tk.Button(bar_frame, text="✕ Exit", command=self._exit_session,
                  bg=self.BG, fg=self.MUTED, font=('Segoe UI', 12),
                  cursor='hand2', relief='flat', borderwidth=0).pack(side=tk.LEFT)

        tk.Button(bar_frame, text="✏️ Edit",
                  command=lambda c=card: self._edit_card_during_study(c),
                  bg=self.BG, fg=self.PURPLE, font=('Segoe UI', 12),
                  cursor='hand2', relief='flat', borderwidth=0).pack(side=tk.LEFT, padx=10)

        pct = int((self.current_idx / len(self.study_cards)) * 100)
        tk.Label(bar_frame, text=f"{self.current_idx + 1}/{len(self.study_cards)}",
                 font=('Segoe UI', 12), bg=self.BG, fg=self.MUTED).pack(side=tk.LEFT, padx=15)

        bar_bg = tk.Frame(bar_frame, bg=self.BORDER, height=4)
        bar_bg.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        bar_fill = tk.Frame(bar_bg, bg=self.ACCENT, width=int(pct * 4), height=4)
        bar_fill.pack(side=tk.LEFT)
        bar_fill.pack_propagate(False)

        tk.Label(bar_frame, text=f"✅ {self.correct_count}",
                 font=('Segoe UI', 12), bg=self.BG, fg=self.GREEN).pack(side=tk.RIGHT)

        q_card = tk.Frame(self.content, bg=self.CARD_BG, padx=60, pady=40)
        q_card.pack(fill=tk.BOTH, padx=60, pady=(0, 15), expand=True)

        if card.level == 0:
            badge, color = "🆕 NEW", self.ACCENT
        elif card.status == "learning":
            badge, color = "📖 LEARNING", self.ORANGE
        else:
            badge, color = "🔄 REVIEW", self.RED

        tk.Label(q_card, text=badge, font=('Segoe UI', 10, 'bold'),
                 bg=self.CARD_BG, fg=color).pack(pady=(0, 10))

        # SELECTABLE question text
        q_text = self._create_selectable_text(q_card, card.front, font_size=28, bold=True)
        q_text.pack(expand=True)

        if card.hint:
            tk.Label(q_card, text=f"💡 {card.hint}", font=('Segoe UI', 11),
                     bg=self.CARD_BG, fg=self.MUTED).pack(pady=(10, 0))

        tk.Label(q_card, text="Choose the correct translation:",
                 font=('Segoe UI', 11), bg=self.CARD_BG, fg=self.MUTED).pack(pady=(15, 0))

        all_answers = [card.back]
        for deck in course.decks:
            for c in deck.cards:
                if c.back != card.back and c.back not in all_answers:
                    all_answers.append(c.back)
        random.shuffle(all_answers)
        choices = all_answers[:4]
        if card.back not in choices:
            choices[random.randint(0, 3)] = card.back
        random.shuffle(choices)

        choices_frame = tk.Frame(self.content, bg=self.BG)
        choices_frame.pack(fill=tk.X, padx=60, pady=(0, 10))

        for i, choice in enumerate(choices):
            letter = chr(65 + i)
            btn = tk.Button(choices_frame, text=f"● {choice}",
                            font=('Segoe UI', 13), bg=self.CARD_BG, fg=self.TEXT,
                            padx=20, pady=14, cursor='hand2', relief='flat',
                            borderwidth=0, anchor='w',
                            activebackground=self.ACCENT, activeforeground='white')
            btn.pack(fill=tk.X, pady=3)
            btn.config(command=lambda ch=choice: self._check_answer(ch, card))

        bottom = tk.Frame(self.content, bg=self.BG)
        bottom.pack(pady=(0, 20))

        tk.Button(bottom, text="⚡ I know this",
                  command=lambda c=card: self._already_known_skip(c),
                  font=('Segoe UI', 10), bg=self.PURPLE, fg='white',
                  padx=15, pady=8, cursor='hand2', relief='flat', borderwidth=0
                  ).pack(side=tk.LEFT, padx=5)

        tk.Button(bottom, text="🗑️ Skip",
                  command=lambda c=card: self._skip_current(c),
                  font=('Segoe UI', 10), bg=self.BG, fg=self.MUTED,
                  padx=15, pady=8, cursor='hand2', relief='flat', borderwidth=0
                  ).pack(side=tk.LEFT, padx=5)

    def _edit_card_during_study(self, card):
        """Edit a card while studying"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Edit Card")
        dialog.geometry("500x300")
        dialog.configure(bg=self.CARD_BG)
        dialog.transient(self.root)
        dialog.grab_set()

        x = self.root.winfo_rootx() + (self.root.winfo_width() - 500) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - 300) // 2
        dialog.geometry(f"+{x}+{y}")

        tk.Label(dialog, text="✏️ Edit Card", font=('Segoe UI', 16, 'bold'),
                 bg=self.CARD_BG, fg=self.TEXT).pack(pady=15)

        tk.Label(dialog, text="Front (Question):", font=('Segoe UI', 11),
                 bg=self.CARD_BG, fg=self.MUTED).pack(anchor='w', padx=30)
        front_entry = tk.Entry(dialog, font=('Segoe UI', 13), bg=self.BG, fg=self.TEXT,
                               insertbackground=self.TEXT, relief='flat')
        front_entry.insert(0, card.front)
        front_entry.pack(fill=tk.X, padx=30, pady=5, ipady=3)
        front_entry.focus()
        front_entry.select_range(0, tk.END)

        tk.Label(dialog, text="Back (Answer):", font=('Segoe UI', 11),
                 bg=self.CARD_BG, fg=self.MUTED).pack(anchor='w', padx=30, pady=(10, 0))
        back_entry = tk.Entry(dialog, font=('Segoe UI', 13), bg=self.BG, fg=self.TEXT,
                              insertbackground=self.TEXT, relief='flat')
        back_entry.insert(0, card.back)
        back_entry.pack(fill=tk.X, padx=30, pady=5, ipady=3)

        def save():
            f = front_entry.get().strip()
            b = back_entry.get().strip()
            if not f or not b:
                messagebox.showwarning("Required", "Front and Back are required!", parent=dialog)
                return
            card.front = f
            card.back = b
            self.dm.save(self.courses)
            dialog.destroy()
            self._show_mc_question()

        btn_frame = tk.Frame(dialog, bg=self.CARD_BG)
        btn_frame.pack(pady=15)

        tk.Button(btn_frame, text="💾 Save", command=save,
                  bg=self.GREEN, fg='white', font=('Segoe UI', 11, 'bold'),
                  padx=20, pady=8, cursor='hand2', relief='flat').pack(side=tk.LEFT, padx=5)

        tk.Button(btn_frame, text="Cancel", command=dialog.destroy,
                  bg=self.MUTED, fg='white', font=('Segoe UI', 11),
                  padx=20, pady=8, cursor='hand2', relief='flat').pack(side=tk.LEFT, padx=5)

    def _check_answer(self, selected, card):
        correct = selected == card.back

        if correct:
            self.correct_count += 1
            card.correct_streak += 1
            card.reps += 1
            intervals = [0, 0.167, 0.5, 1, 3, 7, 30, 90, 180, 365]
            card.level = min(len(intervals) - 1, card.level + 1)
            card.next_review = (datetime.now() + timedelta(days=intervals[card.level])).isoformat()
            card.reviews += 1

            # Go directly to next card
            self.current_idx += 1
            self._show_mc_question()
            return

        else:
            card.lapses += 1
            card.reps = 0
            card.ease_factor = max(1.3, card.ease_factor - 0.20)
            card.level = max(0, card.level - 1)
            card.next_review = datetime.now().isoformat()
            card.correct_streak = 0
            card.reviews += 1

        # Wrong answer - show feedback
        self._clear()

        result = tk.Frame(self.content, bg=self.RED, padx=40, pady=30)
        result.pack(expand=True, fill=tk.BOTH, padx=60, pady=30)

        tk.Label(result, text="❌ Wrong!", font=('Segoe UI', 24, 'bold'),
                 bg=self.RED, fg='white').pack(pady=(10, 15))

        q_text = self._create_selectable_text(result, card.front, font_size=20, bold=True,
                                              fg='white', bg=self.RED)
        q_text.pack(pady=5)

        tk.Label(result, text=f"You chose: {selected}",
                 font=('Segoe UI', 13), bg=self.RED, fg='#ffcccc').pack(pady=(15, 5))
        tk.Frame(result, bg='white', height=1).pack(fill=tk.X, pady=10)
        tk.Label(result, text="Correct answer:",
                 font=('Segoe UI', 13, 'bold'), bg=self.RED, fg='white').pack()

        a_text = self._create_selectable_text(result, card.back, font_size=24, bold=True,
                                              fg='#ffff00', bg=self.RED)
        a_text.pack(pady=10)

        if card.hint:
            tk.Label(result, text=f"💡 {card.hint}",
                     font=('Segoe UI', 11), bg=self.RED, fg='#ffcccc').pack(pady=5)

        tk.Button(result, text="Continue →",
                  command=lambda: self._wrong_continue(),
                  font=('Segoe UI', 14, 'bold'), bg='white', fg=self.RED,
                  padx=30, pady=10, cursor='hand2', relief='flat',
                  borderwidth=0).pack(pady=20)

        self.content.bind('<Return>', lambda e: self._wrong_continue())
        self.content.bind('<space>', lambda e: self._wrong_continue())
        self.content.focus_set()

    def _wrong_continue(self):
        """Continue after wrong answer"""
        self.content.unbind('<Return>')
        self.content.unbind('<space>')
        self.current_idx += 1
        self._show_mc_question()

    def _already_known_skip(self, card):
        card.already_known()
        self.current_idx += 1
        self._show_mc_question()

    def _skip_current(self, card):
        card.ignored = True
        self.current_idx += 1
        self._show_mc_question()

    def _exit_session(self):
        self.dm.save(self.courses)
        self._show_courses()

    def _show_results(self):
        self._clear()
        self.dm.save(self.courses)

        pct = int((self.correct_count / len(self.study_cards)) * 100) if self.study_cards else 0

        tk.Label(self.content, text="🎉 Session Complete!", font=('Segoe UI', 28, 'bold'),
                 bg=self.BG, fg=self.TEXT).pack(pady=(60, 10))
        tk.Label(self.content, text=f"{self.correct_count}/{len(self.study_cards)} correct ({pct}%)",
                 font=('Segoe UI', 16), bg=self.BG, fg=self.MUTED).pack(pady=10)

        if self.current_course:
            s = self.current_course.stats()
            progress = tk.Frame(self.content, bg=self.CARD_BG)
            progress.pack(pady=30, padx=80, fill=tk.X)

            for text, color in [
                (f"🆕 New: {s['new']}", self.ACCENT),
                (f"📖 Learned: {s['learning']}", self.ORANGE),
                (f"🔄 To Review: {s['due']}", self.RED),
                (f"⭐ Mastered: {s['mastered']}", self.GREEN),
            ]:
                tk.Label(progress, text=text, font=('Segoe UI', 13),
                         bg=self.CARD_BG, fg=color).pack(pady=8)

        btn_frame = tk.Frame(self.content, bg=self.BG)
        btn_frame.pack(pady=20)

        if self.current_course:
            s = self.current_course.stats()
            if s['new'] > 0:
                tk.Button(btn_frame, text="📖 Learn New Words",
                          command=lambda: self._start_session(self.current_course, "new"),
                          bg=self.ACCENT, fg='white', font=('Segoe UI', 13, 'bold'),
                          padx=30, pady=12, cursor='hand2', relief='flat', borderwidth=0
                          ).pack(side=tk.LEFT, padx=10)
            if s['due'] > 0:
                tk.Button(btn_frame, text="🔄 Review Words",
                          command=lambda: self._start_session(self.current_course, "due"),
                          bg=self.RED, fg='white', font=('Segoe UI', 13, 'bold'),
                          padx=30, pady=12, cursor='hand2', relief='flat', borderwidth=0
                          ).pack(side=tk.LEFT, padx=10)

        tk.Button(btn_frame, text="Back to Courses", command=self._show_courses,
                  bg=self.CARD_BG, fg=self.TEXT, font=('Segoe UI', 13),
                  padx=30, pady=12, cursor='hand2', relief='flat', borderwidth=0
                  ).pack(side=tk.LEFT, padx=10)

    def _create_selectable_text(self, parent, text, font_size=28, bold=False, fg=None, bg=None, wraplength=600):
        weight = 'bold' if bold else 'normal'
        font = ('Segoe UI', font_size, weight)
        fg = fg or self.TEXT
        bg = bg or self.CARD_BG

        txt = tk.Text(parent, font=font, fg=fg, bg=bg,
                      wrap=tk.WORD, relief='flat', borderwidth=0,
                      highlightthickness=0, cursor='xterm',
                      padx=0, pady=0, height=2)
        txt.insert('1.0', text.strip())
        txt.config(state='disabled')

        def on_click(event):
            txt.config(state='normal')
            txt.focus_set()

        def on_release(event):
            txt.config(state='disabled')

        def on_right_click(event):
            txt.config(state='normal')
            txt.focus_set()
            menu = tk.Menu(txt, tearoff=0)
            menu.add_command(label="Copy", command=lambda: self._copy_text(txt))
            menu.add_command(label="Select All", command=lambda: self._select_all_text(txt))
            menu.post(event.x_root, event.y_root)

        txt.bind('<Button-1>', on_click)
        txt.bind('<ButtonRelease-1>', on_release)
        txt.bind('<Button-3>', on_right_click)

        return txt

    def _copy_text(self, widget):
        try:
            selected = widget.selection_get()
            widget.clipboard_clear()
            widget.clipboard_append(selected)
        except:
            all_text = widget.get("1.0", "end-1c")
            widget.clipboard_clear()
            widget.clipboard_append(all_text)
        widget.config(state='disabled')

    def _select_all_text(self, widget):
        widget.config(state='normal')
        widget.tag_add(tk.SEL, "1.0", tk.END)
        widget.mark_set(tk.INSERT, "1.0")
        widget.see(tk.INSERT)
        widget.config(state='disabled')

    def run(self):
        self.root.mainloop()

    def _add_words_dialog(self, course):
        """Dialog to add more words with a table layout"""
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Add Words - {course.name}")
        dialog.geometry("800x600")
        dialog.configure(bg=self.CARD_BG)
        dialog.transient(self.root)
        dialog.grab_set()

        x = self.root.winfo_rootx() + (self.root.winfo_width() - 800) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - 600) // 2
        dialog.geometry(f"+{x}+{y}")

        # Title
        tk.Label(dialog, text=f"Add Words to {course.name}", font=('Segoe UI', 16, 'bold'),
                 bg=self.CARD_BG, fg=self.TEXT).pack(pady=15)

        # Instructions
        tk.Label(dialog, text="Fill in the table below. Click '+ Add Row' for more rows.",
                 font=('Segoe UI', 10), bg=self.CARD_BG, fg=self.MUTED).pack(pady=(0, 10))

        # Column headers
        col_frame = tk.Frame(dialog, bg=self.CARD_BG)
        col_frame.pack(fill=tk.X, padx=20, pady=(5, 0))

        tk.Label(col_frame, text="#", font=('Segoe UI', 9, 'bold'), bg=self.CARD_BG,
                 fg=self.MUTED, width=4).pack(side=tk.LEFT)
        tk.Label(col_frame, text="Front (Question/Word)", font=('Segoe UI', 9, 'bold'),
                 bg=self.CARD_BG, fg=self.ACCENT, width=28, anchor='w').pack(side=tk.LEFT, padx=(5, 5))
        tk.Label(col_frame, text="Back (Answer/Translation)", font=('Segoe UI', 9, 'bold'),
                 bg=self.CARD_BG, fg=self.GREEN, width=28, anchor='w').pack(side=tk.LEFT, padx=(0, 5))
        tk.Label(col_frame, text="Hint (optional)", font=('Segoe UI', 9, 'bold'),
                 bg=self.CARD_BG, fg=self.MUTED, width=15, anchor='w').pack(side=tk.LEFT)

        # Scrollable table
        canvas = tk.Canvas(dialog, bg=self.CARD_BG, highlightthickness=0, height=300)
        scrollbar = ttk.Scrollbar(dialog, orient="vertical", command=canvas.yview)
        rows_frame = tk.Frame(canvas, bg=self.CARD_BG)

        rows_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=rows_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill=tk.BOTH, expand=True, padx=(20, 0), pady=10)
        scrollbar.pack(side="right", fill=tk.Y, padx=(0, 20), pady=10)

        # Store rows
        rows = []

        def clear_all_rows():
            """Remove all existing rows"""
            for row_data in rows[:]:  # Iterate over a copy
                row_data["frame"].destroy()
            rows.clear()

        def add_row(front="", back="", hint=""):
            """Add a new row to the table"""
            row_num = len(rows) + 1

            row_frame = tk.Frame(rows_frame, bg=self.CARD_BG)
            row_frame.pack(fill=tk.X, pady=1)

            tk.Label(row_frame, text=str(row_num), font=('Segoe UI', 10),
                     bg=self.CARD_BG, fg=self.MUTED, width=4).pack(side=tk.LEFT)

            front_entry = tk.Entry(row_frame, font=('Segoe UI', 10), bg=self.BG, fg=self.TEXT,
                                   insertbackground=self.TEXT, relief='flat', width=28)
            front_entry.pack(side=tk.LEFT, padx=(5, 5))
            if front:
                front_entry.insert(0, front)

            back_entry = tk.Entry(row_frame, font=('Segoe UI', 10), bg=self.BG, fg=self.TEXT,
                                  insertbackground=self.TEXT, relief='flat', width=28)
            back_entry.pack(side=tk.LEFT, padx=(0, 5))
            if back:
                back_entry.insert(0, back)

            hint_entry = tk.Entry(row_frame, font=('Segoe UI', 10), bg=self.BG, fg=self.TEXT,
                                  insertbackground=self.TEXT, relief='flat', width=15)
            hint_entry.pack(side=tk.LEFT)
            if hint:
                hint_entry.insert(0, hint)

            # Delete button
            del_btn = tk.Button(row_frame, text="✕", font=('Segoe UI', 9),
                                bg=self.CARD_BG, fg=self.RED, cursor='hand2',
                                relief='flat', borderwidth=0)
            del_btn.pack(side=tk.RIGHT, padx=(5, 0))

            row_data = {
                "frame": row_frame,
                "front": front_entry,
                "back": back_entry,
                "hint": hint_entry,
                "del_btn": del_btn
            }
            rows.append(row_data)

            del_btn.config(command=lambda r=row_data: delete_row(r))

            update_row_numbers()
            canvas.yview_moveto(1.0)
            front_entry.focus_set()

            return row_data

        def delete_row(row_data):
            """Remove a row"""
            row_data["frame"].destroy()
            rows.remove(row_data)
            update_row_numbers()

        def update_row_numbers():
            """Update row numbers"""
            for i, row in enumerate(rows):
                for widget in row["frame"].winfo_children():
                    if isinstance(widget, tk.Label) and widget.cget("width") == 4:
                        widget.config(text=str(i + 1))

        # Add initial empty rows (just 1 empty row to start with)
        add_row()

        # Buttons below table
        btn_frame = tk.Frame(dialog, bg=self.CARD_BG)
        btn_frame.pack(fill=tk.X, padx=20, pady=10)

        tk.Button(btn_frame, text="+ Add Row", command=add_row,
                  bg=self.ACCENT, fg='white', font=('Segoe UI', 10, 'bold'),
                  padx=15, pady=6, cursor='hand2', relief='flat', borderwidth=0
                  ).pack(side=tk.LEFT)

        tk.Label(btn_frame, text="(or press Tab in last Hint field)",
                 font=('Segoe UI', 8), bg=self.CARD_BG, fg=self.MUTED).pack(side=tk.LEFT, padx=10)

        # OR divider
        sep_frame = tk.Frame(dialog, bg=self.CARD_BG)
        sep_frame.pack(fill=tk.X, padx=20, pady=5)
        tk.Frame(sep_frame, bg=self.MUTED, height=1).pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(sep_frame, text="  OR Import File  ", font=('Segoe UI', 10),
                 bg=self.CARD_BG, fg=self.MUTED).pack(side=tk.LEFT)
        tk.Frame(sep_frame, bg=self.MUTED, height=1).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Import section
        import_frame = tk.Frame(dialog, bg=self.CARD_BG)
        import_frame.pack(fill=tk.X, padx=20, pady=5)

        file_var = tk.StringVar()
        file_label = tk.Label(import_frame, text="No file selected",
                              font=('Segoe UI', 10), bg=self.BG, fg=self.MUTED,
                              anchor='w', padx=10, pady=6)
        file_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        def browse_file():
            fn = filedialog.askopenfilename(filetypes=[("CSV/Excel", "*.csv *.xlsx *.xls")])
            if fn:
                file_var.set(fn)
                file_label.config(text=f"✅ {os.path.basename(fn)}", fg=self.GREEN)
                # Clear existing rows first
                clear_all_rows()
                # Then add imported cards
                cards, _ = self.dm.import_cards(fn)
                if cards:
                    for card in cards:
                        add_row(card.front, card.back, card.hint)
                # If no cards were imported, add one empty row
                if len(rows) == 0:
                    add_row()

        tk.Button(import_frame, text="Browse...", command=browse_file,
                  bg=self.ACCENT, fg='white', font=('Segoe UI', 10),
                  padx=12, pady=6, cursor='hand2', relief='flat', borderwidth=0
                  ).pack(side=tk.RIGHT)

        # Save button
        bottom_frame = tk.Frame(dialog, bg=self.CARD_BG)
        bottom_frame.pack(fill=tk.X, padx=20, pady=15)

        def save_words():
            added = 0
            if not course.decks:
                course.decks.append(Deck("Main"))

            for row in rows:
                front = row["front"].get().strip()
                back = row["back"].get().strip()
                if front and back:
                    hint = row["hint"].get().strip()
                    course.decks[0].add_card(FlashCard(front, back, hint))
                    added += 1

            if added == 0:
                messagebox.showwarning("Error", "Add at least one word!", parent=dialog)
                return

            self.dm.save(self.courses)
            dialog.destroy()
            self._manage_course(course)
            messagebox.showinfo("Success", f"Added {added} words to {course.name}!")

        tk.Button(bottom_frame, text="✅ Add Words", command=save_words,
                  bg=self.GREEN, fg='white', font=('Segoe UI', 13, 'bold'),
                  padx=30, pady=12, cursor='hand2', relief='flat').pack(side=tk.RIGHT, padx=5)

        tk.Button(bottom_frame, text="Cancel", command=dialog.destroy,
                  bg=self.CARD_BG, fg=self.MUTED, font=('Segoe UI', 11),
                  cursor='hand2', relief='flat', borderwidth=0).pack(side=tk.RIGHT, padx=5)

        # Tab in last hint field adds new row
        def on_tab(event):
            if rows and event.widget == rows[-1]["hint"]:
                add_row()
                return "break"

        for row in rows:
            row["hint"].bind('<Tab>', on_tab)

# ===== START =====

if __name__ == "__main__":
    dm = DataManager()
    courses = dm.load()

    if not courses:
        course = Course("Basic Spanish")
        deck = Deck("Greetings")

        words = [
            ("Hola", "Hello"),
            ("Adiós", "Goodbye"),
            ("Gracias", "Thank you"),
            ("Por favor", "Please"),
            ("Buenos días", "Good morning"),
            ("Buenas noches", "Good night"),
            ("¿Cómo estás?", "How are you?"),
            ("Estoy bien", "I'm fine"),
            ("Sí", "Yes"),
            ("No", "No"),
        ]

        for f, b in words:
            deck.add_card(FlashCard(f, b))

        course.add_deck(deck)
        dm.save([course])

    app = MemorizeApp()
    app.run()