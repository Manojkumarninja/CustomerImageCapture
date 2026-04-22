import bcrypt
import streamlit as st
from db import get_user_by_email


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


def login(email: str, password: str):
    """Return user dict on success, None on failure."""
    user = get_user_by_email(email)
    if not user:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    return user


def set_session(user: dict):
    st.session_state.logged_in      = True
    st.session_state.user_id        = user["id"]
    st.session_state.email          = user["email"]
    st.session_state.full_name      = user.get("full_name") or user["email"]
    st.session_state.role           = user["role"]
    st.session_state.executive_code = user.get("executive_code")
    st.session_state.page           = "dashboard"


def logout():
    keys = [
        "logged_in", "user_id", "email", "full_name",
        "role", "executive_code", "page", "selected_customer_id",
        "gps_lat", "gps_lng",
    ]
    for k in keys:
        st.session_state.pop(k, None)
