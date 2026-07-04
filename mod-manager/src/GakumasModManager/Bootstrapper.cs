using GakumasModManager.Services;
using GakumasModManager.ViewModels;
using Stylet;
using StyletIoC;

namespace GakumasModManager;

public sealed class Bootstrapper : Bootstrapper<RootViewModel>
{
    protected override void ConfigureIoC(IStyletIoCBuilder builder)
    {
        builder.Bind<IScannerService>().To<ScannerService>().InSingletonScope();
        builder.Bind<IPackageActionsService>().To<PackageActionsService>().InSingletonScope();
        builder.Bind<IReloadGameService>().To<ReloadGameService>().InSingletonScope();
        builder.Bind<IAppLogService>().To<AppLogService>().InSingletonScope();
        builder.Bind<ID3dxConfigService>().To<D3dxConfigService>().InSingletonScope();
        builder.Bind<IModManagerCore>().To<AsstProxy>().InSingletonScope();
    }
}
