# Noesis Pre-Edit Check

Whenever you receive a coding task:

1. Identify the target file and the specific function or class the task concerns.
2. Write a one-line description of the task.
3. Use these to fill in `<request>` and `<file:symbol>` below.

## Before editing any file, run:

```
python noesis.py check --repo . --change "<request>" --target <file:symbol>
```

- If `noesis.py` cannot be found, or the command errors out for any reason, **stop and tell the human**. Do not proceed with editing.

### Exit code 1 — investigate and resolve

Do **not** edit. Read every file or commit the report points to, then run:

```
python noesis.py resolve <unknown_id> --evidence "<what you found>" --source "<file:line or commit hash>"
```

Re-run the check command. If you notice a risk the tool missed, run:

```
python noesis.py add-unknown --category "<category>" --severity critical|major|minor --text "<description>"
```

Repeat investigating and resolving until the check returns exit code 0 or 2.

### Exit code 2 — stop completely

Show the human the printed questions exactly as they appear. Do **not** edit any files.

### Exit code 0 — proceed

You may edit, staying **only** within the files listed as the footprint in the report, and following any guardrails listed there.

## After editing, run:

```
python noesis.py drift --repo .
```

If it reports `DRIFT_DETECTED`, stop editing and go back to investigating the extra files it flagged before continuing.
