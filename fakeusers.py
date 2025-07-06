# fake_users.py
from webapp import db, User, app
import secrets

def add_fake_users():
    fake_data = [
        {"first_name": "Alice", "last_name": "Smith", "telegram_id": "10000001", "balance": 123.45},
        {"first_name": "Bob", "last_name": "Johnson", "telegram_id": "10000002", "balance": 234.56},
        {"first_name": "Charlie", "last_name": "Brown", "telegram_id": "10000003", "balance": 345.67},
        {"first_name": "Diana", "last_name": "Prince", "telegram_id": "10000004", "balance": 456.78},
        {"first_name": "Eve", "last_name": "Adams", "telegram_id": "10000005", "balance": 567.89},
        {"first_name": "Frank", "last_name": "Miller", "telegram_id": "10000006", "balance": 678.90},
        {"first_name": "Grace", "last_name": "Hopper", "telegram_id": "10000007", "balance": 789.01},
        {"first_name": "Henry", "last_name": "Ford", "telegram_id": "10000008", "balance": 890.12},
        {"first_name": "Ivy", "last_name": "Lee", "telegram_id": "10000009", "balance": 901.23},
        {"first_name": "Jack", "last_name": "Black", "telegram_id": "10000010", "balance": 1012.34},
        {"first_name": "Kate", "last_name": "Winslet", "telegram_id": "10000011", "balance": 1123.45},
        {"first_name": "Leo", "last_name": "Messi", "telegram_id": "10000012", "balance": 1234.56},
        {"first_name": "Mona", "last_name": "Lisa", "telegram_id": "10000013", "balance": 1345.67},
        {"first_name": "Nick", "last_name": "Cave", "telegram_id": "10000014", "balance": 1456.78},
        {"first_name": "Olga", "last_name": "Petrova", "telegram_id": "10000015", "balance": 1567.89},
    ]
    for user in fake_data:
        ref_code = secrets.token_hex(4)
        u = User(telegram_id=user["telegram_id"],
                 first_name=user["first_name"],
                 last_name=user["last_name"],
                 balance=user["balance"],
                 ref_code=ref_code)
        db.session.add(u)
    db.session.commit()
    print('15 fake users added!')

if __name__ == '__main__':
    with app.app_context():
        add_fake_users()
