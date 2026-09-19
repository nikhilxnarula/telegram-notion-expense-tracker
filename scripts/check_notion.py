"""Step 3. Verify the integration can see the database and the schema matches."""
import _bootstrap  # noqa: F401
from notion_writer import describe_database, get_category_options

EXPECTED = {"Name": "title", "Amount": "number", "Date": "date", "Category": "relation"}

props = describe_database()
print("Properties found in your Notion database:")
for name, kind in props.items():
    print(f"  {name:<20} {kind}")

print()
problems = []
for name, kind in EXPECTED.items():
    actual = props.get(name)
    if actual is None:
        problems.append(f"MISSING property '{name}' (expected type {kind})")
    elif actual != kind:
        problems.append(f"'{name}' is type '{actual}', expected '{kind}'")

if problems:
    print("Problems:")
    for problem in problems:
        print("  -", problem)
    raise SystemExit(1)

print("Schema OK.")
print("Category options:", ", ".join(get_category_options()))
