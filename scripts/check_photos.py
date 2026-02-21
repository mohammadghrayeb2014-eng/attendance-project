"""
Quick check script - Shows how many training photos each student has
"""
from pathlib import Path

STUDENTS_DIR = Path("data/students")

def count_images(folder):
    exts = ["*.jpg", "*.png", "*.jpeg", "*.JPG", "*.PNG", "*.JPEG"]
    count = 0
    for ext in exts:
        count += len(list(folder.glob(ext)))
    return count

print("\n📸 STUDENT PHOTO COUNT:")
print("=" * 50)

total = 0
students = []

for student_dir in sorted(STUDENTS_DIR.iterdir()):
    if not student_dir.is_dir():
        continue
    
    count = count_images(student_dir)
    total += count
    students.append((student_dir.name, count))
    
    # Visual indicator
    if count >= 20:
        status = "✅ Excellent"
    elif count >= 15:
        status = "✓ Good"
    elif count >= 10:
        status = "⚠️ OK"
    else:
        status = "❌ Need more"
    
    print(f"{student_dir.name:15} | {count:3} photos | {status}")

print("=" * 50)
print(f"Total students: {len(students)}")
print(f"Total photos: {total}")
if len(students) > 0:
    print(f"Average: {total/len(students):.1f} photos/student")

print("\n💡 Recommendation: 15-20 photos per student for best accuracy!")
