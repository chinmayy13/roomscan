"""Validate plan.json files against plan.schema.json.   python scripts/validate_schema.py out/*/plan.json"""
import json, sys
import jsonschema

schema = json.load(open("plan.schema.json"))
bad = 0
for path in sys.argv[1:]:
    try:
        jsonschema.validate(json.load(open(path)), schema)
        print("OK  ", path)
    except jsonschema.ValidationError as e:
        bad += 1
        print("FAIL", path, "->", e.message[:120])
sys.exit(1 if bad else 0)
