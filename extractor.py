import os
import zipfile

def extract_nested_zipfiles(base_folder):
    for root, dirs, files in os.walk(base_folder):
        for file in files:
            if file.endswith(".zip"):
                zip_path = os.path.join(root, file)
                extract_to = root
                try:
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        zip_ref.extractall(extract_to)
                    print(f"✅ Extracted '{zip_path}' to '{extract_to}'")
                except zipfile.BadZipFile:
                    print(f"❌ Failed to extract '{zip_path}': Bad ZIP file")

if __name__ == "__main__":
    base_path = "/home/oshadi/SISR-Final_Year_Project/envs/grading_workspace/submissions"
    extract_nested_zipfiles(base_path)
