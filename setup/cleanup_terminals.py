import os
import shutil
import time

TERMINALS_PARENT_FOLDER = r"C:\MQ45\Terminals"
DAYS_TO_KEEP = 0  # 0 = delete all

STATIC_FOLDERS = [
    "logs",
    "MQL5\\Logs",
    "tester\\logs"
]

EXCLUDED_BASE_FOLDERS = ["Custom", "Default", "signals"]

FOLDERS_TO_CLEAN = ["history", "ticks", "trades", "mail", "news", "subscriptions"]

def remove_and_recreate(folder_path):
    """Delete a folder entirely and recreate it empty."""
    try:
        if os.path.exists(folder_path):
            shutil.rmtree(folder_path)
        os.makedirs(folder_path, exist_ok=True)
        return True
    except Exception as e:
        print(f"❌ Failed to reset folder {folder_path}: {e}")
        return False

def clean_mt5_data():
    now = time.time()
    cutoff = now - (DAYS_TO_KEEP * 86400)
    total_deleted = 0
    total_size = 0

    for folder_name in os.listdir(TERMINALS_PARENT_FOLDER):
        if not folder_name.upper().startswith("T"):
            continue

        terminal_folder = os.path.join(TERMINALS_PARENT_FOLDER, folder_name)
        bases_folder = os.path.join(terminal_folder, "Bases")

        # 1️⃣ Clean static folders (full delete + recreate)
        for rel_path in STATIC_FOLDERS:
            folder_path = os.path.join(terminal_folder, rel_path)
            if os.path.exists(folder_path):
                # Calculate size and file count before removing
                for root, dirs, files in os.walk(folder_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        try:
                            if DAYS_TO_KEEP == 0 or os.path.getmtime(file_path) < cutoff:
                                total_size += os.path.getsize(file_path)
                                total_deleted += 1
                        except:
                            pass
                remove_and_recreate(folder_path)

        # 2️⃣ Dynamically detect broker server folders under /Bases
        if os.path.exists(bases_folder):
            server_folders = [
                p for p in os.listdir(bases_folder)
                if os.path.isdir(os.path.join(bases_folder, p))
                and not any(keyword.lower() == p.lower() for keyword in EXCLUDED_BASE_FOLDERS)
            ]

            for server_folder in server_folders:
                server_path = os.path.join(bases_folder, server_folder)

                for subfolder in FOLDERS_TO_CLEAN:
                    target = os.path.join(server_path, subfolder)
                    if os.path.exists(target):
                        # Calculate size before deletion
                        for root, dirs, files in os.walk(target):
                            for file in files:
                                file_path = os.path.join(root, file)
                                try:
                                    if DAYS_TO_KEEP == 0 or os.path.getmtime(file_path) < cutoff:
                                        total_size += os.path.getsize(file_path)
                                        total_deleted += 1
                                except:
                                    pass
                        remove_and_recreate(target)

    print(f"🧹 Cleanup complete: {total_deleted} files deleted ({total_size/1024/1024:.2f} MB freed)")

if __name__ == "__main__":
    clean_mt5_data()
