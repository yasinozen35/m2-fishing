import ctypes
from ctypes import wintypes
import subprocess

def test_windows():
    user32 = ctypes.windll.user32
    windows = []
    
    def callback(hwnd, extra):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value
                
                if "metin2" in title.lower():
                    # Get class name
                    class_buff = ctypes.create_unicode_buffer(256)
                    user32.GetClassNameW(hwnd, class_buff, 256)
                    class_name = class_buff.value
                    
                    # Get PID
                    pid = ctypes.c_ulong()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    
                    # Get Process Name via tasklist
                    try:
                        out = subprocess.check_output(f'tasklist /fi "PID eq {pid.value}" /fo csv /nh', shell=True).decode('utf-8', errors='ignore')
                        pname = out.split(',')[0].strip('"')
                    except:
                        pname = "unknown"
                        
                    windows.append({
                        "hwnd": hwnd,
                        "title": title,
                        "class": class_name,
                        "pid": pid.value,
                        "process": pname
                    })
        return True

    CMPFUNC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    cb_func = CMPFUNC(callback)
    user32.EnumWindows(cb_func, 0)
    
    for w in windows:
        print(w)

if __name__ == "__main__":
    test_windows()
