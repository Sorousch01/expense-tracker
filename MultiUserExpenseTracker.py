



import sqlite3
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
import os
from datetime import datetime, timedelta
import csv
from tabulate import tabulate

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
            conn.commit()

    def add_expense(self, amount, category, date, description=""):
        """Add a new expense for the current user."""
        # Check if user is logged in
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

                # Get the expense ID that was just created
                expense_id = c.lastrowid

                # Print confirmation
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
        print("6. Delete expense")
        print("7. Export all to CSV")
        print("8. Logout")
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
            # Delete expense
            try:
                expense_id = int(input("Expense ID to delete: "))
                tracker.delete_expense(expense_id)
            except ValueError:
                print("❌ Invalid ID. Please enter a number.")

        elif choice == '7':
            # Export all to CSV
            tracker.export_to_csv(username=username)

        elif choice == '8':
            print("Logging out...")
            break

        else:
            print("Invalid choice. Please enter 1-8.")

if __name__ == "__main__":
    main()