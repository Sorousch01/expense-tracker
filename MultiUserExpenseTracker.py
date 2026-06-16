



import sqlite3
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
import os
from datetime import datetime, timedelta
import csv
from tabulate import tabulate
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # For non-interactive environments

# ==================== USER MANAGER CLASS ====================
class UserManager:
    def __init__(self, db_name="expense_tracker.db"):  # Single database
        self.db_name = db_name
        self.ph = PasswordHasher()
        self.init_db()  # Create users table

    def init_db(self):
        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            c.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()

    def register(self, username, email, password):
        """Register a new user using Argon2 hashing."""
        try:
            # Argon2 automatically generates and stores salt in the hash
            password_hash = self.ph.hash(password)

            with sqlite3.connect(self.db_name) as conn:
                c = conn.cursor()
                c.execute('''
                    INSERT INTO users (username, email, password_hash)
                    VALUES (?, ?, ?)
                ''', (username, email, password_hash))
                conn.commit()
            return True

        except sqlite3.IntegrityError:
            print("Username or email already exists!")
            return False
        except Exception as e:
            print(f"Registration error: {e}")
            return False

    def login(self, username, password):
        """Login using username OR email."""
        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            # This single query handles both cases correctly
            c.execute('''
                SELECT id, password_hash FROM users 
                WHERE username = ? OR email = ?
            ''', (username, username))
            user = c.fetchone()

            if user:
                user_id, stored_hash = user
                try:
                    self.ph.verify(stored_hash, password)
                    return user_id
                except VerifyMismatchError:
                    return None
            return None

    def get_user_by_id(self, user_id):
        """Return user info for a given user_id."""
        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            c.execute('''
                SELECT id, username, email, created_at 
                FROM users WHERE id = ?
            ''', (user_id,))
            user = c.fetchone()

            if user:
                return {
                    'id': user[0],
                    'username': user[1],
                    'email': user[2],
                    'created_at': user[3]
                }
            return None


# ==================== EXPENSE TRACKER CLASS ====================
class ExpenseTracker:
    def __init__(self, db_name="expense_tracker.db", user_id=None):  # Same database
        self.db_name = db_name
        self.user_id = user_id
        self.init_db()  # Create expenses table

    def init_db(self):
        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            # Create expenses table
            c.execute('''
                CREATE TABLE IF NOT EXISTS expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    category TEXT NOT NULL,
                    date TEXT NOT NULL,
                    description TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')

            # Budgets table
            c.execute('''
                CREATE TABLE IF NOT EXISTS budgets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    monthly_limit REAL NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users (id),
                    UNIQUE(user_id, category)
                )
            ''')

            # NEW: Recurring expenses table
            c.execute('''
                CREATE TABLE IF NOT EXISTS recurring_expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT,
                    day_of_month INTEGER NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT,
                    last_processed TEXT,
                    active BOOLEAN DEFAULT 1,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')

            conn.commit()

    def add_expense(self, amount, category, date, description=""):
        """Add a new expense for the current user."""
        if self.user_id is None:
            print("❌ Error: No user logged in!")
            return False

        try:
            with sqlite3.connect(self.db_name) as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT INTO expenses (user_id, amount, category, date, description)
                    VALUES (?, ?, ?, ?, ?)
                """, (self.user_id, amount, category, date, description))
                conn.commit()

                expense_id = c.lastrowid

                # Check budget status after adding
                budget = self.get_budget(category)
                if budget:
                    # Get current month spending for this category
                    start_date = datetime.now().strftime("%Y-%m-01")
                    end_date = (datetime.now().replace(day=28) + timedelta(days=4)).replace(day=1).strftime("%Y-%m-%d")

                    c.execute("""
                        SELECT COALESCE(SUM(amount), 0)
                        FROM expenses
                        WHERE user_id = ? AND category = ? AND date >= ? AND date < ?
                    """, (self.user_id, category, start_date, end_date))
                    spent = c.fetchone()[0]

                    percentage = (spent / budget * 100) if budget > 0 else 0

                    if percentage >= 100:
                        print(f"⚠️ WARNING: You have EXCEEDED your €{budget:.2f} budget for '{category}'!")
                        print(f"   Current spending: €{spent:.2f} ({percentage:.1f}% of budget)")
                    elif percentage >= 80:
                        print(f"⚡ ALERT: You've used {percentage:.1f}% of your €{budget:.2f} budget for '{category}'")
                        print(f"   Remaining: €{budget - spent:.2f}")

                if description:
                    print(f"✓ Expense #{expense_id} added: €{amount:.2f} for {category} on {date} - {description}")
                else:
                    print(f"✓ Expense #{expense_id} added: €{amount:.2f} for {category} on {date}")
                return True

        except sqlite3.Error as e:
            print(f"❌ Database error: {e}")
            return False
        except Exception as e:
            print(f"❌ Error adding expense: {e}")
            return False

    def get_expenses(self, start_date=None, end_date=None):
        """Return expenses for the current user, filtered by date range."""
        if self.user_id is None:
            print("❌ Error: No user logged in!")
            return []

        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()

            # Base query with user_id filter
            query = "SELECT id, amount, category, date, description FROM expenses WHERE user_id = ?"
            params = [self.user_id]

            # Date conditions
            conditions = []

            if start_date:
                if self.validate_date(start_date):
                    conditions.append("date >= ?")
                    params.append(start_date)
                else:
                    print(f"Warning: Invalid start date '{start_date}' ignored.")

            if end_date:
                if self.validate_date(end_date):
                    conditions.append("date <= ?")
                    params.append(end_date)
                else:
                    print(f"Warning: Invalid end date '{end_date}' ignored.")

            # Add date conditions
            if conditions:
                query += " AND " + " AND ".join(conditions)

            query += " ORDER BY date DESC"

            c.execute(query, params)
            return c.fetchall()

    def show_expenses(self, rows):
        """Print expenses in a formatted table."""
        if not rows:
            print("No expenses found.")
            return
        table = []
        for row in rows:
            desc = (row[4] or "")[:30]
            table.append([row[0], f"{row[1]:.2f}", row[2], row[3], desc])
        print(tabulate(table, headers=["ID", "Amount", "Category", "Date", "Description"], tablefmt="fancy_grid"))

    def get_summary(self, start_date=None, end_date=None):
        """Return total expenses and breakdown by category for the current user."""
        # Validate dates first
        if start_date and not self.validate_date(start_date):
            print(f"Warning: Invalid start date '{start_date}' ignored.")
            start_date = None

        if end_date and not self.validate_date(end_date):
            print(f"Warning: Invalid end date '{end_date}' ignored.")
            end_date = None

        if self.user_id is None:
            print("❌ Error: No user logged in!")
            return 0, []

        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()

            # Start with user_id filter
            params = [self.user_id]  # ← ALWAYS filter by current user
            where_clause = ""

            # Add date conditions
            if start_date and end_date:
                where_clause += " AND date BETWEEN ? AND ?"  # ← Use AND, not WHERE
                params.extend([start_date, end_date])
            elif start_date:
                where_clause += " AND date >= ?"
                params.append(start_date)
            elif end_date:
                where_clause += " AND date <= ?"
                params.append(end_date)

            # Total expenses (all categories combined)
            query_total = f"SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE user_id = ? {where_clause}"
            c.execute(query_total, params)
            total_expenses = c.fetchone()[0]

            # Total expenses by category
            query_by_category = f"""
                SELECT category, COALESCE(SUM(amount), 0) as total
                FROM expenses WHERE user_id = ? {where_clause}
                GROUP BY category
                ORDER BY total DESC
            """
            c.execute(query_by_category, params)
            total_expenses_by_category = c.fetchall()

            return total_expenses, total_expenses_by_category

    def show_summary(self, start_date=None, end_date=None):
        """Print summary (total + per category)."""
        total_expenses, total_expenses_by_category = self.get_summary(start_date, end_date)

        # Check if total is 0 first
        if total_expenses == 0:
            print("No expenses found in this period.")
            return

        print(f"\n💰 Total spent: €{total_expenses:.2f}")

        # Now we know there are expenses
        table = [[cat, f"{amt:.2f}"] for cat, amt in total_expenses_by_category]
        print("\n📊 By category:")
        print(tabulate(table, headers=["Category", "Amount"], tablefmt="grid"))

    def delete_expense(self, expense_id):
        """Delete an expense by ID (only if it belongs to current user)."""
        if self.user_id is None:
            print("❌ Error: No user logged in!")
            return False

        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()

            # Optional: First check if expense exists and belongs to user
            c.execute("SELECT id FROM expenses WHERE id = ? AND user_id = ?",
                      (expense_id, self.user_id))
            expense = c.fetchone()

            if not expense:
                print("❌ Expense not found or doesn't belong to you.")
                return False

            # Delete it
            c.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
            conn.commit()
            print(f"✓ Expense {expense_id} deleted.")
            return True

    def export_to_csv(self, filename=None, username=None):
        """Export all expenses for the current user to a CSV file."""

        # Get expenses
        rows = self.get_expenses()
        if not rows:
            print("No expenses to export.")
            return False

        # Generate filename with timestamp and username
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if username:
                # Clean username to be filesystem-safe
                safe_username = "".join(c for c in username if c.isalnum() or c in "._-")
                filename = f"{safe_username}_expenses_{timestamp}.csv"
            else:
                filename = f"expenses_{timestamp}.csv"

        try:
            with open(filename, 'w', newline='', encoding='utf-8') as f:
                # Use DictWriter for cleaner code
                fieldnames = ["ID", "Amount", "Category", "Date", "Description"]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()

                # Show progress for large exports
                total_rows = len(rows)
                print(f"Exporting {total_rows} expenses to {filename}...")

                for i, row in enumerate(rows, 1):
                    writer.writerow({
                        "ID": row[0],
                        "Amount": f"{row[1]:.2f}",
                        "Category": row[2],
                        "Date": row[3],
                        "Description": row[4] or ""
                    })

                    # Progress indicator every 100 rows or on last row
                    if i % 100 == 0 or i == total_rows:
                        print(f"  Exported {i}/{total_rows} expenses...")

            print(f"✓ Successfully exported {total_rows} expenses to {filename}")
            return True

        except PermissionError:
            print(
                f"❌ Error: Cannot write to {filename}. File may be open in another program or you don't have permission.")
            return False
        except IsADirectoryError:
            print(f"❌ Error: {filename} is a directory. Please provide a filename, not a folder name.")
            return False
        except OSError as e:
            print(f"❌ Error: Cannot write to file. {e}")
            return False
        except Exception as e:
            print(f"❌ Unexpected error exporting to CSV: {e}")
            return False

    def validate_date(self, date_string):
        """Validate date in YYYY-MM-DD format."""
        try:
            datetime.strptime(date_string, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    def edit_expense(self, expense_id, amount=None, category=None, date=None, description=None):
        """Edit an existing expense (only if it belongs to current user)."""
        if self.user_id is None:
            print("❌ Error: No user logged in!")
            return False

        # First, check if expense exists and belongs to user
        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM expenses WHERE id = ? AND user_id = ?", (expense_id, self.user_id))
            expense = c.fetchone()

            if not expense:
                print("❌ Expense not found or doesn't belong to you.")
                return False

            # Get current values
            current_amount, current_category, current_date, current_description = expense[1], expense[2], expense[3], \
            expense[4]

            # Use new values if provided, otherwise keep current
            new_amount = amount if amount is not None else current_amount
            new_category = category if category is not None else current_category
            new_date = date if date is not None else current_date
            new_description = description if description is not None else current_description

            # Update the expense
            c.execute("""
                UPDATE expenses 
                SET amount = ?, category = ?, date = ?, description = ?
                WHERE id = ? AND user_id = ?
            """, (new_amount, new_category, new_date, new_description, expense_id, self.user_id))

            conn.commit()
            print(f"✓ Expense {expense_id} updated successfully!")
            return True

    def set_budget(self, category, monthly_limit):
        """Set or update a monthly budget for a category."""
        if self.user_id is None:
            print("❌ Error: No user logged in!")
            return False

        if monthly_limit <= 0:
            print("❌ Budget must be greater than 0!")
            return False

        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()

            # Check if budget exists
            c.execute("SELECT id FROM budgets WHERE user_id = ? AND category = ?",
                      (self.user_id, category))
            existing = c.fetchone()

            if existing:
                # Update existing budget
                c.execute("""
                    UPDATE budgets SET monthly_limit = ? 
                    WHERE user_id = ? AND category = ?
                """, (monthly_limit, self.user_id, category))
                print(f"✓ Budget updated: €{monthly_limit:.2f} per month for '{category}'")
            else:
                # Insert new budget
                c.execute("""
                    INSERT INTO budgets (user_id, category, monthly_limit)
                    VALUES (?, ?, ?)
                """, (self.user_id, category, monthly_limit))
                print(f"✓ Budget set: €{monthly_limit:.2f} per month for '{category}'")

            conn.commit()
            return True

    def get_budget(self, category):
        """Get the monthly budget for a category."""
        if self.user_id is None:
            return None

        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            c.execute("SELECT monthly_limit FROM budgets WHERE user_id = ? AND category = ?",
                      (self.user_id, category))
            result = c.fetchone()
            return result[0] if result else None

    def get_all_budgets(self):
        """Get all budgets for the current user."""
        if self.user_id is None:
            return []

        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            c.execute("SELECT category, monthly_limit FROM budgets WHERE user_id = ? ORDER BY category",
                      (self.user_id,))
            return c.fetchall()

    def get_budget_status(self, month=None, year=None):
        """Get spending vs budget for all categories in a given month."""
        if self.user_id is None:
            print("❌ Error: No user logged in!")
            return []

        if month is None:
            month = datetime.now().month
        if year is None:
            year = datetime.now().year

        # Get all budgets
        budgets = self.get_all_budgets()
        if not budgets:
            return []

        # Get spending for this month
        start_date = f"{year:04d}-{month:02d}-01"
        # Calculate end of month
        if month == 12:
            end_date = f"{year + 1:04d}-01-01"
        else:
            end_date = f"{year:04d}-{month + 1:02d}-01"

        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            results = []

            for category, limit in budgets:
                c.execute("""
                    SELECT COALESCE(SUM(amount), 0)
                    FROM expenses
                    WHERE user_id = ? AND category = ? AND date >= ? AND date < ?
                """, (self.user_id, category, start_date, end_date))

                spent = c.fetchone()[0]
                remaining = limit - spent
                percentage = (spent / limit * 100) if limit > 0 else 0

                # Determine status
                if percentage >= 100:
                    status = "🔴 EXCEEDED"
                elif percentage >= 80:
                    status = "🟡 WARNING"
                else:
                    status = "🟢 OK"

                results.append({
                    'category': category,
                    'limit': limit,
                    'spent': spent,
                    'remaining': remaining,
                    'percentage': percentage,
                    'status': status
                })

            return results

    def show_budget_status(self, month=None, year=None):
        """Display budget status in a formatted table."""
        status = self.get_budget_status(month, year)

        if not status:
            print("No budgets set. Use 'Set budget' to create one.")
            return

        if month is None:
            month = datetime.now().month
        if year is None:
            year = datetime.now().year

        print(f"\n📊 Budget Status for {datetime(year, month, 1).strftime('%B %Y')}")
        print("-" * 70)

        table = []
        for item in status:
            table.append([
                item['category'],
                f"€{item['limit']:.2f}",
                f"€{item['spent']:.2f}",
                f"€{item['remaining']:.2f}",
                f"{item['percentage']:.1f}%",
                item['status']
            ])

        print(tabulate(table,
                       headers=["Category", "Budget", "Spent", "Remaining", "Used %", "Status"],
                       tablefmt="fancy_grid"))

    def get_category_spending(self, start_date=None, end_date=None):
        """Get spending breakdown by category for date range."""
        if self.user_id is None:
            print("❌ Error: No user logged in!")
            return {}

        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()

            # Build WHERE clause
            params = [self.user_id]
            where_clause = "WHERE user_id = ?"

            if start_date and self.validate_date(start_date):
                where_clause += " AND date >= ?"
                params.append(start_date)

            if end_date and self.validate_date(end_date):
                where_clause += " AND date <= ?"
                params.append(end_date)

            c.execute(f"""
                SELECT category, COALESCE(SUM(amount), 0)
                FROM expenses
                {where_clause}
                GROUP BY category
                ORDER BY SUM(amount) DESC
            """, params)

            return dict(c.fetchall())

    def get_monthly_trend(self, category=None, months=6):
        """Get monthly spending trend for the last N months."""
        if self.user_id is None:
            print("❌ Error: No user logged in!")
            return {}, []

        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()

            # Get last N months
            months_list = []
            for i in range(months - 1, -1, -1):
                date = datetime.now() - timedelta(days=30 * i)
                months_list.append(date.strftime("%Y-%m"))

            results = {}

            if category:
                # Specific category
                spending = []
                for month in months_list:
                    start = f"{month}-01"
                    # End of month
                    year, mon = month.split('-')
                    if int(mon) == 12:
                        end = f"{int(year) + 1}-01-01"
                    else:
                        end = f"{year}-{int(mon) + 1:02d}-01"

                    c.execute("""
                        SELECT COALESCE(SUM(amount), 0)
                        FROM expenses
                        WHERE user_id = ? AND category = ? AND date >= ? AND date < ?
                    """, (self.user_id, category, start, end))
                    spending.append(c.fetchone()[0])

                results[category] = spending
            else:
                # All categories
                c.execute("SELECT DISTINCT category FROM expenses WHERE user_id = ?", (self.user_id,))
                categories = [row[0] for row in c.fetchall()]

                for cat in categories:
                    spending = []
                    for month in months_list:
                        start = f"{month}-01"
                        year, mon = month.split('-')
                        if int(mon) == 12:
                            end = f"{int(year) + 1}-01-01"
                        else:
                            end = f"{year}-{int(mon) + 1:02d}-01"

                        c.execute("""
                            SELECT COALESCE(SUM(amount), 0)
                            FROM expenses
                            WHERE user_id = ? AND category = ? AND date >= ? AND date < ?
                        """, (self.user_id, cat, start, end))
                        spending.append(c.fetchone()[0])

                    results[cat] = spending

            return results, months_list

    def show_pie_chart(self, start_date=None, end_date=None, save=False):
        """Display a pie chart of spending by category."""
        data = self.get_category_spending(start_date, end_date)

        if not data:
            print("No data to visualize.")
            return

        # Remove categories with zero spending
        data = {k: v for k, v in data.items() if v > 0}

        if not data:
            print("No spending data to show.")
            return

        # Create pie chart
        categories = list(data.keys())
        amounts = list(data.values())

        # Colors for categories
        colors = plt.cm.Set3(range(len(categories)))

        fig, ax = plt.subplots(figsize=(10, 7))

        # Create pie chart with percentage
        wedges, texts, autotexts = ax.pie(
            amounts,
            labels=categories,
            autopct='%1.1f%%',
            colors=colors,
            startangle=90,
            textprops={'fontsize': 11},
            pctdistance=0.85
        )

        # Make percentage text bold and white for contrast
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontweight('bold')

        # Title
        title = "Spending by Category"
        if start_date and end_date:
            title += f" ({start_date} to {end_date})"
        elif start_date:
            title += f" (from {start_date})"
        elif end_date:
            title += f" (until {end_date})"

        ax.set_title(title, fontsize=16, fontweight='bold', pad=20)

        # Show total
        total = sum(amounts)
        ax.text(0, -1.2, f"Total: €{total:.2f}",
                fontsize=12, ha='center', va='center')

        plt.tight_layout()

        if save:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"pie_chart_{timestamp}.png"
            plt.savefig(filename, dpi=300, bbox_inches='tight')
            print(f"✓ Chart saved as {filename}")
        else:
            plt.show()

    def show_bar_chart(self, start_date=None, end_date=None, save=False):
        """Display a bar chart of spending by category."""
        data = self.get_category_spending(start_date, end_date)

        if not data:
            print("No data to visualize.")
            return

        # Remove categories with zero spending
        data = {k: v for k, v in data.items() if v > 0}

        if not data:
            print("No spending data to show.")
            return

        categories = list(data.keys())
        amounts = list(data.values())

        # Colors based on amount (green to red)
        max_amount = max(amounts) if amounts else 1
        colors = ['green' if a < max_amount * 0.5 else
                  'orange' if a < max_amount * 0.8 else
                  'red' for a in amounts]

        fig, ax = plt.subplots(figsize=(12, 6))

        bars = ax.bar(categories, amounts, color=colors, edgecolor='black', linewidth=0.5)

        # Add value labels on top of bars
        for bar, amount in zip(bars, amounts):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2., height + 0.01 * max_amount,
                    f'€{amount:.2f}', ha='center', va='bottom', fontsize=10)

        # Title
        title = "Spending by Category"
        if start_date and end_date:
            title += f" ({start_date} to {end_date})"
        elif start_date:
            title += f" (from {start_date})"
        elif end_date:
            title += f" (until {end_date})"

        ax.set_title(title, fontsize=16, fontweight='bold', pad=20)
        ax.set_xlabel('Category', fontsize=12)
        ax.set_ylabel('Amount (€)', fontsize=12)

        # Rotate x-axis labels if many categories
        if len(categories) > 5:
            plt.xticks(rotation=45, ha='right')

        # Add total
        total = sum(amounts)
        ax.text(0.02, 0.98, f'Total: €{total:.2f}',
                transform=ax.transAxes, fontsize=12,
                verticalalignment='top', bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

        plt.tight_layout()

        if save:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"bar_chart_{timestamp}.png"
            plt.savefig(filename, dpi=300, bbox_inches='tight')
            print(f"✓ Chart saved as {filename}")
        else:
            plt.show()

    def show_trend_chart(self, category=None, months=6, save=False):
        """Display a line chart of spending trends."""
        if not category:
            # If no category, ask user
            data = self.get_category_spending()
            if not data:
                print("No data to visualize.")
                return
            categories = list(data.keys())
            print("\nAvailable categories:")
            for i, cat in enumerate(categories, 1):
                print(f"{i}. {cat}")
            try:
                choice = int(input("Choose category (enter number): "))
                if 1 <= choice <= len(categories):
                    category = categories[choice - 1]
                else:
                    print("Invalid choice.")
                    return
            except ValueError:
                print("Invalid input.")
                return

        results, months_list = self.get_monthly_trend(category, months)

        if category not in results:
            print(f"No data found for '{category}'")
            return

        spending = results[category]

        fig, ax = plt.subplots(figsize=(10, 6))

        # Convert month labels to readable format
        month_labels = [datetime.strptime(m, "%Y-%m").strftime("%b %Y") for m in months_list]

        ax.plot(month_labels, spending, marker='o', linewidth=2, markersize=8, color='#3b82f6')
        ax.fill_between(month_labels, 0, spending, alpha=0.3, color='#3b82f6')

        # Add value labels
        for i, (label, value) in enumerate(zip(month_labels, spending)):
            ax.annotate(f'€{value:.2f}',
                        (i, value),
                        textcoords="offset points",
                        xytext=(0, 10),
                        ha='center',
                        fontsize=9)

        ax.set_title(f"Spending Trend: {category}", fontsize=16, fontweight='bold', pad=20)
        ax.set_xlabel('Month', fontsize=12)
        ax.set_ylabel('Amount (€)', fontsize=12)
        ax.grid(True, alpha=0.3)

        plt.tight_layout()

        if save:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"trend_chart_{timestamp}.png"
            plt.savefig(filename, dpi=300, bbox_inches='tight')
            print(f"✓ Chart saved as {filename}")
        else:
            plt.show()

    def add_recurring_expense(self, amount, category, day_of_month, description="", start_date=None, end_date=None):
        """Add a monthly recurring expense."""
        if self.user_id is None:
            print("❌ Error: No user logged in!")
            return False

        if not (1 <= day_of_month <= 28):
            print("❌ Day of month must be between 1 and 28 (to handle all months)")
            return False

        if start_date is None:
            start_date = datetime.now().strftime("%Y-%m-%d")
        elif not self.validate_date(start_date):
            print("❌ Invalid start date.")
            return False

        if end_date and not self.validate_date(end_date):
            print("❌ Invalid end date.")
            return False

        try:
            with sqlite3.connect(self.db_name) as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT INTO recurring_expenses 
                    (user_id, amount, category, description, day_of_month, start_date, end_date, active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 1)
                """, (self.user_id, amount, category, description, day_of_month, start_date, end_date))
                conn.commit()
                recurring_id = c.lastrowid
                print(f"✓ Recurring expense #{recurring_id} added: €{amount:.2f} for {category} on day {day_of_month}")
                return True
        except sqlite3.Error as e:
            print(f"❌ Database error: {e}")
            return False

    def get_recurring_expenses(self, active_only=True):
        """Get all recurring expenses for the current user."""
        if self.user_id is None:
            print("❌ Error: No user logged in!")
            return []

        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            if active_only:
                c.execute("""
                    SELECT id, amount, category, description, day_of_month, start_date, end_date, last_processed, active
                    FROM recurring_expenses
                    WHERE user_id = ? AND active = 1
                    ORDER BY day_of_month
                """, (self.user_id,))
            else:
                c.execute("""
                    SELECT id, amount, category, description, day_of_month, start_date, end_date, last_processed, active
                    FROM recurring_expenses
                    WHERE user_id = ?
                    ORDER BY active DESC, day_of_month
                """, (self.user_id,))
            return c.fetchall()

    def process_recurring_expenses(self, target_date=None):
        """Process all recurring expenses for the target date."""
        if self.user_id is None:
            print("❌ Error: No user logged in!")
            return False

        if target_date is None:
            target_date = datetime.now().strftime("%Y-%m-%d")

        # Get all active recurring expenses
        recurring = self.get_recurring_expenses(active_only=True)
        if not recurring:
            print("No active recurring expenses.")
            return False

        processed = 0
        target = datetime.strptime(target_date, "%Y-%m-%d")

        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()

            for rec in recurring:
                rec_id, amount, category, description, day, start_date, end_date, last_processed, active = rec

                # Check if within date range
                if start_date and target_date < start_date:
                    continue
                if end_date and target_date > end_date:
                    continue

                # Check if already processed this month
                if last_processed:
                    last = datetime.strptime(last_processed, "%Y-%m-%d")
                    if last.month == target.month and last.year == target.year:
                        continue  # Already processed this month

                # Check if day has passed or is today
                # For day 29,30,31 we need to handle months with fewer days
                if day > 28:
                    # Check if this month has this day
                    last_day = self._get_last_day_of_month(target.year, target.month)
                    if day > last_day:
                        # Use the last day of the month
                        day = last_day

                # Create the expense date for this month
                expense_date = f"{target.year:04d}-{target.month:02d}-{day:02d}"

                # Only process if target date is on or after the expense date
                if target_date > expense_date:
                    # This expense should have been processed earlier
                    continue

                if target_date != expense_date:
                    continue  # Only process on the exact day

                # Add the expense
                desc = f"{description} (recurring)" if description else f"Recurring {category}"
                try:
                    c.execute("""
                        INSERT INTO expenses (user_id, amount, category, date, description)
                        VALUES (?, ?, ?, ?, ?)
                    """, (self.user_id, amount, category, target_date, desc))

                    # Update last_processed
                    c.execute("""
                        UPDATE recurring_expenses
                        SET last_processed = ?
                        WHERE id = ?
                    """, (target_date, rec_id))

                    conn.commit()
                    processed += 1
                    print(f"✓ Added recurring expense: €{amount:.2f} for {category} on {target_date}")

                except sqlite3.Error as e:
                    print(f"❌ Error processing recurring expense {rec_id}: {e}")

        if processed == 0:
            print(f"No recurring expenses due on {target_date}")
        else:
            print(f"✅ Processed {processed} recurring expense(s)")

        return True

    def _get_last_day_of_month(self, year, month):
        """Helper: Get the last day of a given month."""
        import calendar
        return calendar.monthrange(year, month)[1]

    def process_all_recurring_expenses(self, look_ahead_days=0):
        """Process all recurring expenses from last processed date until today."""
        if self.user_id is None:
            print("❌ Error: No user logged in!")
            return False

        # Get all recurring expenses
        recurring = self.get_recurring_expenses(active_only=True)
        if not recurring:
            print("No active recurring expenses.")
            return False

        # Get date range
        today = datetime.now()
        start_date = datetime(today.year, today.month, 1).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")

        print(f"Processing recurring expenses from {start_date} to {end_date}...")

        # For each day in the month
        current = datetime.strptime(start_date, "%Y-%m-%d")
        processed_total = 0

        while current <= today:
            current_date = current.strftime("%Y-%m-%d")
            self.process_recurring_expenses(current_date)
            current += timedelta(days=1)

        return True

    def delete_recurring_expense(self, recurring_id):
        """Delete (deactivate) a recurring expense."""
        if self.user_id is None:
            print("❌ Error: No user logged in!")
            return False

        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            # Check if it belongs to user
            c.execute("SELECT id FROM recurring_expenses WHERE id = ? AND user_id = ?",
                      (recurring_id, self.user_id))
            if not c.fetchone():
                print("❌ Recurring expense not found or doesn't belong to you.")
                return False

            # Delete it
            c.execute("DELETE FROM recurring_expenses WHERE id = ?", (recurring_id,))
            conn.commit()
            print(f"✓ Recurring expense {recurring_id} deleted.")
            return True

    def toggle_recurring_expense(self, recurring_id):
        """Toggle active status of a recurring expense."""
        if self.user_id is None:
            print("❌ Error: No user logged in!")
            return False

        with sqlite3.connect(self.db_name) as conn:
            c = conn.cursor()
            c.execute("SELECT active FROM recurring_expenses WHERE id = ? AND user_id = ?",
                      (recurring_id, self.user_id))
            result = c.fetchone()
            if not result:
                print("❌ Recurring expense not found or doesn't belong to you.")
                return False

            new_status = 0 if result[0] else 1
            status_text = "activated" if new_status else "deactivated"

            c.execute("UPDATE recurring_expenses SET active = ? WHERE id = ?",
                      (new_status, recurring_id))
            conn.commit()
            print(f"✓ Recurring expense {recurring_id} {status_text}.")
            return True

    def show_recurring_expenses(self):
        """Display all recurring expenses in a formatted table."""
        recurring = self.get_recurring_expenses(active_only=False)

        if not recurring:
            print("No recurring expenses.")
            return

        table = []
        for rec in recurring:
            rec_id, amount, category, description, day, start_date, end_date, last_processed, active = rec
            status = "✅ Active" if active else "❌ Inactive"
            desc = description or "-"
            last = last_processed or "Never"
            date_range = f"{start_date}"
            if end_date:
                date_range += f" → {end_date}"

            table.append([rec_id, f"€{amount:.2f}", category, desc, day, date_range, last, status])

        print(tabulate(table,
                       headers=["ID", "Amount", "Category", "Description", "Day", "Date Range", "Last Processed",
                                "Status"],
                       tablefmt="fancy_grid"))


# ==================== MAIN MENU ====================
def main():
    user_manager = UserManager()
    print("Welcome to Multi-User Expense Tracker")

    while True:
        print("\n--- Main Menu ---")
        print("1. Register")
        print("2. Login")
        print("3. Exit")
        choice = input("Choose: ")

        if choice == '1':
            print("\n--- Registration ---")
            username = input("Username: ")
            email = input("Email: ")
            password = input("Password: ")

            if user_manager.register(username, email, password):
                print("✓ Registration successful! You can now login.")
            else:
                print("✗ Registration failed.")

        elif choice == '2':
            print("\n--- Login ---")
            identifier = input("Username or email: ")
            password = input("Password: ")

            user_id = user_manager.login(identifier, password)
            if user_id:
                # Get username for export filename
                user_info = user_manager.get_user_by_id(user_id)
                username = user_info['username'] if user_info else None
                print(f"✓ Welcome back, {identifier}!")
                expense_tracker_menu(user_id, username)
            else:
                print("✗ Invalid credentials.")

        elif choice == '3':
            print("Goodbye!")
            break

        else:
            print("Invalid choice. Please enter 1, 2, or 3.")


def expense_tracker_menu(user_id, username=None):
    """Display the expense tracker menu for a logged-in user."""
    tracker = ExpenseTracker(user_id=user_id)

    # Helper function to get date range
    def get_date_range(days):
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        return start_date, end_date

    while True:
        print("\n--- Expense Tracker ---")
        print("1. Add expense")
        print("2. View last 7 days")
        print("3. View last 30 days")
        print("4. View custom date range")
        print("5. Show summary (last 30 days)")
        print("6. Edit expense")
        print("7. Delete expense")
        print("8. Export all to CSV")
        print("9. Budget Management")
        print("10. Data Visualization")
        print("11. Recurring Expenses")
        print("12. Logout")
        choice = input("Choose: ")

        if choice == '1':
            # Add expense
            try:
                amount = float(input("Amount (€): "))
                category = input("Category: ")
                date = input("Date (YYYY-MM-DD) or press Enter for today: ")
                if not date:
                    date = datetime.now().strftime("%Y-%m-%d")
                elif not tracker.validate_date(date):
                    print("❌ Invalid date format. Using today's date.")
                    date = datetime.now().strftime("%Y-%m-%d")

                description = input("Description (optional): ")
                tracker.add_expense(amount, category, date, description)
            except ValueError:
                print("❌ Invalid amount. Please enter a number.")

        elif choice == '2':
            # View last 7 days
            start_date, end_date = get_date_range(7)
            rows = tracker.get_expenses(start_date, end_date)
            tracker.show_expenses(rows)

        elif choice == '3':
            # View last 30 days
            start_date, end_date = get_date_range(30)
            rows = tracker.get_expenses(start_date, end_date)
            tracker.show_expenses(rows)

        elif choice == '4':
            # View custom date range
            start_date = input("Start date (YYYY-MM-DD): ")
            end_date = input("End date (YYYY-MM-DD): ")

            if start_date and not tracker.validate_date(start_date):
                print("❌ Invalid start date format.")
                continue
            if end_date and not tracker.validate_date(end_date):
                print("❌ Invalid end date format.")
                continue

            rows = tracker.get_expenses(start_date, end_date)
            tracker.show_expenses(rows)

        elif choice == '5':
            # Show summary (last 30 days)
            start_date, end_date = get_date_range(30)
            tracker.show_summary(start_date, end_date)

        elif choice == '6':
            # Edit expense
            try:
                # First show recent expenses so user knows IDs
                print("\nYour recent expenses:")
                rows = tracker.get_expenses()
                if not rows:
                    print("No expenses to edit.")
                    continue
                tracker.show_expenses(rows[:10])  # Show last 10

                expense_id = int(input("\nExpense ID to edit: "))
                print("Leave blank to keep current value")

                # Get current expense info
                current = None
                for row in rows:
                    if row[0] == expense_id:
                        current = row
                        break

                if not current:
                    print("❌ Expense not found.")
                    continue

                print(f"\nCurrent: €{current[1]:.2f} - {current[2]} on {current[3]} - {current[4] or 'No description'}")
                print("\nEnter new values (press Enter to keep current):")

                amount = input("New amount (€): ")
                amount = float(amount) if amount else None

                category = input("New category: ") or None

                date = input("New date (YYYY-MM-DD): ")
                if date and not tracker.validate_date(date):
                    print("❌ Invalid date format. Keeping current date.")
                    date = None

                description = input("New description: ") or None

                tracker.edit_expense(expense_id, amount, category, date, description)

            except ValueError:
                print("❌ Invalid input. Please enter numbers where required.")

        elif choice == '7':
            # Delete expense
            try:
                # Show recent expenses first
                print("\nYour recent expenses:")
                rows = tracker.get_expenses()
                if not rows:
                    print("No expenses to delete.")
                    continue
                tracker.show_expenses(rows[:10])

                expense_id = int(input("\nExpense ID to delete: "))
                tracker.delete_expense(expense_id)
            except ValueError:
                print("❌ Invalid ID. Please enter a number.")

        elif choice == '8':
            # Export all to CSV
            tracker.export_to_csv(username=username)

        elif choice == '9':
            # Budget Management
            while True:
                print("\n--- Budget Management ---")
                print("1. Set/Update budget")
                print("2. View budget status")
                print("3. View all budgets")
                print("4. Delete budget")
                print("5. Back to main menu")
                budget_choice = input("Choose: ")

                if budget_choice == '1':
                    # Set budget
                    category = input("Category: ")
                    try:
                        limit = float(input("Monthly limit (€): "))
                        tracker.set_budget(category, limit)
                    except ValueError:
                        print("❌ Invalid amount. Please enter a number.")

                elif budget_choice == '2':
                    # View budget status
                    tracker.show_budget_status()

                elif budget_choice == '3':
                    # View all budgets
                    budgets = tracker.get_all_budgets()
                    if not budgets:
                        print("No budgets set.")
                    else:
                        print("\n📋 Your budgets:")
                        table = [[cat, f"€{limit:.2f}"] for cat, limit in budgets]
                        print(tabulate(table, headers=["Category", "Monthly Budget"], tablefmt="grid"))

                elif budget_choice == '4':
                    # Delete budget
                    category = input("Category to remove budget for: ")
                    with sqlite3.connect(tracker.db_name) as conn:
                        c = conn.cursor()
                        c.execute("DELETE FROM budgets WHERE user_id = ? AND category = ?",
                                  (tracker.user_id, category))
                        if c.rowcount > 0:
                            conn.commit()
                            print(f"✓ Budget removed for '{category}'")
                        else:
                            print(f"❌ No budget found for '{category}'")

                elif budget_choice == '5':
                    break

                else:
                    print("Invalid choice.")

        elif choice == '10':
            print("Logging out...")
            break

        elif choice == '11':
            # Recurring Expenses
            while True:
                print("\n🔄 Recurring Expenses")
                print("1. Add recurring expense")
                print("2. View recurring expenses")
                print("3. Process recurring expenses")
                print("4. Process all (catch up)")
                print("5. Delete recurring expense")
                print("6. Toggle active/inactive")
                print("7. Back to main menu")
                rec_choice = input("Choose: ")

                if rec_choice == '1':
                    # Add recurring expense
                    try:
                        print("\n--- Add Recurring Expense ---")
                        amount = float(input("Amount (€): "))
                        category = input("Category: ")
                        day = int(input("Day of month (1-28): "))
                        description = input("Description (optional): ")
                        start_date = input("Start date (YYYY-MM-DD, press Enter for today): ")
                        start_date = start_date or datetime.now().strftime("%Y-%m-%d")
                        end_date = input("End date (YYYY-MM-DD, optional): ") or None

                        tracker.add_recurring_expense(amount, category, day, description, start_date, end_date)
                    except ValueError:
                        print("❌ Invalid input.")

                elif rec_choice == '2':
                    # View recurring expenses
                    tracker.show_recurring_expenses()

                elif rec_choice == '3':
                    # Process today's recurring expenses
                    tracker.process_recurring_expenses()

                elif rec_choice == '4':
                    # Process all (catch up)
                    tracker.process_all_recurring_expenses()

                elif rec_choice == '5':
                    # Delete recurring expense
                    tracker.show_recurring_expenses()
                    try:
                        rec_id = int(input("Enter recurring expense ID to delete: "))
                        tracker.delete_recurring_expense(rec_id)
                    except ValueError:
                        print("❌ Invalid ID.")

                elif rec_choice == '6':
                    # Toggle active/inactive
                    tracker.show_recurring_expenses()
                    try:
                        rec_id = int(input("Enter recurring expense ID to toggle: "))
                        tracker.toggle_recurring_expense(rec_id)
                    except ValueError:
                        print("❌ Invalid ID.")

                elif rec_choice == '7':
                    break
                else:
                    print("Invalid choice.")


if __name__ == "__main__":
    main()