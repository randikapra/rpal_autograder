import os

def delete_zip_and_pdf_files(base_folder):
    deleted_files = 0
    for root, dirs, files in os.walk(base_folder):
        for file in files:
            if file.endswith(".zip") or file.endswith(".pdf"):
                file_path = os.path.join(root, file)
                try:
                    os.remove(file_path)
                    print(f"🗑️ Deleted: {file_path}")
                    deleted_files += 1
                except Exception as e:
                    print(f"⚠️ Error deleting {file_path}: {e}")
    print(f"\n✅ Done! Total files deleted: {deleted_files}")

if __name__ == "__main__":
    base_path = "/home/oshadi/SISR-Final_Year_Project/envs/grading_workspace/submissions"
    delete_zip_and_pdf_files(base_path)
