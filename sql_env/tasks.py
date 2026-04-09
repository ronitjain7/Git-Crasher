import sqlite3
from faker import Faker
import random

fake = Faker()
# Strict determinism for reproducible grader execution
Faker.seed(42)
random.seed(42)

def generate_fixtures(conn):
    cursor = conn.cursor()
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            name TEXT,
            email TEXT,
            status TEXT,
            country TEXT,
            created_at DATE
        );
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY,
            name TEXT,
            price REAL
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            total REAL,
            order_date DATE,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS line_items (
            id INTEGER PRIMARY KEY,
            order_id INTEGER,
            product_id INTEGER,
            quantity INTEGER,
            price REAL,
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        );
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY,
            product_id INTEGER,
            user_id INTEGER,
            rating INTEGER,
            comment TEXT,
            FOREIGN KEY (product_id) REFERENCES products(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        
        -- Create an index to be used in performance-tune task
        CREATE INDEX idx_user_email ON users(email);
    """)

    users = [(fake.name(), fake.email(), random.choice(['active', 'inactive', 'suspended']), random.choice(['US', 'UK', 'CA', 'AU', 'DE']), fake.date()) for _ in range(2000)]
    cursor.executemany("INSERT INTO users (name, email, status, country, created_at) VALUES (?, ?, ?, ?, ?)", users)
    
    products = [(fake.company(), round(random.uniform(10.0, 500.0), 2)) for _ in range(500)]
    cursor.executemany("INSERT INTO products (name, price) VALUES (?, ?)", products)
    
    orders = [(random.randint(1, 2000), round(random.uniform(20.0, 1000.0), 2), fake.date()) for _ in range(3000)]
    cursor.executemany("INSERT INTO orders (user_id, total, order_date) VALUES (?, ?, ?)", orders)
    
    line_items = [(random.randint(1, 3000), random.randint(1, 500), random.randint(1, 5), round(random.uniform(10.0, 500.0), 2)) for _ in range(3500)]
    cursor.executemany("INSERT INTO line_items (order_id, product_id, quantity, price) VALUES (?, ?, ?, ?)", line_items)
    
    reviews = [(random.randint(1, 500), random.randint(1, 2000), random.randint(1, 5), fake.sentence()) for _ in range(1000)]
    cursor.executemany("INSERT INTO reviews (product_id, user_id, rating, comment) VALUES (?, ?, ?, ?)", reviews)
    
    conn.commit()

# --- Blazing Fast Master Template Cache ---
_MASTER_CONN = None

def get_master_db(task_id=None):
    """Lazily generates and guarantees a single read-only Master Memory DB."""
    if task_id == "schema-design":
        # Schema tasks require a globally clean slate constraint
        c = sqlite3.connect(":memory:")
        c.row_factory = sqlite3.Row
        return c
        
    global _MASTER_CONN
    if _MASTER_CONN is None:
        _MASTER_CONN = sqlite3.connect(":memory:")
        _MASTER_CONN.row_factory = sqlite3.Row
        generate_fixtures(_MASTER_CONN)
    return _MASTER_CONN

def load_fixtures(conn, task_id="syntax-fix"):
    """Instantly clone the master data instead of generating thousands of random rows repeatedly."""
    master = get_master_db(task_id)
    master.backup(conn)


TASKS = {
    "syntax-fix": {
        "db_schema": "users(id, name, email, status, country, created_at)",
        "query": "SELCET id name email FROM users WHRE created_at > '2023-01-01';",
        "expected_hint": "Select the id, name, and email of all users created after 2023-01-01.",
        "validation_query": "SELECT id, name, email FROM users WHERE created_at > '2023-01-01';"
    },
    "performance-tune": {
        "db_schema": "orders(id, user_id, total, order_date), users(id, name, email, status, country, created_at)",
        "query": "SELECT * FROM orders WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%@gmail.com');",
        "expected_hint": "Rewrite to use JOIN and indexing to avoid full table scans",
        "validation_query": "SELECT orders.id, orders.user_id, orders.total, orders.order_date FROM orders JOIN users ON orders.user_id = users.id WHERE users.email LIKE '%@gmail.com';"
    },
    "schema-design": {
        "db_schema": "None (Create from scratch)",
        "query": "",
        "expected_hint": "Design a relational schema for: 'A social media platform where users can post messages, other users can like those messages, and users can follow each other.'",
        "validation_query": "CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT); CREATE TABLE posts (id INTEGER PRIMARY KEY, user_id INTEGER, content TEXT); CREATE TABLE likes (id INTEGER PRIMARY KEY, post_id INTEGER, user_id INTEGER); CREATE TABLE follows (follower_id INTEGER, followed_id INTEGER, PRIMARY KEY(follower_id, followed_id));"
    },
    # ── New Universal Tasks Engine Array ──
    "aggregation-mastery": {
        "db_schema": "orders(id, user_id, total, order_date)",
        "query": "SELECT order_date, total FROM orders;",
        "expected_hint": "Find the total revenue grouped by order_date, having total revenue greater than 1000",
        "validation_query": "SELECT order_date, SUM(total) as revenue FROM orders GROUP BY order_date HAVING revenue > 1000;"
    },
    "data-mutation": {
        "db_schema": "users(id, name, email, status, country, created_at)",
        "query": "UPDATE users SET status = 'inactive';",
        "expected_hint": "Safely update the status to 'suspended' for all users whose country is 'AU'.",
        "validation_query": "UPDATE users SET status = 'suspended' WHERE country = 'AU';"
    },
    "advanced-joins": {
        "db_schema": "products(id, name, price), reviews(id, product_id, user_id, rating, comment)",
        "query": "SELECT name FROM products;",
        "expected_hint": "Select all product names alongside their review comments, including products with no reviews.",
        "validation_query": "SELECT products.name, reviews.comment FROM products LEFT JOIN reviews ON products.id = reviews.product_id;"
    }
}
