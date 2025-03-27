import mysql.connector

conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="your_password",
    database="your_database"
)
cursor = conn.cursor()

cursor.execute("DELETE FROM table_name")  # Replace with your table
conn.commit()

cursor.execute("TRUNCATE TABLE table_name")  # Optional to reset auto-increment
conn.commit()

conn.close()
print("Database cleared successfully!")
