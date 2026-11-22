"""Colab only: copies the official JVS zip into a Drive folder on the server side.

Downloading the public file directly (gdown) often fails with "too many users have viewed or downloaded
this file"; a Drive-side copy into your own Drive does not. Run in the notebook kernel (it asks for
Google authorization): %run colab_fetch_jvs.py DRIVE_DIR
"""
import os
import sys
import time

JVS_DRIVE_ID = "19oAw8wWn3Y7z6CKChRdAyGOB9yupL_Xt"  # official JVS zip (3.5 GB)


def main(drive_dir):
    target = os.path.join(drive_dir, "jvs_ver1.zip")
    if os.path.exists(target):
        print("already there:", target, os.path.getsize(target))
        return
    from google.colab import auth
    from googleapiclient.discovery import build
    auth.authenticate_user()
    service = build("drive", "v3")
    # Resolve the Drive folder id of drive_dir (a path under /content/drive/MyDrive).
    parent = "root"
    for name in os.path.relpath(drive_dir, "/content/drive/MyDrive").split(os.sep):
        found = service.files().list(q=f"name = '{name}' and '{parent}' in parents and trashed = false and "
                                       "mimeType = 'application/vnd.google-apps.folder'",
                                     fields="files(id)").execute()["files"]
        parent = found[0]["id"]
    copy = service.files().copy(fileId=JVS_DRIVE_ID, body={"name": "jvs_ver1.zip", "parents": [parent]},
                                fields="id,size").execute()
    print("copied", copy)
    for _ in range(90):  # the mounted Drive shows the new file after a short delay
        if os.path.exists(target) and os.path.getsize(target) == int(copy["size"]):
            break
        time.sleep(10)
    print(target, os.path.exists(target) and os.path.getsize(target))


if __name__ == "__main__":
    main(sys.argv[1])
