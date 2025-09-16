import subprocess
import os
import sys
import json
import re

def parse_log(log_content):
    errors = []
    stats = {"errors": 0, "warnings": 0}

    for line in log_content.splitlines():
        match = re.search(r"\((\d+),(\d+)\)\s*:\s*(error|warning)\s*\d+:\s*(.*)", line)
        if match:
            line_num, col_num, etype, msg = match.groups()
            errors.append({
                "line": int(line_num),
                "column": int(col_num),
                "type": etype,
                "error": msg.strip()
            })
            stats["errors" if etype == "error" else "warnings"] += 1

        if line.lower().startswith("result:"):
            parts = re.findall(r"(\d+)\s+(\w+)", line, re.IGNORECASE)
            for count, label in parts:
                stats[label.lower()] = int(count)

    return errors, stats

def compile_ea(metaeditor_path, source_file, log_file):
    try:
        subprocess.run(
            [metaeditor_path, f"/compile:{source_file}", f"/log:{log_file}"],
            capture_output=True,
            text=True
        )

        result_obj = {
            "errors": [],
            "stats": {}
        }

        if os.path.exists(log_file):
            with open(log_file, "r", encoding="utf-16") as f:
                log_content = f.read()

            errors, stats = parse_log(log_content)

            result_obj["errors"] = errors
            result_obj["stats"] = stats


    except Exception as e:
        return {
            "errors": [],
            "stats": {}
        }
    finally:
        # cleanup: delete mq5 and log files
        for f in [source_file, log_file]:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except Exception:
                pass
    
    
    return result_obj

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Missing args"}))
        sys.exit(1)
    
    file_path = sys.argv[1]
    filename = sys.argv[2]
    
    log_file_dir = os.path.join(os.getcwd(), "logs")
    os.makedirs(log_file_dir, exist_ok=True)
    
    log_file = os.path.join(log_file_dir, f"{filename}.log")
    
    metaeditor_path = r"C:\MQ45\Metatrader5\MetaEditor64.exe"

    # Run compiler and return JSON result
    result = compile_ea(metaeditor_path, file_path, log_file)
    print(json.dumps(result))

