import psycopg


def create_test_database():
    # Connect to the normal postgres database first.
    connection = psycopg.connect(
        host="localhost",
        port=5433,
        dbname="postgres",
        user="rotto",
        password="rotto",
        autocommit=True,
    )

    cursor = connection.cursor()

    # Check whether rotto_test already exists.
    cursor.execute(
        """
        SELECT 1
        FROM pg_database
        WHERE datname = 'rotto_test';
        """
    )

    exists = cursor.fetchone()

    if exists is None:
        cursor.execute("CREATE DATABASE rotto_test;")
        print("Created rotto_test database.")
    else:
        print("rotto_test database already exists.")

    cursor.close()
    connection.close()


def create_jobs_table():
    connection = psycopg.connect(
        host="localhost",
        port=5433,
        dbname="rotto_test",
        user="rotto",
        password="rotto",
    )

    cursor = connection.cursor()

    with open("sql/init.sql") as file:
        schema = file.read()

    cursor.execute(schema)

    connection.commit()

    cursor.close()
    connection.close()

    print("Test database schema ready.")


if __name__ == "__main__":
    create_test_database()
    create_jobs_table()