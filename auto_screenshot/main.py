# main.py
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import threading
import json
import os
from processor import process_urls

class VideoShotApp:
    def __init__(self, root):
        self.root = root
        self.root.title("视频批量截图软件")
        self.root.geometry("650x700") # 稍微调高一点高度
        
        self.config_file = "config.json"
        # 【新增】停止信号
        self.stop_event = threading.Event()
        
        # --- UI 布局 ---
        tk.Label(root, text="第一步: 输入视频链接:").pack(anchor="w", padx=15, pady=(15, 5))
        self.url_text = scrolledtext.ScrolledText(root, height=10)
        self.url_text.pack(fill="x", padx=15)
        
        config_frame = tk.LabelFrame(root, text="第二步: 设定参数")
        config_frame.pack(fill="x", padx=15, pady=15, ipadx=5, ipady=5)
        
        self.max_count_var = tk.IntVar(value=10)
        self.interval_var = tk.DoubleVar(value=0.5)
        self.base_name_var = tk.StringVar(value="截图项目")
        self.save_path_var = tk.StringVar()
        self.load_config()
        
        # 参数输入行
        tk.Label(config_frame, text="截取数量:").grid(row=0, column=0, sticky="e", pady=5)
        tk.Entry(config_frame, textvariable=self.max_count_var, width=10).grid(row=0, column=1, sticky="w")
        tk.Label(config_frame, text="间隔秒数:").grid(row=1, column=0, sticky="e", pady=5)
        tk.Entry(config_frame, textvariable=self.interval_var, width=10).grid(row=1, column=1, sticky="w")
        tk.Label(config_frame, text="主要名称:").grid(row=2, column=0, sticky="e", pady=5)
        tk.Entry(config_frame, textvariable=self.base_name_var, width=20).grid(row=2, column=1, sticky="w")
        tk.Label(config_frame, text="储存路径:").grid(row=3, column=0, sticky="e", pady=5)
        path_frame = tk.Frame(config_frame)
        path_frame.grid(row=3, column=1, sticky="w")
        tk.Entry(path_frame, textvariable=self.save_path_var, width=30, state="readonly").pack(side="left")
        tk.Button(path_frame, text="选择", command=self.select_folder).pack(side="left", padx=5)
        
        # --- 按钮区 (运行和停止) ---
        btn_frame = tk.Frame(root)
        btn_frame.pack(pady=10)
        
        self.run_btn = tk.Button(btn_frame, text="开始执行任务", command=self.start_task, bg="#4CAF50", fg="black", font=("黑体", 12, "bold"), width=15)
        self.run_btn.pack(side="left", padx=10)
        
        self.stop_btn = tk.Button(btn_frame, text="停止运行", command=self.stop_task, bg="#f44336", fg="white", font=("黑体", 12, "bold"), width=15, state="disabled")
        self.stop_btn.pack(side="left", padx=10)
        
        tk.Label(root, text="运行日志:").pack(anchor="w", padx=15)
        self.log_text = scrolledtext.ScrolledText(root, height=12, state="disabled", bg="#f0f0f0")
        self.log_text.pack(fill="both", padx=15, pady=(0, 15))

    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.save_path_var.set(data.get("save_path", ""))
            except: pass

    def save_config(self):
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump({"save_path": self.save_path_var.get()}, f, ensure_ascii=False, indent=4)

    def select_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.save_path_var.set(folder)
            self.save_config()

    def log(self, message):
        self.root.after(0, self._log_safe, message)
        
    def _log_safe(self, message):
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")

    def stop_task(self):
        """点击停止按钮触发"""
        self.stop_event.set() # 发出停止信号
        self.log("🛑 收到停止指令，正在结束当前任务...")
        self.stop_btn.config(state="disabled")

    def start_task(self):
        urls = self.url_text.get("1.0", tk.END).strip().split('\n')
        urls = [u.strip() for u in urls if u.strip()]
        
        if not urls or not self.save_path_var.get():
            messagebox.showwarning("提示", "请检查链接和路径！")
            return
            
        self.stop_event.clear() # 运行前重置停止信号
        self.run_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.log("=== 任务已启动 ===")
        
        threading.Thread(target=self.run_process, args=(urls,), daemon=True).start()

    def run_process(self, urls):
        process_urls(
            urls=urls,
            max_count=self.max_count_var.get(),
            interval=self.interval_var.get(),
            base_path=self.save_path_var.get(),
            base_folder_name=self.base_name_var.get(),
            log_callback=self.log,
            stop_event=self.stop_event # 将信号传给处理函数
        )
        self.root.after(0, self.reset_buttons)

    def reset_buttons(self):
        self.run_btn.config(state="normal")
        self.stop_btn.config(state="disabled")

if __name__ == "__main__":
    root = tk.Tk()
    app = VideoShotApp(root)
    root.mainloop()