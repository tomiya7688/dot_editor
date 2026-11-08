"""Keep signature-test processes inside an independently owned Windows job."""

import ctypes


# {
#   責務: [BasicJobLimits: Windows Jobの基本制限を表す]
#   フィールド: [process_time: プロセス時間, job_time: Job時間, flags: 制限フラグ, min_working_set: 最小領域, max_working_set: 最大領域, active_processes: プロセス数, affinity: CPU, priority: 優先度, scheduling: スケジューリング]
# }
class BasicJobLimits(ctypes.Structure):
    _fields_ = [
        ("process_time", ctypes.c_int64),
        ("job_time", ctypes.c_int64),
        ("flags", ctypes.c_uint32),
        ("min_working_set", ctypes.c_size_t),
        ("max_working_set", ctypes.c_size_t),
        ("active_processes", ctypes.c_uint32),
        ("affinity", ctypes.c_size_t),
        ("priority", ctypes.c_uint32),
        ("scheduling", ctypes.c_uint32),
    ]


# {
#   責務: [JobIoCounters: Windows Jobの入出力統計を表す]
#   フィールド: [read_ops: 読込回数, write_ops: 書込回数, other_ops: その他回数, read_bytes: 読込量, write_bytes: 書込量, other_bytes: その他量]
# }
class JobIoCounters(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_uint64)
        for name in (
            "read_ops",
            "write_ops",
            "other_ops",
            "read_bytes",
            "write_bytes",
            "other_bytes",
        )
    ]


# {
#   責務: [ExtendedJobLimits: Windows Jobの拡張制限を表す]
#   フィールド: [basic: 基本制限, io: 入出力統計, process_memory: プロセス上限, job_memory: Job上限, peak_process_memory: プロセス最大使用量, peak_job_memory: Job最大使用量]
# }
class ExtendedJobLimits(ctypes.Structure):
    _fields_ = [
        ("basic", BasicJobLimits),
        ("io", JobIoCounters),
        ("process_memory", ctypes.c_size_t),
        ("job_memory", ctypes.c_size_t),
        ("peak_process_memory", ctypes.c_size_t),
        ("peak_job_memory", ctypes.c_size_t),
    ]


# {
#   責務: [SignatureTestJob: 試験プロセスの子孫を独立したJobで回収する]
#   フィールド: [kernel32: Windows API, handle: Jobハンドル]
# }
class SignatureTestJob:
    # {
    #   責務: [__init__: 終了時に子孫を停止するJobを作成する]
    #   処理: [1: Windows APIを設定する, 2: Jobの制限を設定する]
    #   引数: [self: インスタンス]
    #   戻り値: [なし。失敗時は例外]
    # }
    def __init__(self):
        # Windows APIのハンドルをポインタ幅で扱う。
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        self.kernel32.CreateJobObjectW.restype = ctypes.c_void_p
        self.kernel32.SetInformationJobObject.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_uint32,
        ]
        self.kernel32.SetInformationJobObject.restype = ctypes.c_int
        self.kernel32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.kernel32.AssignProcessToJobObject.restype = ctypes.c_int
        self.kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        self.kernel32.CloseHandle.restype = ctypes.c_int
        self.handle = self.kernel32.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        # 最後のJobハンドルが閉じられた際に所属プロセスを停止させる。
        limits = ExtendedJobLimits()
        limits.basic.flags = 0x2000
        if not self.kernel32.SetInformationJobObject(
            self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            error = ctypes.get_last_error()
            try:
                self.close()
            except OSError as cleanup_error:
                raise cleanup_error from ctypes.WinError(error)
            raise ctypes.WinError(error)

    # {
    #   責務: [assign: 試験プロセスを保護用Jobへ入れる]
    #   処理: [1: 既に保持したプロセスハンドルをJobへ割り当てる]
    #   引数: [self: インスタンス, process_handle: 対象プロセスのハンドル]
    #   戻り値: [なし。失敗時は例外]
    # }
    def assign(self, process_handle):
        # PIDを再取得せず、起動時から保持したハンドルを使用する。
        if not self.kernel32.AssignProcessToJobObject(self.handle, process_handle):
            raise ctypes.WinError(ctypes.get_last_error())

    # {
    #   責務: [close: 保護用Jobのハンドルを閉じる]
    #   処理: [1: Jobハンドルを閉じる]
    #   引数: [self: インスタンス]
    #   戻り値: [なし。失敗時は例外]
    # }
    def close(self):
        # Jobの最後のハンドルを閉じて残った子孫を停止する。
        if self.handle:
            if not self.kernel32.CloseHandle(self.handle):
                raise ctypes.WinError(ctypes.get_last_error())
            self.handle = None
