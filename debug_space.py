from pathlib import Path
import os

path_with_space = Path("storage/metadata/4G5G .json")
path_no_space = Path("storage/metadata/4G5G.json")

print(f"Checking '{path_with_space}'...")
if path_with_space.exists():
    print("  EXISTS")
    try:
        with open(path_with_space, "r") as f:
            print("  READ SUCCESS")
    except Exception as e:
        print(f"  READ FAILED: {e}")
else:
    print("  DOES NOT EXIST")

print(f"Checking '{path_no_space}'...")
if path_no_space.exists():
    print("  EXISTS")
else:
    print("  DOES NOT EXIST")
