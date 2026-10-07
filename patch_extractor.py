import os
path = "auto_screenshot/extractor.py"
content = open(path, 'r', encoding='utf-8').read()
content = content.replace("'-i', video_path,", "'-i', os.path.abspath(video_path),")
open(path, 'w', encoding='utf-8').write(content)
