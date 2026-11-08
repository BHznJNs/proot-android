# proot-android

面向独立 Android 应用的 PRoot 定向构建项目。使用 Windows 版 Android NDK，为 ARM64 应用生成可通过子进程启动的 PRoot 和独立 loader，并提供构建脚本、源码归档及验证记录。基于 [termux/proot](https://github.com/termux/proot) 构建。

原始交付基线的编译与 ELF 检查记录保留在原验证文档中。端口映射和 Android 会话模式由本项目在构建副本中注入，上游源码目录保持原样；见 [端口映射扩展](extensions/port-map/README.md)及 [Android 会话模式](extensions/android-session/README.md)。

## 文档

- [项目文档入口](docs/index.md)
- [Windows 构建说明](docs/build.md)
- [Android 应用集成](docs/android-integration.md)
- [构建兼容处理与头文件问题](docs/compatibility.md)
- [验证结果与后续检查](docs/verification.md)

## 快速使用

直接集成时，将 `jniLibs/arm64-v8a` 中的两个文件复制到 Android 应用的 `app/src/main/jniLibs/arm64-v8a`，按[集成说明](docs/android-integration.md)配置解包和启动参数。Android 宿主应用及 rootfs 需要另外准备。

重新构建时，在本项目目录执行：

```powershell
.\build.ps1 -SourceRoot '..\proot'
```

`SourceRoot` 指向另外检出的原版 `termux/proot` 源码仓库，无需维护 PRoot fork。构建时自动复制源码、检查并应用本项目的接入补丁，再编译端口映射和 Android 会话扩展；不会修改输入仓库。完整前提、可选参数和产物位置见[构建说明](docs/build.md)。

## 原始交付基线

| 项目 | 当前记录 |
| --- | --- |
| PRoot 提交 | `52d65a4dc140ca554d241a1438ddd4f6b00c9813` |
| NDK | `30.0.16248370`，Clang 21 |
| 主程序 | Android ARM64，native API 28，PIE |
| talloc | 2.5.0，与所需 libreplace 实现静态链接 |
| 可选 libandroid-shmem | 未启用 |
| ELF 加载段 | 主程序和两个 loader 均为 16 KB 对齐 |
| Android 运行验证 | 尚未进行 |

`libproot.so` 和 loader 是用于 APK 打包的可执行 ELF，通过 `ProcessBuilder`/`exec` 启动。具体产物角色及限制见[项目文档](docs/index.md)。
