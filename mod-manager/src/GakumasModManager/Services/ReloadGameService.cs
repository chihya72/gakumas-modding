using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Threading;
using GakumasModManager.Core;
using GakumasModManager.Models;

namespace GakumasModManager.Services;

public interface IReloadGameService
{
    OperationResult SendReloadKey(string gamePath);
}

public sealed class ReloadGameService : IReloadGameService
{
    private const ushort VkF10 = 0x79;
    private const byte VkF10Byte = 0x79;
    private const byte ScanCodeF10Byte = 0x44;
    private const ushort ScanCodeF10 = 0x44;
    private const uint InputKeyboard = 1;
    private const uint KeyEventScanCode = 0x0008;
    private const uint KeyEventKeyUp = 0x0002;
    private const uint WmKeyDown = 0x0100;
    private const uint WmKeyUp = 0x0101;
    private const int ShowRestore = 9;

    public OperationResult SendReloadKey(string gamePath)
    {
        var gameRoot = NormalizeGameRoot(gamePath);
        var candidate = FindGameWindow(gameRoot);
        if (candidate is null)
        {
            return new OperationResult(
                false,
                $"未找到游戏窗口。请切回游戏手动按 F10，或确认游戏目录：{gameRoot}",
                Severity: "Warning");
        }

        if (!NativeMethods.IsWindow(candidate.Handle))
        {
            return new OperationResult(false, "找到的游戏窗口句柄已失效。", Severity: "Warning");
        }

        if (NativeMethods.IsIconic(candidate.Handle))
        {
            NativeMethods.ShowWindowAsync(candidate.Handle, ShowRestore);
            Thread.Sleep(120);
        }

        var foregroundRequested = ForceForegroundWindow(candidate.Handle);
        Thread.Sleep(220);

        if (NativeMethods.GetForegroundWindow() != candidate.Handle)
        {
            return new OperationResult(
                false,
                foregroundRequested
                    ? $"找到窗口“{candidate.Title}”，但系统未把焦点交给它。请手动切回游戏按 F10。"
                    : $"找到窗口“{candidate.Title}”，但前台激活失败。请手动切回游戏按 F10。",
                Severity: "Warning");
        }

        Thread.Sleep(450);

        var sendResult = SendF10WithSendInputBurst();
        Thread.Sleep(120);
        SendF10WithKeybdEvent();
        Thread.Sleep(120);
        var postResult = SendF10WithWindowMessage(candidate.Handle);
        var foregroundAfterSend = NativeMethods.GetForegroundWindow() == candidate.Handle;

        if (!sendResult.Ok && !postResult.Ok)
        {
            return new OperationResult(
                false,
                $"已切到“{candidate.Title}”，但自动 F10 未完整投递：SendInput={sendResult.Sent}/{sendResult.Expected}, err={sendResult.LastError}; PostMessage={postResult.Ok}, postErr={postResult.LastError}。请手动按 F10。",
                Severity: "Warning");
        }

        return new OperationResult(
            true,
            $"已执行自动 F10 尝试：“{candidate.Title}”，SendInput={sendResult.Sent}/{sendResult.Expected}, keybd_event=True, PostMessage={postResult.Ok}, postErr={postResult.LastError}, 前台仍为游戏={foregroundAfterSend}, 管理器管理员={IsCurrentProcessElevated()}。{PostMessageHint(postResult)}");
    }

    private static bool ForceForegroundWindow(nint handle)
    {
        var foreground = NativeMethods.GetForegroundWindow();
        var currentThreadId = NativeMethods.GetCurrentThreadId();
        var targetThreadId = NativeMethods.GetWindowThreadProcessId(handle, out _);
        var foregroundThreadId = foreground == nint.Zero
            ? 0
            : NativeMethods.GetWindowThreadProcessId(foreground, out _);

        var attachedTarget = false;
        var attachedForeground = false;
        try
        {
            if (targetThreadId != 0 && targetThreadId != currentThreadId)
            {
                attachedTarget = NativeMethods.AttachThreadInput(currentThreadId, targetThreadId, true);
            }

            if (foregroundThreadId != 0 && foregroundThreadId != currentThreadId && foregroundThreadId != targetThreadId)
            {
                attachedForeground = NativeMethods.AttachThreadInput(currentThreadId, foregroundThreadId, true);
            }

            NativeMethods.BringWindowToTop(handle);
            NativeMethods.SetFocus(handle);
            return NativeMethods.SetForegroundWindow(handle);
        }
        finally
        {
            if (attachedForeground)
            {
                NativeMethods.AttachThreadInput(currentThreadId, foregroundThreadId, false);
            }

            if (attachedTarget)
            {
                NativeMethods.AttachThreadInput(currentThreadId, targetThreadId, false);
            }
        }
    }

    private static SendInputResult SendF10WithSendInputBurst()
    {
        uint sent = 0;
        var lastError = 0;
        const int pulses = 3;
        for (var i = 0; i < pulses; i++)
        {
            var result = SendF10WithSendInputOnce();
            sent += result.Sent;
            lastError = result.LastError;
            Thread.Sleep(120);
        }

        const uint expected = pulses * 4;
        return new SendInputResult(sent == expected, sent, expected, lastError);
    }

    private static SendInputResult SendF10WithSendInputOnce()
    {
        var scanInputs = new[]
        {
            new NativeMethods.Input
            {
                Type = InputKeyboard,
                Union = new NativeMethods.InputUnion
                {
                    KeyboardInput = new NativeMethods.KeyboardInput
                    {
                        ScanCode = ScanCodeF10,
                        Flags = KeyEventScanCode,
                    },
                },
            },
            new NativeMethods.Input
            {
                Type = InputKeyboard,
                Union = new NativeMethods.InputUnion
                {
                    KeyboardInput = new NativeMethods.KeyboardInput
                    {
                        ScanCode = ScanCodeF10,
                        Flags = KeyEventScanCode | KeyEventKeyUp,
                    },
                },
            },
        };

        var vkInputs = new[]
        {
            new NativeMethods.Input
            {
                Type = InputKeyboard,
                Union = new NativeMethods.InputUnion
                {
                    KeyboardInput = new NativeMethods.KeyboardInput
                    {
                        VirtualKey = VkF10,
                    },
                },
            },
            new NativeMethods.Input
            {
                Type = InputKeyboard,
                Union = new NativeMethods.InputUnion
                {
                    KeyboardInput = new NativeMethods.KeyboardInput
                    {
                        VirtualKey = VkF10,
                        Flags = KeyEventKeyUp,
                    },
                },
            },
        };

        var sentScanDown = NativeMethods.SendInput(1, [scanInputs[0]], Marshal.SizeOf<NativeMethods.Input>());
        Thread.Sleep(100);
        var sentScanUp = NativeMethods.SendInput(1, [scanInputs[1]], Marshal.SizeOf<NativeMethods.Input>());
        Thread.Sleep(60);
        var sentVkDown = NativeMethods.SendInput(1, [vkInputs[0]], Marshal.SizeOf<NativeMethods.Input>());
        Thread.Sleep(100);
        var sentVkUp = NativeMethods.SendInput(1, [vkInputs[1]], Marshal.SizeOf<NativeMethods.Input>());

        var sent = sentScanDown + sentScanUp + sentVkDown + sentVkUp;
        const uint expected = 4;
        return new SendInputResult(sent == expected, sent, expected, Marshal.GetLastWin32Error());
    }

    private static void SendF10WithKeybdEvent()
    {
        NativeMethods.keybd_event(VkF10Byte, ScanCodeF10Byte, 0, 0);
        Thread.Sleep(150);
        NativeMethods.keybd_event(VkF10Byte, ScanCodeF10Byte, KeyEventKeyUp, 0);
    }

    private static WindowMessageResult SendF10WithWindowMessage(nint handle)
    {
        // lParam: repeat=1, scan=0x44, previous/up bits for keyup.
        var down = NativeMethods.PostMessage(handle, WmKeyDown, VkF10, 0x0044_0001);
        Thread.Sleep(100);
        var up = NativeMethods.PostMessage(handle, WmKeyUp, VkF10, unchecked((nint)0xC044_0001));
        return new WindowMessageResult(down && up, Marshal.GetLastWin32Error());
    }

    private static bool IsCurrentProcessElevated()
    {
        using var identity = WindowsIdentity.GetCurrent();
        var principal = new WindowsPrincipal(identity);
        return principal.IsInRole(WindowsBuiltInRole.Administrator);
    }

    private static string PostMessageHint(WindowMessageResult postResult)
    {
        if (postResult.Ok)
        {
            return "请以游戏内 d3dx.ini reloaded 提示为准。";
        }

        return postResult.LastError == 5
            ? "窗口消息被拒绝访问；若游戏内无提示，请以管理员运行管理器，或手动切回游戏按 F10。"
            : "若游戏内无提示，请手动切回游戏按 F10。";
    }

    private static string NormalizeGameRoot(string gamePath)
    {
        var path = string.IsNullOrWhiteSpace(gamePath)
            ? Directory.GetCurrentDirectory()
            : Environment.ExpandEnvironmentVariables(gamePath.Trim().Trim('"'));

        if (string.Equals(Path.GetFileName(path), "Mods", StringComparison.OrdinalIgnoreCase))
        {
            return Directory.GetParent(path)?.FullName ?? path;
        }

        return path;
    }

    private static GameWindowCandidate? FindGameWindow(string gameRoot)
    {
        var normalizedRoot = SafeFullPath(gameRoot);
        var processes = Process.GetProcesses()
            .Where(process => process.MainWindowHandle != nint.Zero)
            .OrderBy(process => process.ProcessName, StringComparer.OrdinalIgnoreCase);

        GameWindowCandidate? fallback = null;
        foreach (var process in processes)
        {
            string title;
            try
            {
                title = process.MainWindowTitle;
            }
            catch
            {
                continue;
            }

            if (string.IsNullOrWhiteSpace(title))
            {
                continue;
            }

            var handle = process.MainWindowHandle;
            if (IsProcessUnderGameRoot(process, normalizedRoot))
            {
                return new GameWindowCandidate(handle, title);
            }

            if (fallback is null && LooksLikeGakumasWindow(process.ProcessName, title))
            {
                fallback = new GameWindowCandidate(handle, title);
            }
        }

        return fallback;
    }

    private static bool IsProcessUnderGameRoot(Process process, string? normalizedRoot)
    {
        if (string.IsNullOrWhiteSpace(normalizedRoot))
        {
            return false;
        }

        try
        {
            var modulePath = process.MainModule?.FileName;
            if (string.IsNullOrWhiteSpace(modulePath))
            {
                return false;
            }

            var fullModulePath = SafeFullPath(modulePath);
            return fullModulePath is not null
                && fullModulePath.StartsWith(normalizedRoot, StringComparison.OrdinalIgnoreCase);
        }
        catch
        {
            return false;
        }
    }

    private static string? SafeFullPath(string path)
    {
        try
        {
            return Path.GetFullPath(path).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar)
                + Path.DirectorySeparatorChar;
        }
        catch
        {
            return null;
        }
    }

    private static bool LooksLikeGakumasWindow(string processName, string title)
    {
        return ContainsAny(processName, ["gakumas", "gkms", "gakuen", "idolmaster"])
            || ContainsAny(title, ["gakumas", "gkms", "gakuen", "idolmaster", "学園アイドルマスター", "学マス"]);
    }

    private static bool ContainsAny(string value, IEnumerable<string> needles)
    {
        return needles.Any(needle => value.Contains(needle, StringComparison.OrdinalIgnoreCase));
    }

    private sealed record GameWindowCandidate(nint Handle, string Title);

    private sealed record SendInputResult(bool Ok, uint Sent, uint Expected, int LastError);

    private sealed record WindowMessageResult(bool Ok, int LastError);
}
