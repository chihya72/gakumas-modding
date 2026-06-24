# Mods

3DMigoto mod 安装目录。`d3dx.ini` 配置了 `include_recursive=Mods`,会递归扫描这里
的所有 `mod.ini`。

- 把 Blender 插件导出的 mod 文件夹整体放到这里(不要改名);
- 以 `DISABLED_` 开头的文件夹会被忽略,可用于临时禁用;
- 实际 mod 内容(buffer/贴图)体积较大,默认不入库(见仓库 `.gitignore`)。
