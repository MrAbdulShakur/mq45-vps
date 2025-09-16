import os
import shutil

# === CONFIGURATION ===
SOURCE_FOLDER = r"C:\MQ45\Metatrader5"     # Path to original MT5 terminal folder
DEST_PARENT_FOLDER = r"C:\MQ45\Terminals"  # Where to create the T1, T2... folders
RANGE_START = 1
RANGE_END = 32                        # Change as needed


def duplicate_mt5_terminals():
    if not os.path.exists(SOURCE_FOLDER):
        print(f"❌ Source folder does not exist: {SOURCE_FOLDER}")
        return
    
    os.makedirs(DEST_PARENT_FOLDER, exist_ok=True)

    for i in range(RANGE_START, RANGE_END + 1):
        dest_folder = os.path.join(DEST_PARENT_FOLDER, f"T{i}")
        if os.path.exists(dest_folder):
            print(f"⚠️  Skipping T{i}: Already exists")
            continue
        try:
            print(f"🔁 Copying to {dest_folder}...")
            shutil.copytree(SOURCE_FOLDER, dest_folder)
            print(f"✅ Created {dest_folder}")
        except Exception as e:
            print(f"❌ Failed to create T{i}: {e}")

if __name__ == "__main__":
    duplicate_mt5_terminals()
