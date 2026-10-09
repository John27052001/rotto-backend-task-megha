import os

import psycopg


def get_connection():
    database_name = os.getenv("DB_NAME", "rotto")

    return psycopg.connect(
        host="localhost",
        port=5433,
        dbname=database_name,
        user="rotto",
        password="rotto",
    )


def count_jobs():
    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("SELECT COUNT(*) FROM jobs;")

    result = cursor.fetchone()

    print("Number of jobs:", result[0])

    cursor.close()
    connection.close()


if __name__ == "__main__":
    count_jobs()