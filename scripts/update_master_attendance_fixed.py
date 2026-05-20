import pandas as pd
from pathlib import Path
from datetime import datetime
import sys
import os

# Fix Windows console encoding for emoji support
if sys.platform == 'win32':
    os.system('chcp 65001 > nul')
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

# ===== PATHS =====
DAILY_CSV = Path("output/attendance/attendance.csv")
MASTER_CSV = Path("output/attendance/master_attendance.csv")

if not DAILY_CSV.exists():
    raise SystemExit(f"❌ Daily attendance file not found: {DAILY_CSV}")

# ===== READ DAILY ATTENDANCE =====
daily = pd.read_csv(DAILY_CSV)

if daily.empty:
    raise SystemExit("❌ Daily attendance is empty!")

# Extract date from first row (format: "2026-02-08 09:56:47")
date_str = daily['date'].iloc[0]
DATE_COL = date_str.split()[0]  # Extract just "2026-02-08"

print(f"📅 Processing attendance for: {DATE_COL}")

# ===== LOAD OR CREATE MASTER =====
if MASTER_CSV.exists():
    master = pd.read_csv(MASTER_CSV)
    print(f"📂 Loaded existing master with {len(master)} students")
else:
    print("📝 Creating new master attendance file")
    master = pd.DataFrame(columns=['name'])

# ===== ENSURE ALL STUDENTS ARE IN MASTER =====
all_students = set(daily['name'].unique())
existing_students = set(master['name'].unique()) if 'name' in master.columns else set()
new_students = all_students - existing_students

if new_students:
    print(f"➕ Adding {len(new_students)} new students: {', '.join(new_students)}")
    new_rows = pd.DataFrame({'name': list(new_students)})
    master = pd.concat([master, new_rows], ignore_index=True)

# ===== ADD/UPDATE DATE COLUMN =====
# Create a mapping from daily attendance
attendance_map = dict(zip(daily['name'], daily['present']))

# Add or update the date column - THIS IS THE FIX!
if DATE_COL not in master.columns:
    master[DATE_COL] = "NO"  # Initialize with NO
    print(f"✨ Created new column: {DATE_COL}")
else:
    print(f"🔄 Updating existing column: {DATE_COL}")

# Update attendance for each student
for idx, row in master.iterrows():
    student_name = row['name']
    if student_name in attendance_map:
        master.at[idx, DATE_COL] = attendance_map[student_name]

# ===== SORT AND SAVE =====
# Sort columns: name first, then dates in chronological order
date_columns = [col for col in master.columns if col != 'name']
date_columns.sort()
master = master[['name'] + date_columns]

# Sort rows by name
master = master.sort_values('name').reset_index(drop=True)

# Save
MASTER_CSV.parent.mkdir(parents=True, exist_ok=True)
master.to_csv(MASTER_CSV, index=False)

# ===== SUMMARY =====
print(f"\n✅ Updated: {MASTER_CSV}")
print(f"👥 Total students: {len(master)}")
print(f"📊 Date columns: {len(date_columns)}")

# Count present/absent for today
present_count = (master[DATE_COL] == "YES").sum()
absent_count = (master[DATE_COL] == "NO").sum()

print(f"\n📋 TODAY'S SUMMARY ({DATE_COL}):")
print(f"   ✓ Present: {present_count}")
print(f"   ✗ Absent:  {absent_count}")
print(f"   📈 Attendance rate: {present_count/len(master)*100:.1f}%")
