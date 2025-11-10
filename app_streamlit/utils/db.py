import mysql.connector
from mysql.connector import Error

def get_connection():
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="@ayushiii096",     # ← put your MySQL password here
            database="mirrorbank"
        )
        return conn
    except Error as e:
        print("Database connection error:", e)
        return None


def run_query(query, params=None, fetch=False):
    conn = get_connection()
    if conn is None:
        return None

    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute(query, params)

        if fetch:
            result = cursor.fetchall()
            conn.close()
            return result

        conn.commit()
        conn.close()
        return True

    except Error as e:
        print("Query error:", e)
        conn.close()
        return None
