# Multi-User Expense Tracker

A secure command-line expense tracking application with user authentication, category summaries, and CSV export.

## Features

- **User Authentication**: Register/login with Argon2 password hashing
- **Multi-User Support**: Each user sees only their own expenses
- **Expense Management**: Add, view, and delete expenses
- **Date Filtering**: View expenses for last 7/30 days or custom ranges
- **Spending Summary**: Total expenses + breakdown by category
- **CSV Export**: Export all expenses with progress indicator
- **Formatted Tables**: Clean display using tabulate library

## Tech Stack

- Python 3
- SQLite3 (with foreign key constraints)
- Argon2-cffi (password hashing)
- Tabulate (table formatting)

## Installation

```bash
# Clone the repository
git clone https://github.com/Sorousch01/expense-tracker.git
cd expense-tracker

# Install dependencies
pip install -r requirements.txt

# Run the application
python MultiUserExpenseTracker.py
