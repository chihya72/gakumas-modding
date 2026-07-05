using System.Windows;
using System.Windows.Controls;
using System.Windows.Data;
using GakumasModManager.ViewModels;

namespace GakumasModManager.Views;

public partial class RootView : Window
{
    // 记住每个角色分组的折叠状态，重扫后不复位（进程内，不持久化）
    private readonly Dictionary<string, bool> _groupExpanded = new();

    public RootView()
    {
        InitializeComponent();
    }

    private void OnGroupExpanderLoaded(object sender, RoutedEventArgs e)
    {
        if (sender is Expander expander
            && expander.DataContext is CollectionViewGroup { Name: string key }
            && _groupExpanded.TryGetValue(key, out var expanded))
        {
            expander.IsExpanded = expanded;
        }
    }

    private void OnGroupExpanderToggled(object sender, RoutedEventArgs e)
    {
        if (sender is Expander expander
            && expander.DataContext is CollectionViewGroup { Name: string key })
        {
            _groupExpanded[key] = expander.IsExpanded;
        }
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
