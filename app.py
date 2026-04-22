import streamlit as st
from datetime import datetime
import time

from db import (
    init_db,
    get_customers_for_executive,
    get_all_customers,
    get_customer_by_id,
    update_image_slot,
    clear_customer_images,
    get_overall_stats,
    get_executive_stats,
    get_distinct_executives,
    get_distinct_localities,
    create_user,
    get_all_users,
    update_user,
    update_user_password,
    delete_user,
)
from auth import hash_password, login, set_session, logout
from drive import upload_image, is_drive_configured

# ── Page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="NinjaCart | Customer Image Capture",
    page_icon="📸",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .customer-card {
        background: #f8f9fa;
        border-radius: 10px;
        padding: 14px 18px;
        margin-bottom: 10px;
        border-left: 4px solid #dee2e6;
    }
    .card-pending  { border-left-color: #ffc107; }
    .card-partial  { border-left-color: #fd7e14; }
    .card-complete { border-left-color: #28a745; }
    .badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 0.78rem;
        font-weight: 600;
    }
    .badge-pending  { background:#fff3cd; color:#856404; }
    .badge-partial  { background:#ffe5d0; color:#7d3c0a; }
    .badge-complete { background:#d4edda; color:#155724; }
    div[data-testid="stMetricValue"] { font-size: 2rem; }
</style>
""", unsafe_allow_html=True)


# ── Bootstrap ──────────────────────────────────────────────────────────────

def _bootstrap():
    if "initialized" not in st.session_state:
        init_db()
        st.session_state.initialized = True
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "page" not in st.session_state:
        st.session_state.page = "dashboard"


# ── Helpers ────────────────────────────────────────────────────────────────

def image_status(customer: dict):
    urls = [customer.get("ImageUrl1"), customer.get("ImageUrl2"), customer.get("ImageUrl3")]
    n = sum(1 for u in urls if u)
    if n == 0:
        return "pending",  "⏳ Pending",       "badge-pending",  "card-pending"
    if n < 3:
        return "partial",  f"📷 {n}/3 Images", "badge-partial",  "card-partial"
    return     "complete", "✅ Complete",       "badge-complete", "card-complete"


def next_slot(customer: dict):
    for i, key in enumerate(["ImageUrl1", "ImageUrl2", "ImageUrl3"], 1):
        if not customer.get(key):
            return i
    return None


# ── Login page ─────────────────────────────────────────────────────────────

def show_login():
    col1, col2, col3 = st.columns([1, 1.6, 1])
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(
            "<h2 style='text-align:center;'>📸 Customer Image Capture</h2>"
            "<p style='text-align:center; color:#6c757d;'>NinjaCart — Sales Executive Portal</p>",
            unsafe_allow_html=True,
        )
        st.markdown("---")

        with st.form("login"):
            email    = st.text_input("Email Address", placeholder="you@ninjacart.com")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login", use_container_width=True, type="primary")

        if submitted:
            if not email or not password:
                st.error("Please enter both email and password.")
            else:
                user = login(email, password)
                if user:
                    set_session(user)
                    st.rerun()
                else:
                    st.error("Invalid email or password. Please try again.")


# ── Sidebar ────────────────────────────────────────────────────────────────

def show_sidebar():
    with st.sidebar:
        st.markdown(f"### 👤 {st.session_state.full_name}")
        st.caption(st.session_state.email)
        role = st.session_state.role
        st.caption(f"Role: **{'Admin' if role == 'admin' else 'Sales Executive'}**")
        if st.session_state.executive_code:
            st.caption(f"Code: `{st.session_state.executive_code}`")
        st.markdown("---")

        if role == "admin":
            if st.button("📊 Dashboard", use_container_width=True):
                st.session_state.page = "dashboard"
                st.rerun()
            if st.button("👥 Manage Users", use_container_width=True):
                st.session_state.page = "admin"
                st.rerun()

        st.markdown("---")
        if st.button("🚪 Logout", use_container_width=True):
            logout()
            st.rerun()

        if not is_drive_configured():
            st.markdown("---")
            st.warning(
                "**Drive not configured.**\n\n"
                "Add your Service Account credentials to `.streamlit/secrets.toml` "
                "to enable image uploads."
            )


# ── Dashboard ──────────────────────────────────────────────────────────────

def show_dashboard():
    show_sidebar()
    st.title("📸 Customer Image Capture")

    role      = st.session_state.role
    exec_code = st.session_state.executive_code

    if role == "admin":
        # ── Step 1: Executive filter ──
        all_executives = get_distinct_executives()
        fcol1, fcol2 = st.columns([2, 2])
        with fcol1:
            sel_exec = st.selectbox(
                "Executive", ["All"] + all_executives,
                label_visibility="collapsed",
                placeholder="Select Executive…",
            )

        # ── Step 2: Locality filter — scoped to selected executive ──
        exec_for_loc   = None if sel_exec == "All" else sel_exec
        raw_localities = get_distinct_localities(exec_for_loc)
        loc_map        = {l["Locality"]: l["LocalityId"]
                          for l in raw_localities if l.get("Locality")}

        with fcol2:
            sel_loc = st.selectbox(
                "Locality", ["All"] + list(loc_map.keys()),
                label_visibility="collapsed",
                placeholder="Select Locality…",
            )

        # ── Step 3: Fetch customers with exec + locality filters ──
        customers = get_all_customers(
            executive_filter   = None if sel_exec == "All" else sel_exec,
            locality_id_filter = None if sel_loc  == "All" else loc_map[sel_loc],
        )

        # ── Step 4: Customer name dropdown (populated from filtered set) ──
        customer_names = sorted({c["Customer"] for c in customers if c.get("Customer")})
        sel_customer   = st.selectbox(
            "Customer Name", ["All"] + customer_names,
            label_visibility="collapsed",
            placeholder="Select Customer…",
        )
        if sel_customer != "All":
            customers = [c for c in customers if c["Customer"] == sel_customer]

        # ── Metrics ──
        stats = get_overall_stats()
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Customers", stats["total"])
        m2.metric("Images Captured", stats["captured"])
        m3.metric("Pending",         stats["pending"])
        pct = round(stats["captured"] / stats["total"] * 100) if stats["total"] else 0
        m4.metric("Completion", f"{pct}%")

    else:
        if not exec_code:
            st.warning(
                "Your account is not linked to an Executive Code yet. "
                "Please contact your admin."
            )
            return

        # ── Step 1: Locality filter — only this SE's localities ──
        raw_localities = get_distinct_localities(exec_code)
        loc_map        = {l["Locality"]: l["LocalityId"]
                          for l in raw_localities if l.get("Locality")}

        sel_loc = st.selectbox(
            "Locality", ["All"] + list(loc_map.keys()),
            label_visibility="collapsed",
            placeholder="Select Locality…",
        )

        # ── Step 2: Fetch customers for this SE, apply locality filter ──
        customers = get_customers_for_executive(exec_code)
        if sel_loc != "All":
            lid       = loc_map[sel_loc]
            customers = [c for c in customers if c["LocalityId"] == lid]

        # ── Step 3: Customer name dropdown ──
        customer_names = sorted({c["Customer"] for c in customers if c.get("Customer")})
        sel_customer   = st.selectbox(
            "Customer Name", ["All"] + customer_names,
            label_visibility="collapsed",
            placeholder="Select Customer…",
        )
        if sel_customer != "All":
            customers = [c for c in customers if c["Customer"] == sel_customer]

        total    = len(customers)
        captured = sum(1 for c in customers if c["ImageUrl1"] or c["ImageUrl2"] or c["ImageUrl3"])
        m1, m2, m3 = st.columns(3)
        m1.metric("My Customers", total)
        m2.metric("Captured",     captured)
        m3.metric("Pending",      total - captured)

    st.markdown("---")
    st.subheader(f"Customers ({len(customers)})")

    if not customers:
        st.info("No customers match your filters.")
        return

    for c in customers:
        status_key, status_label, badge_cls, card_cls = image_status(c)

        st.markdown(
            f"""<div class="customer-card {card_cls}">
                <span class="badge {badge_cls}">{status_label}</span>
            </div>""",
            unsafe_allow_html=True,
        )

        col1, col2, col3, col4 = st.columns([3.5, 2, 2, 1.2])
        with col1:
            st.markdown(f"**{c['Customer']}**")
            st.caption(f"📍 {c['Locality']}  |  🏪 {c['Facility']}")
        with col2:
            st.caption(f"📞 {c['ContactNumber']}")
            if role == "admin":
                st.caption(f"👤 {c['Executive']}")
        with col3:
            if c.get("ActualLaitude") and c.get("ActualLongitude"):
                maps_url = (
                    f"https://maps.google.com/?q="
                    f"{c['ActualLaitude']},{c['ActualLongitude']}"
                )
                st.markdown(f"[📍 Actual location]({maps_url})")
        with col4:
            can_capture = status_key != "complete" or role == "admin"
            if can_capture:
                if st.button("📷 Capture", key=f"cap_{c['CustomerId']}"):
                    st.session_state.page = "capture"
                    st.session_state.selected_customer_id = c["CustomerId"]
                    st.session_state.pop("gps_lat", None)
                    st.session_state.pop("gps_lng", None)
                    st.rerun()

        st.divider()


# ── Capture page ───────────────────────────────────────────────────────────

def show_capture_page():
    show_sidebar()

    cid = st.session_state.get("selected_customer_id")
    if not cid:
        st.session_state.page = "dashboard"
        st.rerun()

    customer = get_customer_by_id(cid)
    if not customer:
        st.error("Customer not found.")
        st.session_state.page = "dashboard"
        st.rerun()

    if st.button("← Back to Dashboard"):
        st.session_state.page = "dashboard"
        st.rerun()

    st.title(f"📸 {customer['Customer']}")

    left, right = st.columns([1, 1.2])

    # ── Left: customer info ──
    with left:
        st.subheader("Customer Details")
        st.markdown(f"**Locality:** {customer['Locality']}")
        st.markdown(f"**Facility:** {customer['Facility']}")
        st.markdown(f"**Contact:** {customer['ContactNumber']}")
        st.markdown(f"**Executive:** {customer['Executive']}")

        if customer.get("Latitude") and customer.get("Longitude"):
            exp_url = f"https://maps.google.com/?q={customer['Latitude']},{customer['Longitude']}"
            st.markdown(f"**Expected Location:** [📍 View on Maps]({exp_url})")

        if customer.get("ActualLaitude") and customer.get("ActualLongitude"):
            act_url = (
                f"https://maps.google.com/?q="
                f"{customer['ActualLaitude']},{customer['ActualLongitude']}"
            )
            st.success(
                f"Last GPS: {customer['ActualLaitude']:.6f}, "
                f"{customer['ActualLongitude']:.6f}  "
                f"[📍 View]({act_url})"
            )

        st.subheader("Captured Images")
        for i, key in enumerate(["ImageUrl1", "ImageUrl2", "ImageUrl3"], 1):
            url = customer.get(key)
            if url:
                st.markdown(
                    f"**Image {i}:** &nbsp; "
                    f"<a href='{url}' target='_blank'>🔗 Open in Google Drive</a>",
                    unsafe_allow_html=True,
                )
                st.caption(f"Stored: {url}")
            else:
                st.caption(f"Image {i}: Not captured yet")

        if st.session_state.role == "admin" and any(
            customer.get(k) for k in ["ImageUrl1", "ImageUrl2", "ImageUrl3"]
        ):
            if st.button("🗑️ Clear All Images", type="secondary"):
                clear_customer_images(cid)
                st.success("All images cleared.")
                time.sleep(1)
                st.rerun()

    # ── Right: capture ──
    with right:
        slot = next_slot(customer)

        if slot is None:
            st.success("✅ All 3 images have been captured for this customer.")
            if st.session_state.role == "admin":
                st.info("Use 'Clear All Images' on the left to re-capture.")
            return

        st.subheader(f"Capture Image {slot} of 3")

        if not is_drive_configured():
            st.error(
                "Google Drive is not configured. "
                "Please add your Service Account to `.streamlit/secrets.toml`."
            )
            return

        # ── GPS ──
        st.markdown("**Step 1 — Location**")

        from streamlit_js_eval import get_geolocation

        gps = get_geolocation()

        if gps:
            lat = gps["coords"]["latitude"]
            lng = gps["coords"]["longitude"]
            st.session_state.gps_lat = lat
            st.session_state.gps_lng = lng
            st.success(f"📍 GPS acquired: {lat:.6f}, {lng:.6f}")
        elif st.session_state.get("gps_lat"):
            lat = st.session_state.gps_lat
            lng = st.session_state.gps_lng
            st.success(f"📍 GPS: {lat:.6f}, {lng:.6f}")
        else:
            st.warning(
                "Waiting for location… Allow location access when your browser asks, "
                "or enter coordinates manually below."
            )
            lat = None
            lng = None

        use_manual = st.checkbox("Enter location manually")
        if use_manual or lat is None:
            col_lat, col_lng = st.columns(2)
            with col_lat:
                lat = st.number_input("Latitude",  value=lat or 0.0, format="%.6f", key="manual_lat")
            with col_lng:
                lng = st.number_input("Longitude", value=lng or 0.0, format="%.6f", key="manual_lng")

        # ── Camera ──
        st.markdown("**Step 2 — Photo**")
        photo = st.camera_input(
            f"Take photo for Image {slot}",
            help="Allow camera access when prompted by your browser.",
        )

        # ── Submit ──
        if photo:
            st.markdown("**Step 3 — Upload**")

            if not lat or not lng:
                st.warning("Please provide location coordinates before submitting.")
            else:
                if st.button(
                    f"✅ Upload Image {slot}",
                    type="primary",
                    use_container_width=True,
                ):
                    with st.spinner("Uploading to Google Drive…"):
                        try:
                            img_bytes = photo.getvalue()
                            ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
                            filename  = (
                                f"{customer['Executive']}_{cid}_{ts}_img{slot}.jpg"
                            )
                            url = upload_image(img_bytes, filename)
                            update_image_slot(cid, slot, url, lat, lng)
                            st.success(f"Image {slot} uploaded successfully!")
                            st.balloons()
                            time.sleep(1.5)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Upload failed: {e}")


# ── Admin panel ─────────────────────────────────────────────────────────────

def show_admin_panel():
    if st.session_state.role != "admin":
        st.error("Access denied.")
        return

    show_sidebar()
    st.title("👥 User Management")

    tab_list, tab_add, tab_stats = st.tabs(["Users", "Add User", "Exec Stats"])

    # ── Tab: existing users ──
    with tab_list:
        users = get_all_users()
        if not users:
            st.info("No users found.")
        else:
            for u in users:
                active_icon = "✅" if u["is_active"] else "❌"
                with st.expander(
                    f"{active_icon}  {u['email']}  —  "
                    f"{'Admin' if u['role'] == 'admin' else 'SE'}"
                    + (f"  (`{u['executive_code']}`)" if u.get("executive_code") else "")
                ):
                    c1, c2 = st.columns(2)
                    with c1:
                        new_name   = st.text_input("Full Name",  value=u.get("full_name") or "", key=f"n_{u['id']}")
                        new_role   = st.selectbox("Role", ["admin", "se"],
                                                  index=0 if u["role"] == "admin" else 1,
                                                  key=f"r_{u['id']}")
                        exec_codes = get_distinct_executives()
                        ec_options = ["(none)"] + exec_codes
                        default_ec = u.get("executive_code") or "(none)"
                        ec_idx     = ec_options.index(default_ec) if default_ec in ec_options else 0
                        new_ec     = st.selectbox("Executive Code", ec_options,
                                                  index=ec_idx, key=f"e_{u['id']}")
                        new_active = st.checkbox("Active", value=bool(u["is_active"]), key=f"a_{u['id']}")
                    with c2:
                        st.caption(f"Created: {u['created_at']}")
                        new_pw = st.text_input("New Password (blank = keep)",
                                               type="password", key=f"p_{u['id']}")

                    bcol1, bcol2 = st.columns(2)
                    with bcol1:
                        if st.button("💾 Update", key=f"upd_{u['id']}"):
                            update_user(
                                u["id"], new_name, new_role,
                                None if new_ec == "(none)" else new_ec,
                                new_active,
                            )
                            if new_pw:
                                update_user_password(u["id"], hash_password(new_pw))
                            st.success("Updated successfully.")
                            st.rerun()
                    with bcol2:
                        if u["email"] != st.secrets["app"]["admin_email"]:
                            if st.button("🗑️ Delete", key=f"del_{u['id']}", type="secondary"):
                                delete_user(u["id"])
                                st.success("User deleted.")
                                st.rerun()

    # ── Tab: add user ──
    with tab_add:
        with st.form("add_user"):
            st.subheader("Create New User")
            a_email    = st.text_input("Email Address")
            a_name     = st.text_input("Full Name")
            a_password = st.text_input("Initial Password", type="password")
            a_role     = st.selectbox("Role", ["se", "admin"])
            exec_codes = get_distinct_executives()
            a_ec       = st.selectbox("Executive Code (SE only)", ["(none)"] + exec_codes)
            submitted  = st.form_submit_button("Create User", type="primary")

        if submitted:
            if not a_email or not a_password:
                st.error("Email and password are required.")
            else:
                try:
                    create_user(
                        a_email.strip().lower(),
                        hash_password(a_password),
                        a_name,
                        a_role,
                        None if a_ec == "(none)" else a_ec,
                    )
                    st.success(f"User **{a_email}** created. Initial password: `{a_password}`")
                except Exception as e:
                    if "Duplicate" in str(e):
                        st.error("An account with that email already exists.")
                    else:
                        st.error(f"Error: {e}")

    # ── Tab: executive stats ──
    with tab_stats:
        st.subheader("Capture Progress by Executive")
        rows = get_executive_stats()
        if rows:
            for r in rows:
                total    = r["total"]
                captured = r["captured"] or 0
                pct      = round(captured / total * 100) if total else 0
                st.markdown(f"**{r['Executive']}**  — {captured}/{total} ({pct}%)")
                st.progress(pct / 100)
        else:
            st.info("No data found.")


# ── Router ──────────────────────────────────────────────────────────────────

def main():
    _bootstrap()

    if not st.session_state.logged_in:
        show_login()
        return

    page = st.session_state.get("page", "dashboard")
    if page == "dashboard":
        show_dashboard()
    elif page == "capture":
        show_capture_page()
    elif page == "admin":
        show_admin_panel()


if __name__ == "__main__":
    main()
