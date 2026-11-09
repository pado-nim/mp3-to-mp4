"""
MP3 → MP4 변환기 (창으로 쓰는 프로그램)
- MP3 여러 개 + 배경 사진 → 곡 제목이 뜨고 연속 재생되는 MP4 한 개
- 유튜브 설명란용 타임스탬프(_chapters.txt)도 같이 생성
exe로 만들면 ffmpeg가 안에 들어 있어서 따로 설치할 것 없음.
"""
import json, os, queue, re, subprocess, sys, tempfile, threading

from PIL import Image, ImageDraw, ImageFilter, ImageFont

APP_NAME = 'MP3 → MP4 변환기'
NO_WINDOW = 0x08000000 if os.name == 'nt' else 0          # ffmpeg 검은 창 숨기기
FONT_CANDIDATES = [
    r'C:\Windows\Fonts\malgunbd.ttf', r'C:\Windows\Fonts\malgun.ttf',
    '/System/Library/Fonts/AppleSDGothicNeo.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
    '/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf',
]


# ───────────────────────── 변환 엔진 ─────────────────────────
def ffmpeg_path():
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(sys.argv[0])))
    for name in ('ffmpeg.exe', 'ffmpeg'):
        p = os.path.join(base, name)
        if os.path.exists(p): return p
    return 'ffmpeg'


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                          creationflags=NO_WINDOW, **kw)


def probe(path):
    """재생 시간, 제목, 가수 (ffmpeg -i 출력에서 읽음)"""
    err = run([ffmpeg_path(), '-hide_banner', '-i', path]).stderr
    m = re.search(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)', err)
    if not m: raise RuntimeError(f'오디오를 읽지 못했어요: {os.path.basename(path)}')
    dur = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    head = err.split('Stream #')[0]
    def tag(name):
        t = re.search(rf'^\s+{name}\s*:\s*(.+)$', head, re.M | re.I)
        return t[1].strip() if t else ''
    title = tag('title') or os.path.splitext(os.path.basename(path))[0]
    return dur, title, tag('artist')


def find_font():
    for f in FONT_CANDIDATES:
        if os.path.exists(f): return f
    return None


def _font(path, size):
    return ImageFont.truetype(path, size) if path else ImageFont.load_default()


def fit(draw, text, fp, size, max_w):
    while size > 20:
        f = _font(fp, size)
        if draw.textlength(text, font=f) <= max_w: return f
        size -= 4
    return _font(fp, size)


def make_background(bg_path, W, H):
    img = Image.open(bg_path).convert('RGB')
    s = max(W / img.width, H / img.height)
    img = img.resize((int(img.width * s) + 1, int(img.height * s) + 1), Image.LANCZOS)
    l, t = (img.width - W) // 2, (img.height - H) // 2
    img = img.crop((l, t, l + W, t + H))
    return Image.blend(img, Image.new('RGB', (W, H)), 0.35)


def render_frame(bg, tracks, idx, fp, show_list=True):
    W, H = bg.size; k = W / 1920
    img = bg.copy(); d = ImageDraw.Draw(img)
    if show_list:
        box = (int(60 * k), int(60 * k), int(760 * k), H - int(60 * k))
        panel = img.crop(box).filter(ImageFilter.GaussianBlur(18 * k))
        img.paste(Image.blend(panel, Image.new('RGB', panel.size), 0.45), box[:2])
        d = ImageDraw.Draw(img)
        d.text((100 * k, 95 * k), 'PLAYLIST', font=_font(fp, int(34 * k)), fill=(200, 200, 200))
        row = min(110 * k, (H - 260 * k) / max(len(tracks), 1))
        for i, t in enumerate(tracks):
            y = 170 * k + i * row; now = i == idx
            mm, ss = divmod(int(t['start']), 60)
            line = f"{i + 1:02d}  {t['title']}"
            f = fit(d, line, fp, int((40 if now else 34) * k), 560 * k)
            if now: d.rectangle((80 * k, y - 8 * k, 90 * k, y + 48 * k), fill=(255, 90, 90))
            d.text((110 * k, y), line, font=f, fill=(255, 255, 255) if now else (150, 150, 150))
            if row >= 70 * k:
                d.text((110 * k, y + 48 * k), f'{mm:02d}:{ss:02d}', font=_font(fp, int(22 * k)),
                       fill=(170, 170, 170) if now else (110, 110, 110))
    x0 = (840 if show_list else 120) * k
    t = tracks[idx]
    d.text((x0, H - 330 * k), 'NOW PLAYING', font=_font(fp, int(36 * k)), fill=(255, 90, 90))
    d.text((x0, H - 270 * k), t['title'], font=fit(d, t['title'], fp, int(96 * k), W - x0 - 60 * k),
           fill=(255, 255, 255), stroke_width=max(1, int(3 * k)), stroke_fill=(0, 0, 0))
    if t['artist']:
        d.text((x0, H - 140 * k), t['artist'], font=_font(fp, int(48 * k)), fill=(220, 220, 220),
               stroke_width=max(1, int(2 * k)), stroke_fill=(0, 0, 0))
    return img


def convert(tracks, bg_path, out_path, height=1080, show_list=True, progress=None, cancel=None):
    """tracks: [{'path','title','artist'}]  progress(0~1, 문구)"""
    progress = progress or (lambda p, s: None)
    W, H = (1920, 1080) if height == 1080 else (1280, 720)
    fp = find_font(); ff = ffmpeg_path()
    t0 = 0.0
    for t in tracks:
        if 'dur' not in t: t['dur'] = probe(t['path'])[0]
        t['start'] = t0; t0 += t['dur']
    total = t0
    bg = make_background(bg_path, W, H)
    with tempfile.TemporaryDirectory() as tmp:
        segs = []
        for i, t in enumerate(tracks):
            if cancel and cancel(): raise RuntimeError('취소했어요')
            png = os.path.join(tmp, f'f{i}.png'); render_frame(bg, tracks, i, fp, show_list).save(png)
            seg = os.path.join(tmp, f's{i}.mp4')
            cmd = [ff, '-y', '-hide_banner', '-loglevel', 'error', '-progress', 'pipe:1', '-nostats',
                   '-loop', '1', '-framerate', '2', '-i', png, '-i', t['path'],
                   '-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'stillimage', '-pix_fmt', 'yuv420p', '-r', '2',
                   '-c:a', 'aac', '-b:a', '192k', '-ar', '44100', '-ac', '2', '-shortest', seg]
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                 encoding='utf-8', errors='replace', creationflags=NO_WINDOW)
            for line in p.stdout:
                if line.startswith('out_time_us=') or line.startswith('out_time_ms='):
                    try: cur = int(line.split('=')[1]) / 1e6
                    except ValueError: continue
                    progress(min(0.98, (t['start'] + cur) / total), f"[{i + 1}/{len(tracks)}] {t['title']}")
                if cancel and cancel(): p.kill(); raise RuntimeError('취소했어요')
            p.wait()
            if p.returncode != 0: raise RuntimeError('ffmpeg 오류:\n' + p.stderr.read()[-1500:])
            segs.append(seg)
        lst = os.path.join(tmp, 'list.txt')
        with open(lst, 'w', encoding='utf-8') as f:
            for s in segs: f.write("file '" + s.replace("'", "'\\''") + "'\n")
        progress(0.99, '이어 붙이는 중…')
        r = run([ff, '-y', '-hide_banner', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', lst,
                 '-c', 'copy', '-movflags', '+faststart', out_path])
        if r.returncode != 0: raise RuntimeError('ffmpeg 오류:\n' + r.stderr[-1500:])
    chap = os.path.splitext(out_path)[0] + '_chapters.txt'
    with open(chap, 'w', encoding='utf-8') as f:
        for t in tracks:
            h, rem = divmod(int(t['start']), 3600); m, s = divmod(rem, 60)
            ts = f'{h}:{m:02d}:{s:02d}' if total >= 3600 else f'{m:02d}:{s:02d}'
            f.write(f"{ts} {t['title']}{' - ' + t['artist'] if t['artist'] else ''}\n")
    progress(1.0, '완료!')
    return out_path, chap


# ───────────────────────── 화면 ─────────────────────────
def gui():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, simpledialog
    from PIL import ImageTk

    if os.name == 'nt':                                     # 고해상도 화면에서 글자 흐림 방지
        try:
            import ctypes; ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception: pass
    root = tk.Tk(); root.title(APP_NAME); root.geometry('880x560'); root.minsize(760, 480)
    style = ttk.Style()
    try: style.theme_use('vista' if os.name == 'nt' else 'clam')
    except Exception: pass
    style.configure('Big.TButton', font=('Malgun Gothic', 12, 'bold'), padding=8)

    tracks, state = [], {'bg': None, 'busy': False, 'cancel': False, 'thumb': None}
    q = queue.Queue()

    # 왼쪽: 곡 목록
    left = ttk.Frame(root, padding=12); left.pack(side='left', fill='both', expand=True)
    ttk.Label(left, text='곡 목록 (재생 순서)', font=('Malgun Gothic', 11, 'bold')).pack(anchor='w')
    lf = ttk.Frame(left); lf.pack(fill='both', expand=True, pady=6)
    lb = tk.Listbox(lf, font=('Malgun Gothic', 11), activestyle='none', selectmode='extended',
                    highlightthickness=1, relief='flat')
    sb = ttk.Scrollbar(lf, command=lb.yview); lb.config(yscrollcommand=sb.set)
    lb.pack(side='left', fill='both', expand=True); sb.pack(side='right', fill='y')
    ttk.Label(left, text='더블클릭하면 화면에 나올 제목을 바꿀 수 있어요', foreground='#666').pack(anchor='w')

    def fmt(sec): m, s = divmod(int(sec), 60); return f'{m}:{s:02d}'
    def refresh(sel=None):
        lb.delete(0, 'end')
        for i, t in enumerate(tracks):
            lb.insert('end', f"{i + 1:02d}.  {t['title']}{'  — ' + t['artist'] if t['artist'] else ''}   ({fmt(t['dur'])})")
        if sel is not None:
            for i in sel: lb.selection_set(i)
        total = sum(t['dur'] for t in tracks)
        info.set(f'{len(tracks)}곡 · 총 {fmt(total)}' if tracks else '곡을 추가하세요')

    def add():
        files = filedialog.askopenfilenames(title='MP3 추가', filetypes=[('오디오', '*.mp3 *.m4a *.wav *.flac *.ogg'), ('모든 파일', '*.*')])
        bad = []
        for f in sorted(files):
            try: d, ti, ar = probe(f); tracks.append({'path': f, 'title': ti, 'artist': ar, 'dur': d})
            except Exception: bad.append(os.path.basename(f))
        refresh()
        if bad: messagebox.showwarning(APP_NAME, '읽지 못한 파일:\n' + '\n'.join(bad))
    def remove():
        for i in reversed(lb.curselection()): tracks.pop(i)
        refresh()
    def move(dv):
        sel = list(lb.curselection())
        if not sel: return
        if dv < 0 and sel[0] == 0 or dv > 0 and sel[-1] == len(tracks) - 1: return
        for i in (sel if dv < 0 else reversed(sel)): tracks[i], tracks[i + dv] = tracks[i + dv], tracks[i]
        refresh([i + dv for i in sel])
    def rename(_=None):
        sel = lb.curselection()
        if not sel: return
        t = tracks[sel[0]]
        v = simpledialog.askstring(APP_NAME, '화면에 나올 제목', initialvalue=t['title'], parent=root)
        if v is not None and v.strip(): t['title'] = v.strip(); refresh([sel[0]])
    lb.bind('<Double-Button-1>', rename); lb.bind('<Delete>', lambda e: remove())

    bf = ttk.Frame(left); bf.pack(fill='x', pady=(6, 0))
    for txt, fn in [('＋ 추가', add), ('삭제', remove), ('▲ 위로', lambda: move(-1)), ('▼ 아래로', lambda: move(1)),
                    ('제목 바꾸기', rename), ('비우기', lambda: (tracks.clear(), refresh()))]:
        ttk.Button(bf, text=txt, command=fn).pack(side='left', padx=(0, 4))
    info = tk.StringVar(value='곡을 추가하세요')
    ttk.Label(left, textvariable=info, foreground='#333').pack(anchor='w', pady=(8, 0))

    # 오른쪽: 배경, 설정, 변환
    right = ttk.Frame(root, padding=12, width=330); right.pack(side='right', fill='y'); right.pack_propagate(False)
    ttk.Label(right, text='배경 사진', font=('Malgun Gothic', 11, 'bold')).pack(anchor='w')
    prev = tk.Label(right, text='(사진 없음)', bg='#222', fg='#aaa', width=300, height=169); prev.pack(pady=6)
    prev.config(width=40, height=9)
    def pick_bg():
        f = filedialog.askopenfilename(title='배경 사진', filetypes=[('이미지', '*.jpg *.jpeg *.png *.webp *.bmp')])
        if not f: return
        state['bg'] = f
        im = Image.open(f).convert('RGB'); im.thumbnail((300, 169))
        state['thumb'] = ImageTk.PhotoImage(im); prev.config(image=state['thumb'], text='', width=300, height=169)
        bgname.set(os.path.basename(f))
    bgname = tk.StringVar(value='')
    ttk.Button(right, text='사진 고르기', command=pick_bg).pack(fill='x')
    ttk.Label(right, textvariable=bgname, foreground='#666').pack(anchor='w')

    ttk.Separator(right).pack(fill='x', pady=10)
    show_list = tk.BooleanVar(value=True); ttk.Checkbutton(right, text='왼쪽에 곡 목록 보이기', variable=show_list).pack(anchor='w')
    res = tk.StringVar(value='1080p')
    rf = ttk.Frame(right); rf.pack(anchor='w', pady=4)
    ttk.Label(rf, text='화질').pack(side='left')
    ttk.Radiobutton(rf, text='1080p', value='1080p', variable=res).pack(side='left', padx=6)
    ttk.Radiobutton(rf, text='720p (빠름)', value='720p', variable=res).pack(side='left')

    ttk.Separator(right).pack(fill='x', pady=10)
    pb = ttk.Progressbar(right, maximum=1000); pb.pack(fill='x')
    status = tk.StringVar(value='준비됨'); ttk.Label(right, textvariable=status, wraplength=300).pack(anchor='w', pady=4)
    go = ttk.Button(right, text='MP4 만들기', style='Big.TButton'); go.pack(fill='x', side='bottom')

    def start():
        if state['busy']: state['cancel'] = True; status.set('취소하는 중…'); return
        if not tracks: return messagebox.showinfo(APP_NAME, '곡을 먼저 추가하세요.')
        if not state['bg']: return messagebox.showinfo(APP_NAME, '배경 사진을 골라 주세요.')
        out = filedialog.asksaveasfilename(title='저장할 곳', defaultextension='.mp4', initialfile='playlist.mp4',
                                           filetypes=[('MP4 영상', '*.mp4')])
        if not out: return
        state.update(busy=True, cancel=False); go.config(text='취소'); pb['value'] = 0
        job = [dict(t) for t in tracks]
        def work():
            try:
                r = convert(job, state['bg'], out, 1080 if res.get() == '1080p' else 720, show_list.get(),
                            progress=lambda p, s: q.put(('p', p, s)), cancel=lambda: state['cancel'])
                q.put(('done', r))
            except Exception as e: q.put(('err', str(e)))
        threading.Thread(target=work, daemon=True).start()
    go.config(command=start)

    def poll():
        try:
            while True:
                m = q.get_nowait()
                if m[0] == 'p': pb['value'] = m[1] * 1000; status.set(m[2])
                else:
                    state['busy'] = False; go.config(text='MP4 만들기')
                    if m[0] == 'done':
                        out, chap = m[1]; status.set('완료! ' + os.path.basename(out))
                        if messagebox.askyesno(APP_NAME, f'완료!\n{out}\n\n유튜브 타임스탬프: {os.path.basename(chap)}\n\n폴더를 열까요?'):
                            folder = os.path.dirname(out)
                            if os.name == 'nt': os.startfile(folder)
                            else: subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', folder])
                    else:
                        pb['value'] = 0; status.set(m[1].splitlines()[0])
                        if '취소' not in m[1]: messagebox.showerror(APP_NAME, m[1])
        except queue.Empty: pass
        root.after(100, poll)
    poll()

    # ffmpeg 확인
    try: run([ffmpeg_path(), '-version'])
    except FileNotFoundError:
        messagebox.showerror(APP_NAME, 'ffmpeg를 찾지 못했어요. exe 버전을 쓰거나 ffmpeg를 설치해 주세요.')
    root.mainloop()


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--cli':          # 테스트용: app.py --cli bg.jpg out.mp4 a.mp3 b.mp3
        bg, out, files = sys.argv[2], sys.argv[3], sys.argv[4:]
        ts = [dict(zip(('dur', 'title', 'artist'), probe(f)), path=f) for f in files]
        print(convert(ts, bg, out, progress=lambda p, s: print(f'{p:5.0%} {s}')))
    else:
        gui()
