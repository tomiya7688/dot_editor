# {
#   責務: [Enter-SignatureJob: 署名検査専用プロセスを子孫終了用Jobに所属させる]
#   処理: [1: Windows APIを読み込む, 2: Jobを作成して現在の専用プロセスを所属させる]
#   引数: [なし]
#   戻り値: [なし。失敗時は例外]
# }
function Enter-SignatureJob {
    # 32ビットの構造体レイアウトは検証していないため、失敗側へ倒す。
    if ([IntPtr]::Size -ne 8) {
        throw 'The signature job requires 64-bit PowerShell.'
    }
    # 専用プロセスの終了時にOSが最後のハンドルを閉じ、残った子孫も停止する。
    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;

// { 責務: [SignatureJob: 専用検査プロセスと子孫の寿命をOSに管理させる], フィールド: [なし] }
public static class SignatureJob
{
    // { 責務: [BasicLimits: Windowsの基本Job制限を表す], フィールド: [PerProcessUserTimeLimit: プロセス時間, PerJobUserTimeLimit: Job時間, LimitFlags: 有効な制限, MinimumWorkingSetSize: 最小ワーキングセット, MaximumWorkingSetSize: 最大ワーキングセット, ActiveProcessLimit: プロセス数上限, Affinity: CPU, PriorityClass: 優先度, SchedulingClass: スケジューリング] }
    [StructLayout(LayoutKind.Sequential)]
    private struct BasicLimits
    {
        public long PerProcessUserTimeLimit, PerJobUserTimeLimit;
        public uint LimitFlags;
        public UIntPtr MinimumWorkingSetSize, MaximumWorkingSetSize;
        public uint ActiveProcessLimit;
        public UIntPtr Affinity;
        public uint PriorityClass, SchedulingClass;
    }

    // { 責務: [IoCounters: WindowsのJob入出力カウンターを表す], フィールド: [ReadOperationCount: 読込回数, WriteOperationCount: 書込回数, OtherOperationCount: その他回数, ReadTransferCount: 読込量, WriteTransferCount: 書込量, OtherTransferCount: その他転送量] }
    [StructLayout(LayoutKind.Sequential)]
    private struct IoCounters
    {
        public ulong ReadOperationCount, WriteOperationCount, OtherOperationCount;
        public ulong ReadTransferCount, WriteTransferCount, OtherTransferCount;
    }

    // { 責務: [ExtendedLimits: Windowsの拡張Job制限を表す], フィールド: [BasicLimitInformation: 基本制限, IoInfo: 入出力統計, ProcessMemoryLimit: プロセスメモリ上限, JobMemoryLimit: Jobメモリ上限, PeakProcessMemoryUsed: プロセス最大使用量, PeakJobMemoryUsed: Job最大使用量] }
    [StructLayout(LayoutKind.Sequential)]
    private struct ExtendedLimits
    {
        public BasicLimits BasicLimitInformation;
        public IoCounters IoInfo;
        public UIntPtr ProcessMemoryLimit, JobMemoryLimit, PeakProcessMemoryUsed, PeakJobMemoryUsed;
    }

    // { 責務: [CreateJobObjectW: WindowsのJobを作成する], 処理: [1: kernel32へ委譲する], 引数: [attributes: セキュリティ属性, name: Job名], 戻り値: [Jobハンドル] }
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr CreateJobObjectW(IntPtr attributes, string name);
    // { 責務: [SetInformationJobObject: Jobの制限を設定する], 処理: [1: kernel32へ委譲する], 引数: [job: Jobハンドル, type: 情報種別, limits: 制限, size: 構造体のサイズ], 戻り値: [成功ならtrue] }
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool SetInformationJobObject(IntPtr job, int type, ref ExtendedLimits limits, int size);
    // { 責務: [AssignProcessToJobObject: プロセスをJobへ追加する], 処理: [1: kernel32へ委譲する], 引数: [job: Jobハンドル, process: プロセスハンドル], 戻り値: [成功ならtrue] }
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
    // { 責務: [GetCurrentProcess: 現在のプロセスを取得する], 処理: [1: kernel32へ委譲する], 引数: [なし], 戻り値: [現在プロセスの疑似ハンドル] }
    [DllImport("kernel32.dll")]
    private static extern IntPtr GetCurrentProcess();
    // { 責務: [CloseHandle: ハンドルを閉じる], 処理: [1: kernel32へ委譲する], 引数: [handle: 対象ハンドル], 戻り値: [成功ならtrue] }
    [DllImport("kernel32.dll")]
    private static extern bool CloseHandle(IntPtr handle);

    // { 責務: [Enter: 現在の専用プロセスを終了時に子孫を停止するJobへ追加する], 処理: [1: Jobと制限を作成する, 2: 所属させる], 引数: [なし], 戻り値: [なし。失敗時は例外] }
    public static void Enter()
    {
        // NULLのセキュリティ属性によりJobハンドルを子へ継承しない。
        IntPtr job = CreateJobObjectW(IntPtr.Zero, null);
        if (job == IntPtr.Zero) throw new Win32Exception(Marshal.GetLastWin32Error());
        var limits = new ExtendedLimits();
        limits.BasicLimitInformation.LimitFlags = 0x00002000;
        if (!SetInformationJobObject(job, 9, ref limits, Marshal.SizeOf<ExtendedLimits>()))
        {
            int error = Marshal.GetLastWin32Error();
            CloseHandle(job);
            throw new Win32Exception(error);
        }
        if (!AssignProcessToJobObject(job, GetCurrentProcess()))
        {
            int error = Marshal.GetLastWin32Error();
            CloseHandle(job);
            throw new Win32Exception(error);
        }
        // 現在の専用プロセスが終了するとOSがハンドルを閉じる。
    }
}
'@
    [SignatureJob]::Enter()
}
