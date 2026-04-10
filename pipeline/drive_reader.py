"""
Google Drive folder traversal for the Spark Expense Engine.

Walks the contractor folder tree on Google Drive and returns a list of
receipt files.

CRITICAL — Shared Drive flags:
The Spark Expenses parent folder lives in a Shared Drive (not My Drive).
Every Drive API call in this module MUST pass:
    supportsAllDrives=True
    includeItemsFromAllDrives=True   (only on .list() calls)
Without these flags the API returns 404 for shared-drive folders.
See CLAUDE.md "CRITICAL: Shared Drive flags" for the full story.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from googleapiclient.discovery import build

from google_auth import load_credentials


@dataclass
class DriveReceipt:
    """One receipt file discovered in Drive (not yet downloaded or processed)."""
    file_id: str
    name: str
    mime_type: str
    size_bytes: Optional[int]
    contractor_id: str       # e.g. "brandon"
    project_id: str          # folder name under contractor, e.g. "NDL - 2026"
    drive_path: str          # for display: "brandon/NDL - 2026/foo.pdf"


def _build_service():
    return build("drive", "v3", credentials=load_credentials())


def list_receipts_for_contractor(
    contractor_id: str,
    contractor_folder_id: str,
) -> list[DriveReceipt]:
    """List every receipt file in a contractor's project folders.

    Walks one level down: <contractor>/<project>/<files>. Each project
    subfolder name becomes the project_id on the returned receipts.
    Folders nested deeper than that are ignored (intentional — keeps
    contractors from accidentally creating sub-buckets that confuse the
    rules engine).
    """
    svc = _build_service()
    receipts: list[DriveReceipt] = []

    project_folders = svc.files().list(
        q=(
            f"'{contractor_folder_id}' in parents "
            f"and mimeType='application/vnd.google-apps.folder' "
            f"and trashed=false"
        ),
        fields="files(id,name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
        pageSize=100,
    ).execute().get("files", [])

    for project in project_folders:
        project_id = project["name"]
        files = svc.files().list(
            q=(
                f"'{project['id']}' in parents "
                f"and trashed=false "
                f"and mimeType != 'application/vnd.google-apps.folder'"
            ),
            fields="files(id,name,mimeType,size)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            pageSize=1000,
        ).execute().get("files", [])

        for f in files:
            receipts.append(
                DriveReceipt(
                    file_id=f["id"],
                    name=f["name"],
                    mime_type=f["mimeType"],
                    size_bytes=int(f["size"]) if "size" in f else None,
                    contractor_id=contractor_id,
                    project_id=project_id,
                    drive_path=f"{contractor_id}/{project_id}/{f['name']}",
                )
            )

    return receipts


def download_file_bytes(file_id: str) -> bytes:
    """Download a Drive file's raw bytes."""
    svc = _build_service()
    return svc.files().get_media(
        fileId=file_id,
        supportsAllDrives=True,
    ).execute()
