import uuid
import json

# Load your fixture file
with open('initial_fixtures.json', 'r') as f:
    data = json.load(f)

# Generate UUIDs for each record
for item in data:
    # Replace integer pk with UUID
    item['pk'] = str(uuid.uuid4())

    # If you need to maintain relationships, you'll need to
    # track old_pk -> new_uuid mapping for references

# Save the converted fixture
with open('initial_fixtures1.json', 'w') as f:
    json.dump(data, f, indent=4)

