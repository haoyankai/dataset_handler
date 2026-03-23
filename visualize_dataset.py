import os
import json
import shutil
import random
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from PIL import Image, ImageTk

class ToolTip:
    """为控件创建工具提示"""
    def __init__(self, widget, text='widget info'):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        self.id = None
        self.x = self.y = 0

    def showtip(self):
        """显示工具提示窗口"""
        self.hidetip()
        x, y, _, _ = self.widget.bbox("insert")
        x = x + self.widget.winfo_rootx() + 25
        y = y + self.widget.winfo_rooty() + 25
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                         background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                         font=("tahoma", "8", "normal"))
        label.pack()

    def hidetip(self):
        if self.tipwindow:
            self.tipwindow.destroy()
        self.tipwindow = None

class RatioDialog(tk.Toplevel):
    """比例输入对话框"""
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("设置拆分比例")
        self.geometry("300x200")
        self.resizable(False, False)

        tk.Label(self, text="训练比例 (默认70):").pack(pady=5)
        self.train_var = tk.StringVar(value="70")
        tk.Entry(self, textvariable=self.train_var).pack(pady=5)

        tk.Label(self, text="验证比例 (默认20):").pack(pady=5)
        self.valid_var = tk.StringVar(value="20")
        tk.Entry(self, textvariable=self.valid_var).pack(pady=5)

        tk.Label(self, text="测试比例 (默认10):").pack(pady=5)
        self.test_var = tk.StringVar(value="10")
        tk.Entry(self, textvariable=self.test_var).pack(pady=5)

        tk.Button(self, text="确定", command=self.ok).pack(pady=10)
        tk.Button(self, text="取消", command=self.destroy).pack()

        self.result = None
        self.grab_set()

    def ok(self):
        try:
            train = float(self.train_var.get())
            valid = float(self.valid_var.get())
            test = float(self.test_var.get())
            total = train + valid + test
            if abs(total - 100) > 1e-6:
                messagebox.showerror("错误", "比例之和必须为100")
                return
            self.result = (train/100, valid/100, test/100)
            self.destroy()
        except ValueError:
            messagebox.showerror("错误", "请输入有效的数字")

class YOLOViewer:
    def __init__(self, root):
        self.root = root
        self.root.title("YOLO / COCO 数据集可视化工具")
        self.root.geometry("1000x700")

        # 变量
        self.mode = None                 # 'yolo' 或 'coco'
        self.image_paths = []             # 所有图片的完整路径
        self.label_paths = []              # YOLO 模式：对应的标签路径
        self.current_index = 0
        self.class_names = {}              # YOLO 类别 ID -> 名称 (如果有 classes.txt)
        self.img_display = None             # 保持 PhotoImage 引用

        # COCO 专用数据结构
        self.coco_images = []               # 列表，元素为 {'id': int, 'file_name': str, 'width': int, 'height': int}
        self.coco_annotations = {}           # dict: image_id -> list of annotations
        self.coco_categories = {}            # dict: category_id -> name

        # 创建 GUI 组件
        self.create_widgets()

        # 绑定键盘事件
        self.root.bind_all('<Up>', self.on_key_up)
        self.root.bind_all('<Down>', self.on_key_down)
        self.root.bind_all('<Delete>', self.on_key_delete)
        self.root.bind_all('<Shift-Delete>', self.on_key_shift_delete)

    def create_widgets(self):
        # 使用 PanedWindow 以便调整左右区域比例
        self.paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, sashrelief=tk.RAISED, sashwidth=5)
        self.paned.pack(fill=tk.BOTH, expand=True)

        # ========== 左侧：图片列表 ==========
        left_frame = tk.Frame(self.paned, bg='lightgray', width=200)
        self.paned.add(left_frame, minsize=150)

        lbl_list = tk.Label(left_frame, text="图片列表 (单击切换, Ctrl+单击多选, Shift+单击范围)", 
                            bg='lightgray', font=('Arial', 9))
        lbl_list.pack(pady=5)

        list_frame = tk.Frame(left_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, 
                                   selectmode=tk.MULTIPLE, bg='white', 
                                   exportselection=False)
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar.config(command=self.listbox.yview)

        self.listbox.bind('<Button-1>', self.on_listbox_click, add=True)

        # ========== 右侧：图片显示区域 ==========
        right_frame = tk.Frame(self.paned)
        self.paned.add(right_frame, minsize=400, width=800)

        # 顶部框架：路径选择和文件信息
        top_frame = tk.Frame(right_frame)
        top_frame.pack(fill=tk.X, padx=5, pady=5)

        self.btn_select = tk.Button(top_frame, text="选择YOLO数据集目录", command=self.select_directory)
        self.btn_select.pack(side=tk.LEFT, padx=5)

        self.btn_coco = tk.Button(top_frame, text="加载COCO数据集", command=self.load_coco_dataset)
        self.btn_coco.pack(side=tk.LEFT, padx=5)

        self.btn_split = tk.Button(top_frame, text="拆分COCO", command=self.split_coco_dataset, state=tk.DISABLED)
        self.btn_split.pack(side=tk.LEFT, padx=5)

        self.btn_merge = tk.Button(top_frame, text="合并COCO", command=self.merge_coco_datasets)
        self.btn_merge.pack(side=tk.LEFT, padx=5)

        self.lbl_info = tk.Label(top_frame, text="未加载数据集", anchor=tk.W)
        self.lbl_info.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # 画布区域
        canvas_frame = tk.Frame(right_frame, bd=2, relief=tk.SUNKEN)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.canvas = tk.Canvas(canvas_frame, bg='gray', width=800, height=600)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # 底部按钮框架
        bottom_frame = tk.Frame(right_frame)
        bottom_frame.pack(fill=tk.X, padx=5, pady=5)

        self.btn_prev = tk.Button(bottom_frame, text="上一张", command=self.prev_image, state=tk.DISABLED)
        self.btn_prev.pack(side=tk.LEFT, padx=5)

        self.btn_next = tk.Button(bottom_frame, text="下一张", command=self.next_image, state=tk.DISABLED)
        self.btn_next.pack(side=tk.LEFT, padx=5)

        self.btn_delete = tk.Button(bottom_frame, text="删除选中", command=self.delete_selected, 
                                    state=tk.DISABLED, bg='#ffcccc')
        self.btn_delete.pack(side=tk.LEFT, padx=5)

        self.lbl_filename = tk.Label(bottom_frame, text="", anchor=tk.W)
        self.lbl_filename.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=20)

        tk.Label(bottom_frame, text="快捷键: ↑/↓切换  Del删除(确认)  Shift+Del直接删除", 
                 fg='gray').pack(side=tk.RIGHT, padx=10)

        self.create_tooltip(self.lbl_filename)

    def create_tooltip(self, widget):
        tooltip = ToolTip(widget)
        def on_enter(event):
            tooltip.text = widget.cget("text")
            tooltip.showtip()
        def on_leave(event):
            tooltip.hidetip()
        widget.bind('<Enter>', on_enter)
        widget.bind('<Leave>', on_leave)

    # ==================== YOLO 数据集加载 ====================
    def select_directory(self):
        dir_path = filedialog.askdirectory(title="选择数据集根目录")
        if not dir_path:
            return

        images_dir = os.path.join(dir_path, "images")
        labels_dir = os.path.join(dir_path, "labels")

        if not os.path.isdir(images_dir):
            images_dir = filedialog.askdirectory(title="选择图片文件夹")
            if not images_dir:
                return
            labels_dir = filedialog.askdirectory(title="选择标签文件夹")
            if not labels_dir:
                return

        self.load_yolo_dataset(images_dir, labels_dir)

    def load_yolo_dataset(self, images_dir, labels_dir):
        img_extensions = ('.jpg', '.jpeg', '.png', '.bmp')
        all_files = os.listdir(images_dir)
        img_files = [f for f in all_files if f.lower().endswith(img_extensions)]
        img_files.sort()

        if not img_files:
            messagebox.showerror("错误", "指定文件夹中没有找到图片文件")
            return

        self.image_paths = []
        self.label_paths = []

        for img_file in img_files:
            base_name = os.path.splitext(img_file)[0]
            img_path = os.path.join(images_dir, img_file)
            label_path = os.path.join(labels_dir, base_name + ".txt")
            self.image_paths.append(img_path)
            if os.path.isfile(label_path):
                self.label_paths.append(label_path)
            else:
                self.label_paths.append(None)

        classes_path = os.path.join(labels_dir, "classes.txt")
        if not os.path.isfile(classes_path):
            classes_path = os.path.join(os.path.dirname(labels_dir), "classes.txt")
        self.class_names = {}
        if os.path.isfile(classes_path):
            with open(classes_path, 'r') as f:
                for idx, line in enumerate(f):
                    self.class_names[idx] = line.strip()

        self.mode = 'yolo'
        self.btn_split.config(state=tk.DISABLED)
        self._update_listbox_and_display()

    # ==================== COCO 数据集加载 ====================
    def load_coco_dataset(self):
        # 选择图片文件夹
        img_dir = filedialog.askdirectory(title="选择COCO图片文件夹")
        if not img_dir:
            return

        # 选择标注 JSON 文件
        json_path = filedialog.askopenfilename(
            title="选择COCO标注文件",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not json_path:
            return

        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                coco_data = json.load(f)
        except Exception as e:
            messagebox.showerror("错误", f"无法加载JSON文件：{e}")
            return

        # 解析 categories
        self.coco_categories = {}
        for cat in coco_data.get('categories', []):
            self.coco_categories[cat['id']] = cat['name']

        # 解析 images
        self.coco_images = []
        id_to_filename = {}  # 用于快速查找
        for img in coco_data.get('images', []):
            self.coco_images.append({
                'id': img['id'],
                'file_name': img['file_name'],
                'width': img.get('width', 0),
                'height': img.get('height', 0)
            })
            id_to_filename[img['id']] = img['file_name']

        # 解析 annotations，按 image_id 分组
        self.coco_annotations = {}
        for ann in coco_data.get('annotations', []):
            img_id = ann['image_id']
            if img_id not in self.coco_annotations:
                self.coco_annotations[img_id] = []
            # 保留必要字段：segmentation, bbox, category_id
            self.coco_annotations[img_id].append({
                'segmentation': ann.get('segmentation'),
                'bbox': ann.get('bbox'),
                'category_id': ann['category_id']
            })

        # 构建图片路径列表，只保留 JSON 中存在的图片（且实际存在于文件夹中）
        self.image_paths = []
        valid_ids = set()
        for img_info in self.coco_images:
            fname = img_info['file_name']
            full_path = os.path.join(img_dir, fname)
            if os.path.isfile(full_path):
                self.image_paths.append(full_path)
                valid_ids.add(img_info['id'])
            else:
                print(f"警告：图片文件不存在 {full_path}")

        # 移除无效图片对应的标注
        for img_id in list(self.coco_annotations.keys()):
            if img_id not in valid_ids:
                del self.coco_annotations[img_id]

        if not self.image_paths:
            messagebox.showerror("错误", "在指定文件夹中没有找到JSON中对应的图片文件")
            return

        self.mode = 'coco'
        self.class_names = self.coco_categories
        self.btn_split.config(state=tk.NORMAL)
        self._update_listbox_and_display()

    # ==================== 公共更新方法 ====================
    def _update_listbox_and_display(self):
        """更新列表和显示第一张图片"""
        self.listbox.delete(0, tk.END)
        for img_path in self.image_paths:
            self.listbox.insert(tk.END, os.path.basename(img_path))

        self.current_index = 0 if self.image_paths else -1
        self.lbl_info.config(text=f"共 {len(self.image_paths)} 张图片 ({self.mode.upper()})")
        if self.image_paths:
            self.btn_prev.config(state=tk.NORMAL)
            self.btn_next.config(state=tk.NORMAL)
            # COCO 模式下禁用删除按钮（避免修改 JSON 的复杂性）
            if self.mode == 'coco':
                self.btn_delete.config(state=tk.DISABLED)
            else:
                self.btn_delete.config(state=tk.NORMAL)
            self.show_image(0)
        else:
            self.btn_prev.config(state=tk.DISABLED)
            self.btn_next.config(state=tk.DISABLED)
            self.btn_delete.config(state=tk.DISABLED)

    def on_listbox_click(self, event):
        index = event.widget.nearest(event.y)
        if index < 0 or index >= len(self.image_paths):
            return

        ctrl = (event.state & 0x0004) != 0
        shift = (event.state & 0x0001) != 0

        if not ctrl and not shift:
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(index)
            self.show_image(index)
            return "break"
        else:
            def update_display():
                sel = self.listbox.curselection()
                if sel:
                    first = sel[0]
                    if first != self.current_index:
                        self.show_image(first)
            self.root.after_idle(update_display)

    def show_image(self, index):
        if not self.image_paths or index < 0 or index >= len(self.image_paths):
            return

        self.current_index = index
        img_path = self.image_paths[index]

        try:
            pil_img = Image.open(img_path)
        except Exception as e:
            messagebox.showerror("错误", f"无法加载图片：{img_path}\n{e}")
            return

        orig_w, orig_h = pil_img.size

        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        if canvas_w <= 1 or canvas_h <= 1:
            canvas_w, canvas_h = 800, 600

        scale = min(canvas_w / orig_w, canvas_h / orig_h)
        new_w = int(orig_w * scale)
        new_h = int(orig_h * scale)
        offset_x = (canvas_w - new_w) // 2
        offset_y = (canvas_h - new_h) // 2

        resized = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        self.img_display = ImageTk.PhotoImage(resized)

        self.canvas.delete("all")
        self.canvas.create_image(offset_x, offset_y, anchor=tk.NW, image=self.img_display)

        # 根据模式绘制标注
        if self.mode == 'yolo':
            self._draw_yolo_annotations(index, orig_w, orig_h, scale, offset_x, offset_y)
        elif self.mode == 'coco':
            self._draw_coco_annotations(index, orig_w, orig_h, scale, offset_x, offset_y)

        filename = os.path.basename(img_path)
        self.lbl_filename.config(text=f"{index+1}/{len(self.image_paths)} - {filename}")

    def _draw_yolo_annotations(self, img_idx, orig_w, orig_h, scale, offset_x, offset_y):
        """绘制YOLO格式的标注"""
        label_path = self.label_paths[img_idx]
        if not label_path or not os.path.isfile(label_path):
            return

        with open(label_path, 'r') as f:
            lines = f.readlines()

        for line in lines:
            parts = line.strip().split()
            if len(parts) != 5:
                continue
            class_id, x_center, y_center, width, height = map(float, parts)
            x_center_pix = x_center * orig_w
            y_center_pix = y_center * orig_h
            box_w_pix = width * orig_w
            box_h_pix = height * orig_h

            x1 = x_center_pix - box_w_pix / 2
            y1 = y_center_pix - box_h_pix / 2
            x2 = x_center_pix + box_w_pix / 2
            y2 = y_center_pix + box_h_pix / 2

            self._draw_rect(x1, y1, x2, y2, int(class_id), scale, offset_x, offset_y)

    def _draw_coco_annotations(self, img_idx, orig_w, orig_h, scale, offset_x, offset_y):
        """绘制COCO格式的标注（优先使用分割多边形，后备使用边界框）"""
        # 获取当前图片的ID
        img_path = self.image_paths[img_idx]
        fname = os.path.basename(img_path)
        img_id = None
        for img_info in self.coco_images:
            if img_info['file_name'] == fname:
                img_id = img_info['id']
                break
        if img_id is None:
            return

        annotations = self.coco_annotations.get(img_id, [])
        for ann in annotations:
            cat_id = ann['category_id']
            color = self.get_color(cat_id)
            label_text = self.class_names.get(cat_id, str(cat_id))

            # 优先绘制分割多边形
            seg = ann.get('segmentation')
            if seg and isinstance(seg, list) and len(seg) > 0:
                # COCO segmentation 可以是多边形列表（每个多边形是一个点的列表）
                for polygon in seg:
                    if isinstance(polygon, list) and len(polygon) >= 6:
                        points = [(polygon[i], polygon[i+1]) for i in range(0, len(polygon), 2)]
                        self._draw_polygon(points, color, label_text, scale, offset_x, offset_y)
            elif ann.get('bbox'):
                # 如果没有分割，则使用边界框
                bbox = ann['bbox']
                x, y, w, h = bbox
                x1, y1, x2, y2 = x, y, x + w, y + h
                self._draw_rect(x1, y1, x2, y2, cat_id, scale, offset_x, offset_y, label_text)

    def _draw_polygon(self, points, color, label_text, scale, offset_x, offset_y):
        """在画布上绘制多边形（轮廓）和类别标签"""
        if len(points) < 3:
            return
        canvas_points = []
        min_x, min_y = float('inf'), float('inf')
        for (x, y) in points:
            cx = x * scale + offset_x
            cy = y * scale + offset_y
            canvas_points.extend([cx, cy])
            if cx < min_x: min_x = cx
            if cy < min_y: min_y = cy

        self.canvas.create_polygon(canvas_points, outline=color, fill='', width=2)
        self.canvas.create_text(
            min_x, min_y - 5,
            text=label_text, fill=color, anchor=tk.SW,
            font=("Arial", 10, "bold")
        )

    def _draw_rect(self, x1, y1, x2, y2, class_id, scale, offset_x, offset_y, label_text=None):
        """在画布上绘制矩形和类别标签"""
        x1_canvas = x1 * scale + offset_x
        y1_canvas = y1 * scale + offset_y
        x2_canvas = x2 * scale + offset_x
        y2_canvas = y2 * scale + offset_y

        color = self.get_color(class_id)
        self.canvas.create_rectangle(
            x1_canvas, y1_canvas, x2_canvas, y2_canvas,
            outline=color, width=2
        )
        if label_text is None:
            label_text = self.class_names.get(class_id, str(class_id))
        self.canvas.create_text(
            x1_canvas, y1_canvas - 5,
            text=label_text, fill=color, anchor=tk.SW,
            font=("Arial", 10, "bold")
        )

    def get_color(self, class_id):
        colors = ["red", "green", "blue", "cyan", "magenta", "yellow", "orange", "purple"]
        return colors[class_id % len(colors)]

    def prev_image(self):
        if self.current_index > 0:
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(self.current_index - 1)
            self.show_image(self.current_index - 1)

    def next_image(self):
        if self.current_index < len(self.image_paths) - 1:
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(self.current_index + 1)
            self.show_image(self.current_index + 1)

    def on_key_up(self, event):
        self.prev_image()

    def on_key_down(self, event):
        self.next_image()

    def on_key_delete(self, event):
        if self.mode == 'coco':
            messagebox.showinfo("提示", "COCO模式下不支持删除操作（如需删除请手动管理文件）")
            return
        self.delete_selected(confirm=True)

    def on_key_shift_delete(self, event):
        if self.mode == 'coco':
            messagebox.showinfo("提示", "COCO模式下不支持删除操作（如需删除请手动管理文件）")
            return
        self.delete_selected(confirm=False)

    def delete_selected(self, confirm=True):
        if self.mode == 'coco':
            return
        selected_indices = self.listbox.curselection()
        if not selected_indices:
            messagebox.showinfo("提示", "没有选中任何图片")
            return

        files_to_delete = []
        for idx in selected_indices:
            img_path = self.image_paths[idx]
            label_path = self.label_paths[idx]
            files_to_delete.append(f"图片: {img_path}" + (f"\n标签: {label_path}" if label_path else " (无标签)"))

        if confirm:
            msg = f"确定要删除以下 {len(selected_indices)} 项吗？\n\n" + "\n\n".join(files_to_delete)
            if not messagebox.askyesno("确认删除", msg):
                return

        indices_sorted = sorted(selected_indices, reverse=True)
        for idx in indices_sorted:
            img_path = self.image_paths[idx]
            label_path = self.label_paths[idx]

            try:
                os.remove(img_path)
            except Exception as e:
                messagebox.showerror("错误", f"删除图片失败：{img_path}\n{e}")
                return

            if label_path and os.path.isfile(label_path):
                try:
                    os.remove(label_path)
                except Exception as e:
                    messagebox.showerror("错误", f"删除标签失败：{label_path}\n{e}")
                    return

            del self.image_paths[idx]
            del self.label_paths[idx]

        self.listbox.delete(0, tk.END)
        for img_path in self.image_paths:
            self.listbox.insert(tk.END, os.path.basename(img_path))

        if self.image_paths:
            new_index = min(indices_sorted[-1], len(self.image_paths)-1)
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(new_index)
            self.show_image(new_index)
            self.lbl_info.config(text=f"共 {len(self.image_paths)} 张图片 ({self.mode.upper()})")
        else:
            self.canvas.delete("all")
            self.lbl_filename.config(text="")
            self.lbl_info.config(text="数据集为空")
            self.btn_prev.config(state=tk.DISABLED)
            self.btn_next.config(state=tk.DISABLED)
            self.btn_delete.config(state=tk.DISABLED)
            self.current_index = -1

    # ==================== 拆分 COCO 数据集 ====================
    def split_coco_dataset(self):
        if self.mode != 'coco' or not self.coco_images:
            messagebox.showinfo("提示", "请先加载一个COCO数据集")
            return

        # 获取比例
        dlg = RatioDialog(self.root)
        self.root.wait_window(dlg)
        if dlg.result is None:
            return
        train_ratio, valid_ratio, test_ratio = dlg.result

        # 选择输出目录
        out_dir = filedialog.askdirectory(title="选择输出目录")
        if not out_dir:
            return

        # 准备数据
        total = len(self.image_paths)
        indices = list(range(total))
        random.shuffle(indices)
        train_end = int(total * train_ratio)
        valid_end = train_end + int(total * valid_ratio)
        train_indices = indices[:train_end]
        valid_indices = indices[train_end:valid_end] if valid_ratio > 0 else []
        test_indices = indices[valid_end:] if test_ratio > 0 else []

        splits = {
            'train': train_indices,
            'valid': valid_indices,
            'test': test_indices
        }

        for split_name, split_indices in splits.items():
            if not split_indices:
                continue

            # 创建子目录
            split_dir = os.path.join(out_dir, split_name)
            images_dir = os.path.join(split_dir, 'images')
            os.makedirs(images_dir, exist_ok=True)

            # 收集该子集的图片ID和标注
            split_image_ids = set()
            split_images = []
            split_annotations = []

            # 建立原图片ID到新文件名的映射（如果重名冲突？这里不冲突，因为原文件名已唯一）
            for idx in split_indices:
                img_path = self.image_paths[idx]
                fname = os.path.basename(img_path)
                # 查找对应的图片信息
                img_info = None
                for info in self.coco_images:
                    if info['file_name'] == fname:
                        img_info = info
                        break
                if img_info is None:
                    continue
                img_id = img_info['id']
                split_image_ids.add(img_id)
                split_images.append(img_info.copy())  # 保留原ID
                # 复制图片
                dst_path = os.path.join(images_dir, fname)
                shutil.copy2(img_path, dst_path)

            # 收集标注
            for img_id in split_image_ids:
                anns = self.coco_annotations.get(img_id, [])
                for ann in anns:
                    split_annotations.append({
                        'id': len(split_annotations) + 1,  # 新标注ID从1开始
                        'image_id': img_id,
                        'category_id': ann['category_id'],
                        'bbox': ann['bbox'],
                        'segmentation': ann['segmentation'],
                        'area': ann['bbox'][2] * ann['bbox'][3] if ann.get('bbox') else 0,
                        'iscrowd': 0
                    })

            # 构建新的COCO JSON
            new_coco = {
                'images': split_images,
                'annotations': split_annotations,
                'categories': [{'id': cid, 'name': name} for cid, name in self.coco_categories.items()]
            }

            # 保存JSON
            json_path = os.path.join(split_dir, '_annotations.coco.json')
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(new_coco, f, indent=2)

        messagebox.showinfo("完成", f"数据集拆分完成，已保存至 {out_dir}")

    # ==================== 合并 COCO 数据集 ====================
    def merge_coco_datasets(self):
        # 选择多个JSON文件
        json_paths = filedialog.askopenfilenames(
            title="选择要合并的COCO JSON文件（可多选）",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not json_paths:
            return

        datasets = []
        for jpath in json_paths:
            # 为每个JSON询问图片文件夹
            img_dir = filedialog.askdirectory(title=f"选择JSON对应的图片文件夹\n{jpath}")
            if not img_dir:
                return
            try:
                with open(jpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                datasets.append({
                    'json_path': jpath,
                    'img_dir': img_dir,
                    'data': data
                })
            except Exception as e:
                messagebox.showerror("错误", f"无法加载 {jpath}: {e}")
                return

        if not datasets:
            return

        # 选择输出目录
        out_dir = filedialog.askdirectory(title="选择合并后数据集的输出目录")
        if not out_dir:
            return

        # 创建 images 目录
        images_out_dir = os.path.join(out_dir, 'images')
        os.makedirs(images_out_dir, exist_ok=True)

        # 类别合并：按名称合并
        category_name_to_new_id = {}
        new_categories = []
        new_category_id = 1
        # 同时记录每个数据集的旧类别ID到新类别ID的映射
        old_to_new_cat_maps = []  # 每个元素是一个 dict

        for ds in datasets:
            cat_map = {}
            for cat in ds['data'].get('categories', []):
                name = cat['name']
                if name not in category_name_to_new_id:
                    category_name_to_new_id[name] = new_category_id
                    new_categories.append({'id': new_category_id, 'name': name})
                    new_category_id += 1
                cat_map[cat['id']] = category_name_to_new_id[name]
            old_to_new_cat_maps.append(cat_map)

        # 图片合并：重新编号
        new_images = []
        new_annotations = []
        new_image_id = 1
        # 用于处理图片文件名冲突
        used_filenames = set()

        for ds_idx, ds in enumerate(datasets):
            img_dir = ds['img_dir']
            data = ds['data']
            cat_map = old_to_new_cat_maps[ds_idx]

            # 建立原图片ID到新图片ID的映射
            old_img_id_to_new = {}

            for img in data.get('images', []):
                old_id = img['id']
                fname = img['file_name']
                # 检查文件名冲突
                base, ext = os.path.splitext(fname)
                new_fname = fname
                counter = 1
                while new_fname in used_filenames:
                    new_fname = f"{base}_{counter}{ext}"
                    counter += 1
                used_filenames.add(new_fname)

                # 复制图片
                src_path = os.path.join(img_dir, fname)
                dst_path = os.path.join(images_out_dir, new_fname)
                if os.path.isfile(src_path):
                    shutil.copy2(src_path, dst_path)
                else:
                    print(f"警告：图片不存在 {src_path}")

                # 构建新图片信息
                new_img = img.copy()
                new_img['id'] = new_image_id
                new_img['file_name'] = new_fname
                new_images.append(new_img)

                old_img_id_to_new[old_id] = new_image_id
                new_image_id += 1

            # 处理标注
            for ann in data.get('annotations', []):
                old_img_id = ann['image_id']
                if old_img_id not in old_img_id_to_new:
                    continue  # 图片可能未找到
                new_ann = {
                    'id': len(new_annotations) + 1,
                    'image_id': old_img_id_to_new[old_img_id],
                    'category_id': cat_map.get(ann['category_id'], 0),  # 映射后的类别ID
                    'bbox': ann.get('bbox'),
                    'segmentation': ann.get('segmentation'),
                    'area': ann.get('area', 0),
                    'iscrowd': ann.get('iscrowd', 0)
                }
                new_annotations.append(new_ann)

        # 构建最终COCO JSON
        merged_coco = {
            'images': new_images,
            'annotations': new_annotations,
            'categories': new_categories
        }

        # 保存JSON
        json_out = os.path.join(out_dir, '_annotations.coco.json')
        with open(json_out, 'w', encoding='utf-8') as f:
            json.dump(merged_coco, f, indent=2)

        messagebox.showinfo("完成", f"合并完成！\n输出目录：{out_dir}\n总图片数：{len(new_images)}\n总标注数：{len(new_annotations)}")

if __name__ == "__main__":
    root = tk.Tk()
    app = YOLOViewer(root)
    root.mainloop()
