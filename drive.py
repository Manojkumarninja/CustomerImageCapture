import io
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.errors import HttpError

_SCOPES = ["https://www.googleapis.com/auth/drive"]


def is_drive_configured() -> bool:
    try:
        key = st.secrets["gcp_service_account"]
        return key.get("project_id", "REPLACE") != "REPLACE_WITH_PROJECT_ID"
    except Exception:
        return False


def _get_service():
    creds = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=_SCOPES,
    )
    return build("drive", "v3", credentials=creds)


def upload_image(image_bytes: bytes, filename: str) -> str:
    """
    Upload image_bytes to the configured Drive folder.
    Makes the file publicly readable and returns a direct-view URL.
    """
    if not is_drive_configured():
        raise RuntimeError(
            "Google Drive is not configured yet. "
            "Add your service account credentials to .streamlit/secrets.toml."
        )

    try:
        service   = _get_service()
        folder_id = st.secrets["drive"]["folder_id"]

        file_meta = {"name": filename, "parents": [folder_id]}
        media = MediaIoBaseUpload(
            io.BytesIO(image_bytes), mimetype="image/jpeg", resumable=False
        )

        file = (
            service.files()
            .create(
                body=file_meta,
                media_body=media,
                fields="id,webViewLink",
                supportsAllDrives=True,
            )
            .execute()
        )

        return file.get("webViewLink", f"https://drive.google.com/file/d/{file['id']}/view")

    except HttpError as e:
        raise RuntimeError(f"Drive upload failed: {e}") from e
