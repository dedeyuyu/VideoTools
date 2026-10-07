import codecs
path = r'd:\Antigravity\VideoTools\UI\ui_duet_video.py'
lines = codecs.open(path, 'r', 'utf-8').read().splitlines()

# find duplicate global_speed lines and remove them
new_lines = []
for i, line in enumerate(lines):
    if 'global_speed=' in line:
        if any('global_speed=' in l for l in new_lines[-5:]):
            continue
    if 'max_3min=' in line:
        if any('max_3min=' in l for l in new_lines[-5:]):
            continue
    new_lines.append(line)

codecs.open(path, 'w', 'utf-8').write('\n'.join(new_lines))
