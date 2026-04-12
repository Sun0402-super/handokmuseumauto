import os

file_path = r"c:\Users\kr2200047\Documents\한독의약박물관 관람 후기 자동 수집\streamlit_app.py"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace("use_container_width=True", "width=\"stretch\"")

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Replacement complete.")
