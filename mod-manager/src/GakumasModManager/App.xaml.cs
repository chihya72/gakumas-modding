using System.Windows;

namespace GakumasModManager;

public partial class App : Application
{
    private readonly Bootstrapper _bootstrapper = new();

    public App()
    {
        _bootstrapper.Setup(this);
    }

    protected override void OnExit(ExitEventArgs e)
    {
        _bootstrapper.Dispose();
        base.OnExit(e);
    }
}
