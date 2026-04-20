"""
Tạo dummy Python repo với fake git history để test KG + risk scoring.

Repo structure:
  src/auth.py          ← nhiều bug fixes (high bug_frequency)
  src/payment.py       ← import auth, nhiều contributors (high churn)
  src/cart.py          ← import payment
  src/models/user.py
  src/models/order.py
  src/utils/validator.py
  src/utils/logger.py
  tests/test_auth.py
  tests/test_payment.py
  # cart.py và models/ không có test → coverage gap

Usage:
    python scripts/create_dummy_repo.py [output_dir]
    default output_dir: dummy_repo/
"""

import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("dummy_repo")

# --- Source files ---
FILES = {
    "src/__init__.py": "",
    "src/auth.py": '''\
import hashlib
import sqlite3


def create_user(username: str, password: str) -> bool:
    """Create a new user with hashed password."""
    conn = sqlite3.connect("users.db")
    hashed = hashlib.sha256(password.encode()).hexdigest()
    conn.execute("INSERT INTO users VALUES (?, ?)", (username, hashed))
    conn.commit()
    conn.close()
    return True


def login(username: str, password: str) -> bool:
    """Verify user credentials."""
    conn = sqlite3.connect("users.db")
    hashed = hashlib.sha256(password.encode()).hexdigest()
    row = conn.execute(
        "SELECT 1 FROM users WHERE username=? AND password=?", (username, hashed)
    ).fetchone()
    conn.close()
    return row is not None


def get_user(username: str) -> dict | None:
    conn = sqlite3.connect("users.db")
    row = conn.execute(
        "SELECT username FROM users WHERE username=?", (username,)
    ).fetchone()
    conn.close()
    return {"username": row[0]} if row else None
''',

    "src/payment.py": '''\
from src.auth import get_user
from src.utils.validator import validate_amount


def process_payment(username: str, amount: float) -> dict:
    """Process a payment for a user."""
    user = get_user(username)
    if not user:
        raise ValueError("User not found")
    if not validate_amount(amount):
        raise ValueError("Invalid amount")
    return {"status": "ok", "user": username, "amount": amount}


def refund(username: str, amount: float) -> dict:
    user = get_user(username)
    if not user:
        raise ValueError("User not found")
    return {"status": "refunded", "user": username, "amount": amount}
''',

    "src/cart.py": '''\
from src.payment import process_payment
from src.models.order import Order


def add_to_cart(username: str, item: str, price: float) -> dict:
    order = Order(username=username, item=item, price=price)
    return {"cart": order.to_dict()}


def checkout(username: str, items: list) -> dict:
    total = sum(i["price"] for i in items)
    result = process_payment(username, total)
    return {"checkout": result}
''',

    "src/models/__init__.py": "",
    "src/models/user.py": '''\
class User:
    def __init__(self, username: str, email: str):
        self.username = username
        self.email = email

    def to_dict(self) -> dict:
        return {"username": self.username, "email": self.email}
''',

    "src/models/order.py": '''\
class Order:
    def __init__(self, username: str, item: str, price: float):
        self.username = username
        self.item = item
        self.price = price

    def to_dict(self) -> dict:
        return {"username": self.username, "item": self.item, "price": self.price}
''',

    "src/utils/__init__.py": "",
    "src/utils/validator.py": '''\
def validate_amount(amount: float) -> bool:
    """Validate that amount is positive and reasonable."""
    return isinstance(amount, (int, float)) and 0 < amount < 1_000_000


def validate_username(username: str) -> bool:
    return bool(username) and len(username) >= 3 and username.isalnum()
''',

    "src/utils/logger.py": '''\
import logging

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger
''',

    "tests/__init__.py": "",
    "tests/test_auth.py": '''\
from src.auth import login, create_user


def test_create_user():
    assert create_user("alice", "secret") is True


def test_login_valid():
    assert login("alice", "secret") is True


def test_login_invalid():
    assert login("alice", "wrong") is False
''',

    "tests/test_payment.py": '''\
from src.payment import process_payment


def test_process_payment_valid():
    result = process_payment("alice", 99.99)
    assert result["status"] == "ok"


def test_process_payment_invalid_amount():
    try:
        process_payment("alice", -1)
        assert False
    except ValueError:
        pass
''',
}

# --- Fake git history ---
# Each entry: (file, commit_message, author, days_ago)
COMMITS = [
    # Initial setup — 120 days ago
    ("src/auth.py",          "Initial commit: add auth module",           "alice", 120),
    ("src/payment.py",       "Initial commit: add payment module",        "alice", 120),
    ("src/cart.py",          "Initial commit: add cart module",           "alice", 119),
    ("src/models/user.py",   "Initial commit: add User model",            "alice", 119),
    ("src/models/order.py",  "Initial commit: add Order model",           "bob",   118),
    ("src/utils/validator.py","Initial commit: add validator",            "bob",   118),
    ("src/utils/logger.py",  "Initial commit: add logger",                "alice", 117),
    ("tests/test_auth.py",   "test: add auth tests",                      "alice", 116),
    ("tests/test_payment.py","test: add payment tests",                   "alice", 116),
    # Bug fixes on auth.py — many in 90 days (high bug_frequency)
    ("src/auth.py",          "fix: sql injection in login",               "carol", 85),
    ("src/auth.py",          "fix: password hashing was md5, upgrade sha256","dave",80),
    ("src/auth.py",          "bugfix: get_user returns None on empty db", "carol", 72),
    ("src/auth.py",          "hotfix: login case sensitivity issue",      "eve",   65),
    ("src/auth.py",          "fix: connection not closed on exception",   "bob",   50),
    ("src/auth.py",          "fix: concurrent login race condition",      "carol", 30),
    # payment.py — nhiều contributor (high churn)
    ("src/payment.py",       "refactor: split process_payment logic",     "bob",   80),
    ("src/payment.py",       "fix: refund amount validation",             "carol", 60),
    ("src/payment.py",       "feat: add refund function",                 "dave",  45),
    ("src/payment.py",       "fix: payment status typo",                  "eve",   20),
    ("src/payment.py",       "refactor: use validate_amount from utils",  "frank", 10),
    # cart.py — ít thay đổi (low risk)
    ("src/cart.py",          "feat: add checkout function",               "alice", 70),
    ("src/cart.py",          "refactor: cleanup cart logic",              "alice", 15),
    # validator.py — stable
    ("src/utils/validator.py","feat: add validate_username",              "bob",   90),
]


def run(cmd: list[str], cwd: Path, env: dict = None):
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    subprocess.run(cmd, cwd=str(cwd), check=True, capture_output=True, env=full_env)


def main():
    if REPO_DIR.exists():
        import shutil, stat
        def _force_remove(func, path, _):
            os.chmod(path, stat.S_IWRITE)
            func(path)
        shutil.rmtree(REPO_DIR, onexc=_force_remove)
    REPO_DIR.mkdir(parents=True)

    run(["git", "init"], REPO_DIR)
    run(["git", "config", "user.email", "test@example.com"], REPO_DIR)
    run(["git", "config", "user.name", "Test User"], REPO_DIR)

    # Write all files first
    for rel_path, content in FILES.items():
        full_path = REPO_DIR / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content)

    # Replay commits with fake timestamps
    # Each commit appends a small comment to the file so it's a real change
    now = datetime.now()
    commit_counters: dict[str, int] = {}
    for rel_path, message, author, days_ago in COMMITS:
        fake_date = (now - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%S")
        env = {
            "GIT_AUTHOR_NAME": author,
            "GIT_AUTHOR_EMAIL": f"{author}@example.com",
            "GIT_AUTHOR_DATE": fake_date,
            "GIT_COMMITTER_NAME": author,
            "GIT_COMMITTER_EMAIL": f"{author}@example.com",
            "GIT_COMMITTER_DATE": fake_date,
        }
        # Append a small change so git tracks this file in the commit
        commit_counters[rel_path] = commit_counters.get(rel_path, 0) + 1
        full_path = REPO_DIR / rel_path
        with open(full_path, "a") as f:
            f.write(f"\n# commit-{commit_counters[rel_path]}: {message[:40]}\n")
        run(["git", "add", rel_path], REPO_DIR, env)
        run(["git", "commit", "-m", message], REPO_DIR, env)

    print(f"[OK] Dummy repo created at: {REPO_DIR.resolve()}")
    print(f"  Files: {len(FILES)}, Commits: {len(COMMITS)}")
    print(f"  High bug_frequency: src/auth.py (6 fixes in 90 days)")
    print(f"  High contributor churn: src/payment.py (5 distinct authors)")
    print(f"  Coverage gap: src/cart.py, src/models/, src/utils/ have no tests")


if __name__ == "__main__":
    main()
