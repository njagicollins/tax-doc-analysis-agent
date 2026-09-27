"""Where documents come from. Each source hides its own details behind one method."""

import csv
import io
import sqlite3
from pathlib import Path
from typing import Protocol

import httpx2


class DocumentSource(Protocol):
    """Anything that can hand over a quarter's documents as (name, bytes) pairs."""

    name: str

    def fetch_documents(self, quarter: str) -> list[tuple[str, bytes]]: ...


class AdpApiSource:
    name = "adp"

    def __init__(
        self, base_url: str, api_key: str, client: httpx2.Client | None = None
    ) -> None:
        # Tests pass in their own client; real runs create one for the base URL
        self.client = client or httpx2.Client(base_url=base_url, timeout=30)
        self.headers = {"X-API-Key": api_key}

    def fetch_documents(self, quarter: str) -> list[tuple[str, bytes]]:
        listing = self.client.get(
            "/documents", params={"quarter": quarter}, headers=self.headers
        )
        listing.raise_for_status()

        documents = []
        for item in listing.json():
            response = self.client.get(
                f"/documents/{item['name']}", headers=self.headers
            )
            response.raise_for_status()
            documents.append((item["name"], response.content))
        return documents


PAYROLL_EXPORT_SQL = """
SELECT p.employee_id, e.name, e.ssn, p.quarter,
       p.regular_wages_cents, p.bonus_cents, p.gross_wages_cents,
       p.federal_tax_cents, p.ss_wages_cents, p.ss_tax_cents, p.medicare_tax_cents
FROM payroll AS p
JOIN employees AS e ON e.employee_id = p.employee_id
WHERE p.quarter = ?
ORDER BY p.employee_id
"""


class SqlPayrollSource:
    name = "sql"

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def fetch_documents(self, quarter: str) -> list[tuple[str, bytes]]:
        # Open read-only: ingestion must never change the source system
        conn = sqlite3.connect(f"file:{self.db_path.as_posix()}?mode=ro", uri=True)
        try:
            cursor = conn.execute(PAYROLL_EXPORT_SQL, (quarter,))
            header = [column[0] for column in cursor.description]
            rows = cursor.fetchall()
        finally:
            conn.close()

        # Same data must give the same bytes, so the hash only changes if data does
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)
        return [(f"payroll_db_{quarter}.csv", buffer.getvalue().encode("utf-8"))]
