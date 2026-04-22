import mysql.connector
import streamlit as st
from contextlib import contextmanager


@contextmanager
def _conn():
    conn = mysql.connector.connect(
        host=st.secrets["db"]["host"],
        port=int(st.secrets["db"]["port"]),
        user=st.secrets["db"]["user"],
        password=st.secrets["db"]["password"],
        database=st.secrets["db"]["database"],
    )
    try:
        yield conn
    finally:
        conn.close()


# ── Bootstrap ──────────────────────────────────────────────────────────────

def init_db():
    """Create AppUsers table and seed the default admin on first run."""
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS AppUsers (
                id             INT AUTO_INCREMENT PRIMARY KEY,
                email          VARCHAR(200) UNIQUE NOT NULL,
                password_hash  VARCHAR(255)        NOT NULL,
                full_name      VARCHAR(200),
                role           ENUM('admin','se')  DEFAULT 'se',
                executive_code VARCHAR(200),
                is_active      BOOLEAN             DEFAULT TRUE,
                created_at     TIMESTAMP           DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

        cur.execute("SELECT id FROM AppUsers WHERE email = %s",
                    (st.secrets["app"]["admin_email"],))
        if cur.fetchone() is None:
            import bcrypt
            pw_hash = bcrypt.hashpw(
                st.secrets["app"]["admin_password"].encode(),
                bcrypt.gensalt()
            ).decode()
            cur.execute(
                "INSERT INTO AppUsers (email, password_hash, full_name, role) "
                "VALUES (%s, %s, 'Admin', 'admin')",
                (st.secrets["app"]["admin_email"], pw_hash),
            )
            conn.commit()


# ── Auth ───────────────────────────────────────────────────────────────────

def get_user_by_email(email: str):
    with _conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT * FROM AppUsers WHERE email = %s AND is_active = TRUE",
            (email.strip().lower(),),
        )
        return cur.fetchone()


# ── Customer queries ───────────────────────────────────────────────────────

def get_customers_for_executive(executive_code: str):
    with _conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT * FROM FnVCustomerImageCaputure "
            "WHERE Executive = %s ORDER BY Locality, Customer",
            (executive_code,),
        )
        return cur.fetchall()


def get_all_customers(executive_filter=None, locality_id_filter=None):
    with _conn() as conn:
        cur = conn.cursor(dictionary=True)
        query = "SELECT * FROM FnVCustomerImageCaputure WHERE 1=1"
        params = []
        if executive_filter:
            query += " AND Executive = %s"
            params.append(executive_filter)
        if locality_id_filter:
            query += " AND LocalityId = %s"
            params.append(locality_id_filter)
        query += " ORDER BY Executive, Locality, Customer"
        cur.execute(query, params)
        return cur.fetchall()


def get_customer_by_id(customer_id: int):
    with _conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT * FROM FnVCustomerImageCaputure WHERE CustomerId = %s",
            (customer_id,),
        )
        return cur.fetchone()


def update_image_slot(customer_id: int, slot: int,
                      image_url: str, actual_lat: float, actual_lng: float):
    """Fill the next available ImageUrl slot and update actual coordinates."""
    allowed_cols = {1: "ImageUrl1", 2: "ImageUrl2", 3: "ImageUrl3"}
    col = allowed_cols[slot]
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE FnVCustomerImageCaputure "
            f"SET {col} = %s, ActualLaitude = %s, ActualLongitude = %s "
            f"WHERE CustomerId = %s",
            (image_url, actual_lat, actual_lng, customer_id),
        )
        conn.commit()
        return cur.rowcount > 0


def clear_customer_images(customer_id: int):
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE FnVCustomerImageCaputure "
            "SET ImageUrl1=NULL, ImageUrl2=NULL, ImageUrl3=NULL, "
            "ActualLaitude=NULL, ActualLongitude=NULL "
            "WHERE CustomerId = %s",
            (customer_id,),
        )
        conn.commit()


# ── Aggregates ─────────────────────────────────────────────────────────────

def get_overall_stats():
    with _conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN ImageUrl1 IS NOT NULL
                          OR ImageUrl2 IS NOT NULL
                          OR ImageUrl3 IS NOT NULL THEN 1 ELSE 0 END) AS captured,
                SUM(CASE WHEN ImageUrl1 IS NULL
                         AND ImageUrl2 IS NULL
                         AND ImageUrl3 IS NULL THEN 1 ELSE 0 END) AS pending
            FROM FnVCustomerImageCaputure
        """)
        return cur.fetchone()


def get_executive_stats():
    with _conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT
                Executive,
                COUNT(*) AS total,
                SUM(CASE WHEN ImageUrl1 IS NOT NULL
                          OR ImageUrl2 IS NOT NULL
                          OR ImageUrl3 IS NOT NULL THEN 1 ELSE 0 END) AS captured
            FROM FnVCustomerImageCaputure
            WHERE Executive IS NOT NULL
            GROUP BY Executive
            ORDER BY Executive
        """)
        return cur.fetchall()


# ── Reference lists ────────────────────────────────────────────────────────

def get_distinct_executives():
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT Executive FROM FnVCustomerImageCaputure "
            "WHERE Executive IS NOT NULL ORDER BY Executive"
        )
        return [r[0] for r in cur.fetchall()]


def get_distinct_localities(executive_code=None):
    with _conn() as conn:
        cur = conn.cursor(dictionary=True)
        if executive_code:
            cur.execute(
                "SELECT DISTINCT LocalityId, Locality "
                "FROM FnVCustomerImageCaputure "
                "WHERE Executive = %s ORDER BY Locality",
                (executive_code,),
            )
        else:
            cur.execute(
                "SELECT DISTINCT LocalityId, Locality "
                "FROM FnVCustomerImageCaputure ORDER BY Locality"
            )
        return cur.fetchall()


# ── User management ────────────────────────────────────────────────────────

def create_user(email: str, password_hash: str, full_name: str,
                role: str, executive_code=None):
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO AppUsers "
            "(email, password_hash, full_name, role, executive_code) "
            "VALUES (%s, %s, %s, %s, %s)",
            (email.strip().lower(), password_hash, full_name, role, executive_code),
        )
        conn.commit()


def get_all_users():
    with _conn() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT id, email, full_name, role, executive_code, "
            "is_active, created_at FROM AppUsers ORDER BY role, email"
        )
        return cur.fetchall()


def update_user(user_id: int, full_name: str, role: str,
                executive_code, is_active: bool):
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE AppUsers "
            "SET full_name=%s, role=%s, executive_code=%s, is_active=%s "
            "WHERE id=%s",
            (full_name, role, executive_code or None, is_active, user_id),
        )
        conn.commit()


def update_user_password(user_id: int, password_hash: str):
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE AppUsers SET password_hash=%s WHERE id=%s",
            (password_hash, user_id),
        )
        conn.commit()


def delete_user(user_id: int):
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM AppUsers WHERE id=%s", (user_id,))
        conn.commit()
