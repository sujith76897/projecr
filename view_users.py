import sqlite3

# Connect to the database
conn = sqlite3.connect('users.db')
cursor = conn.cursor()

# Fetch and display all user records (excluding face encodings for readability)
cursor.execute("SELECT id, name, roll_no FROM users")
users = cursor.fetchall()

print("Registered Users:")
for user in users:
    print(f"ID: {user[0]}, Name: {user[1]}, Roll No: {user[2]}")

conn.close()
