[CmdletBinding()]
param(
    [string]$ProcessName = 'gakumas',
    [string]$DllPath = (Join-Path $PSScriptRoot '..\dist\runtime\GakumasMIRuntime.dll'),
    [int]$TimeoutMilliseconds = 10000
)

$ErrorActionPreference = 'Stop'
$resolvedDll = (Resolve-Path -LiteralPath $DllPath).Path
$process = Get-Process -Name $ProcessName -ErrorAction Stop | Select-Object -First 1

if (-not ('GakumasMI.NativeInjector' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;

namespace GakumasMI {
    public static class NativeInjector {
        const uint PROCESS_CREATE_THREAD = 0x0002;
        const uint PROCESS_QUERY_INFORMATION = 0x0400;
        const uint PROCESS_VM_OPERATION = 0x0008;
        const uint PROCESS_VM_WRITE = 0x0020;
        const uint MEM_COMMIT = 0x1000;
        const uint MEM_RESERVE = 0x2000;
        const uint MEM_RELEASE = 0x8000;
        const uint PAGE_READWRITE = 0x04;
        const uint WAIT_OBJECT_0 = 0;

        [DllImport("kernel32.dll", SetLastError = true)]
        static extern IntPtr OpenProcess(uint access, bool inheritHandle, int processId);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern IntPtr VirtualAllocEx(IntPtr process, IntPtr address, UIntPtr size, uint allocationType, uint protection);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool VirtualFreeEx(IntPtr process, IntPtr address, UIntPtr size, uint freeType);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool WriteProcessMemory(IntPtr process, IntPtr address, byte[] buffer, UIntPtr size, out UIntPtr written);
        [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Ansi)]
        static extern IntPtr GetModuleHandle(string moduleName);
        [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Ansi)]
        static extern IntPtr GetProcAddress(IntPtr module, string procedureName);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern IntPtr CreateRemoteThread(IntPtr process, IntPtr attributes, UIntPtr stackSize, IntPtr startAddress, IntPtr parameter, uint flags, IntPtr threadId);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern uint WaitForSingleObject(IntPtr handle, uint milliseconds);
        [DllImport("kernel32.dll", SetLastError = true)]
        static extern bool GetExitCodeThread(IntPtr thread, out uint exitCode);
        [DllImport("kernel32.dll")]
        static extern bool CloseHandle(IntPtr handle);

        static void Check(bool condition, string operation) {
            if (!condition) throw new Win32Exception(Marshal.GetLastWin32Error(), operation);
        }

        public static void Inject(int processId, string dllPath, int timeoutMilliseconds) {
            uint access = PROCESS_CREATE_THREAD | PROCESS_QUERY_INFORMATION | PROCESS_VM_OPERATION | PROCESS_VM_WRITE;
            IntPtr process = OpenProcess(access, false, processId);
            Check(process != IntPtr.Zero, "OpenProcess failed");
            IntPtr remotePath = IntPtr.Zero;
            IntPtr thread = IntPtr.Zero;
            try {
                byte[] pathBytes = System.Text.Encoding.Unicode.GetBytes(dllPath + "\0");
                remotePath = VirtualAllocEx(process, IntPtr.Zero, (UIntPtr)pathBytes.Length, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
                Check(remotePath != IntPtr.Zero, "VirtualAllocEx failed");
                UIntPtr written;
                Check(WriteProcessMemory(process, remotePath, pathBytes, (UIntPtr)pathBytes.Length, out written), "WriteProcessMemory failed");
                Check(written.ToUInt64() == (ulong)pathBytes.Length, "WriteProcessMemory was incomplete");

                IntPtr kernel32 = GetModuleHandle("kernel32.dll");
                Check(kernel32 != IntPtr.Zero, "GetModuleHandle(kernel32) failed");
                IntPtr loadLibrary = GetProcAddress(kernel32, "LoadLibraryW");
                Check(loadLibrary != IntPtr.Zero, "GetProcAddress(LoadLibraryW) failed");

                thread = CreateRemoteThread(process, IntPtr.Zero, UIntPtr.Zero, loadLibrary, remotePath, 0, IntPtr.Zero);
                Check(thread != IntPtr.Zero, "CreateRemoteThread failed");
                Check(WaitForSingleObject(thread, (uint)timeoutMilliseconds) == WAIT_OBJECT_0, "Remote LoadLibrary timed out");
                uint result;
                Check(GetExitCodeThread(thread, out result), "GetExitCodeThread failed");
                Check(result != 0, "Remote LoadLibrary returned null");
            } finally {
                if (thread != IntPtr.Zero) CloseHandle(thread);
                if (remotePath != IntPtr.Zero) VirtualFreeEx(process, remotePath, UIntPtr.Zero, MEM_RELEASE);
                CloseHandle(process);
            }
        }
    }
}
'@
}

[GakumasMI.NativeInjector]::Inject($process.Id, $resolvedDll, $TimeoutMilliseconds)
Write-Output ([pscustomobject]@{
    Status = 'Injected'
    ProcessId = $process.Id
    DllPath = $resolvedDll
})
