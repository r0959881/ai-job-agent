import sqlite3

JOB_COLUMNS = {
    "description": "TEXT DEFAULT ''",
    "category": "TEXT DEFAULT ''",
    "contract_type": "TEXT DEFAULT ''",
    "salary_min": "REAL",
    "salary_max": "REAL",
    "salary_currency": "TEXT DEFAULT ''",
    "posted_at": "TEXT DEFAULT ''",
    "discovered_at": "TEXT DEFAULT ''",
    "cv_path": "TEXT DEFAULT ''",
    "source_data": "TEXT DEFAULT ''",
}

NON_BELGIAN_LOCATION_MARKERS = (
    "germany", "deutschland", "düsseldorf", "dusseldorf", "berlin",
    "munich", "münchen", "frankfurt", "hamburg", "cologne", "köln",
    "stuttgart", "france", "paris", "uk", "united kingdom", "england", "scotland",
    "wales", "london", "manchester", "birmingham", "leeds", "edinburgh",
    "glasgow", "bristol",
)

ALLOWED_LOCATION_MARKERS = (
    "belgium", "belgië", "belgique", "mechelen", "antwerp", "antwerpen",
    "brussels", "bruxelles", "ghent", "gent", "leuven", "flanders", "vlaanderen",
    "netherlands", "nederland", "amsterdam", "rotterdam", "utrecht", "eindhoven",
)

def init_db():
    conn = sqlite3.connect("jobs.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            title TEXT,
            company TEXT,
            location TEXT,
            url TEXT,
            source TEXT,
            status TEXT DEFAULT 'new'
        )
    ''')
    existing_columns = {
        row[1] for row in cursor.execute("PRAGMA table_info(jobs)")
    }
    for column, definition in JOB_COLUMNS.items():
        if column not in existing_columns:
            cursor.execute(f"ALTER TABLE jobs ADD COLUMN {column} {definition}")
    cursor.execute(
        "UPDATE jobs SET discovered_at = datetime('now') "
        "WHERE COALESCE(discovered_at, '') = ''"
    )
    location_filter = " OR ".join("LOWER(COALESCE(location, '')) LIKE ?" for _ in ALLOWED_LOCATION_MARKERS)
    cursor.execute(
        f"DELETE FROM jobs WHERE NOT ({location_filter})",
        tuple(f"%{marker}%" for marker in ALLOWED_LOCATION_MARKERS),
    )
    conn.commit()
    conn.close()
    print("✅ Database initialized successfully!")

if __name__ == "__main__":
    init_db()