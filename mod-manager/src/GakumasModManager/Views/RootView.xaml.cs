using System.Windows;
using GakumasModManager.ViewModels;

namespace GakumasModManager.Views;

public partial class RootView : Window
{
    public RootView()
    {
        InitializeComponent();
    }

    private void OnDragOver(object sender, DragEventArgs e)
    {
        e.Effects = e.Data.GetDataPresent(DataFormats.FileDrop) ? DragDropEffects.Copy : DragDropEffects.None;
        e.Handled = true;
    }

    private void OnDrop(object sender, DragEventArgs e)
    {
        if (DataContext is RootViewModel viewModel
            && e.Data.GetData(DataFormats.FileDrop) is string[] paths)
        {
            viewModel.InstallDroppedPaths(paths);
        }
    }
}
