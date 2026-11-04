# 项目说明

## 目标与运行方式

本项目复用 `termux/proot` 的 Android 适配，构建供独立 Android 应用分发和启动的原生程序。当前构建没有修改 PRoot 的 C 源码或 GNUmakefile；兼容处理集中在本项目的构建脚本中。

```text
Android 应用的 Kotlin/Java 代码
  -> ProcessBuilder 或 PTY 启动器
    -> APK 安装目录中的 PRoot 可执行程序
      -> 独立 loader
        -> rootfs 内的 Linux 程序及其子进程
```

应用需要自行提供 rootfs、命令参数、输入输出及会话生命周期管理。PRoot 通过 ptrace 等机制工作，保留应用自身的 UID、SELinux 和 seccomp 限制。

## 项目目录

| 位置 | 内容 |
| --- | --- |
| `build.ps1` | Windows 构建入口 |
| `build-support/configure_talloc.py` | talloc 交叉配置及 Windows 宿主适配 |
| `build-support/compile_proot.py` | 静态依赖编译、源码副本构建、主程序和 loader 链接 |
| `build-support/ndk_cc.py` | NDK 编译器适配与单文件强制头文件包含 |
| `build-support/downloads` | 构建使用的 talloc 源码归档 |
| `jniLibs/arm64-v8a` | 可供 Android 应用打包的 ARM64 主程序和 loader |
| `compat` | ARM32 兼容 loader，需单独决定是否集成 |
| `sources` | 基线 PRoot/talloc 源码归档及 PRoot COPYING |
| `verification.json` | 交付基线的版本、大小、SHA256 和检查结果 |
| `elf-details.txt`、`build-log.txt` | 基线 ELF 详情和编译记录 |
| `docs` | 本项目的使用及实现说明 |

构建过程中会在 `build-support` 下生成依赖源码、Waf 配置、对象文件、源码副本和日志。传入的 PRoot 源码仓库不会被构建脚本改写。

## 文档阅读顺序

1. [构建说明](build.md)：准备工具链并重新生成产物。
2. [Android 集成](android-integration.md)：打包、loader 路径和最小启动示例。
3. [兼容处理](compatibility.md)：记录各项构建适配的原因和头文件问题的已验证结论。
4. [验证记录](verification.md)：查看已验证范围及仍需设备验证的项目。

后续构建或运行结果应在本项目内更新记录，并保留源码和许可证声明。
