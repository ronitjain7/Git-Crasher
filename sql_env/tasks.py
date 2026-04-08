import sqlite3
from faker import Faker
import random

fake = Faker()

def load_fixtures(conn):
    # Set seeds for deterministic fixture generation
    Faker.seed(42)
    random.seed(42)
    
    cursor = conn.cursor()
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            name TEXT,
            email TEXT,
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

    users = [(fake.name(), fake.email(), fake.date()) for _ in range(2000)]
    cursor.executemany("INSERT INTO users (name, email, created_at) VALUES (?, ?, ?)", users)
    
    products = [(fake.company(), round(random.uniform(10.0, 500.0), 2)) for _ in range(500)]
    cursor.executemany("INSERT INTO products (name, price) VALUES (?, ?)", products)
    
    orders = [(random.randint(1, 2000), round(random.uniform(20.0, 1000.0), 2), fake.date()) for _ in range(3000)]
    cursor.executemany("INSERT INTO orders (user_id, total, order_date) VALUES (?, ?, ?)", orders)
    
    line_items = [(random.randint(1, 3000), random.randint(1, 500), random.randint(1, 5), round(random.uniform(10.0, 500.0), 2)) for _ in range(3500)]
    cursor.executemany("INSERT INTO line_items (order_id, product_id, quantity, price) VALUES (?, ?, ?, ?)", line_items)
    
    reviews = [(random.randint(1, 500), random.randint(1, 2000), random.randint(1, 5), fake.sentence()) for _ in range(1000)]
    cursor.executemany("INSERT INTO reviews (product_id, user_id, rating, comment) VALUES (?, ?, ?, ?)", reviews)
    
    conn.commit()

TASKS = {
    "syntax-fix": {
        "db_schema": "users(id, name, email, created_at)",
        "query": "SELCET id name email FROM users WHRE created_at > '2023-01-01';",
        "expected_hint": "Select all active users created after 2023-01-01",
        "validation_query": "SELECT id, name, email FROM users WHERE created_at > '2023-01-01';"
    },
    "performance-tune": {
        "db_schema": "orders(id, user_id, total, order_date), users(id, name, email, created_at)",
        "query": "SELECT * FROM orders WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%@gmail.com');",
        "expected_hint": "Rewrite to use JOIN and indexing to avoid full table scans",
        "validation_query": "SELECT orders.id, orders.user_id, orders.total, orders.order_date FROM orders JOIN users ON orders.user_id = users.id WHERE users.email LIKE '%@gmail.com';"
    },
    "schema-design": {
        "db_schema": "None (Create from scratch)",
        "query": "",
        "expected_hint": "Design a relational schema for: 'A social media platform where users can post messages, other users can like those messages, and users can follow each other.'",
        "validation_query": ""
    }
}
