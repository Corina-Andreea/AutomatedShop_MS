import json

KB_PATH = 'C:\\Users\\Asus\\OneDrive\\Desktop\\Master\\An2\\MS_Lab\\Shop\\data\\supplier_kb.json'

def save_to_kb(data):
    with open(KB_PATH, "a") as f:
        f.write(json.dumps(data) + "\n")
