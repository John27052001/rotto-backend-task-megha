.PHONY: test crawl

test:
	python3 tests/setup_test_db.py
	DB_NAME=rotto_test python3 tests/test_lifecycle.py

crawl:
	python3 crawler/crawl.py