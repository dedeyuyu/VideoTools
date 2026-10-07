import codecs

path = r"d:\Antigravity\VideoTools\UI\ui_duet_video.py"
lines = codecs.open(path, 'r', 'utf-8').read().splitlines()

# find where we incorrectly replaced in refresh_task_list
# it looks like:
#             if self.time_slider.value() == 0:
#                 
#         # Update Scope Radios
bad_idx = -1
for i, l in enumerate(lines):
    if "if self.time_slider.value() == 0:" in l:
        if "# Update Scope Radios" in lines[i+2]:
            bad_idx = i
            break

if bad_idx != -1:
    # Remove the bad replacement block
    end_idx = bad_idx + 1
    while "self.time_slider.blockSignals(True)" not in lines[end_idx]:
        end_idx += 1
    
    # restore original line
    lines = lines[:bad_idx+1] + ["                self.time_slider.blockSignals(True)"] + lines[end_idx+1:]

codecs.open(path, 'w', 'utf-8').write('\n'.join(lines))
