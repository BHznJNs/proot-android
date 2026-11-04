# Windows 构建说明

## 前提

| 工具或输入 | 要求 |
| --- | --- |
| Android NDK | `30.0.16248370`；入口脚本会检查版本 |
| Python | 3.11.5 或更新版本 |
| Git for Windows | 提供 Git 及 Git Bash |
| PRoot 源码 | 单独检出的 `termux/proot` 或基于它的 fork，包含 Git 元数据 |
| talloc 源码 | 项目已附带 2.5.0 归档，入口脚本校验 SHA256 |

当前公开入口固定构建 ARM64 / API 28。`compile_proot.py` 虽然有 `--api` 参数，但 talloc 配置脚本固定为 API 28；不能仅修改该参数就宣称完成了其他 API 的一致构建。

## 执行构建

在本项目目录执行，以下假定源码仓库位于同级 `proot` 目录：

```powershell
.\build.ps1 -SourceRoot '..\proot'
```

按需显式指定工具位置：

```powershell
.\build.ps1 `
  -SourceRoot '<PRoot Git 检出目录>' `
  -NdkRoot '<NDK 30.0.16248370 目录>' `
  -PythonExecutable '<python.exe 路径>' `
  -BashExecutable '<Git Bash 的 bash.exe 路径>'
```

默认 NDK 位置为 `%LOCALAPPDATA%\Android\Sdk\ndk\30.0.16248370`。Git Bash 默认根据 PATH 中的 Git 安装位置推导。

`sources/proot.tar.gz` 用于保存交付基线源码；当前脚本仍要求传入 Git 检出目录，因为它读取 HEAD 的短提交号作为版本字符串。脚本会构建传入目录的实际 `src` 内容，不会自动切换或锁定到基线提交。需要复现某次构建时，应先确认对应源码检出状态。

## 执行流程

1. 校验工具路径、NDK 版本和 talloc 源码归档 SHA256。
2. 首次解包 talloc，在 `build-support/talloc-config` 中运行 Waf 交叉配置。
3. 编译 talloc 和所需的 libreplace，并生成静态归档。
4. 将 PRoot 的 `src` 原样复制到 `build-support/proot-arm64`，通过原始 GNUmakefile 编译。
5. 显式生成 `build.h`，编译主程序、ARM64 loader 和 ARM32 兼容 loader。
6. 把两个 ARM64 文件复制到 `jniLibs/arm64-v8a` 并 strip。

运行时依赖、编译器参数和 Windows 适配的原因见[兼容处理](compatibility.md)。

## 输出位置

| 位置 | 内容 |
| --- | --- |
| `jniLibs/arm64-v8a/libproot.so` | strip 后的主程序 |
| `jniLibs/arm64-v8a/libproot_loader.so` | strip 后的 ARM64 loader |
| `build-support/proot-arm64/loader/loader-m32` | 本次构建的 ARM32 loader |
| `build-support/talloc-configure.log` | 依赖配置日志 |
| `build-support/compile.log` | 编译与链接日志 |

当前 `build.ps1` 只更新两个 ARM64 交付文件。它不会自动更新 `compat/libproot_loader32.so`、`verification.json`、`elf-details.txt` 或根目录的 `build-log.txt`；这些仍是原交付基线记录。重新构建后需重新收集校验信息，不能继续把旧记录当作新产物的验证结果。

## 缓存与排错

- 入口脚本发现已有 talloc `config.h` 时会复用配置。更换工具链或修改依赖配置时，宜在新的构建项目副本中重新配置，避免混用缓存。
- 构建目录含 Windows junction。清理前应确认目标及其链接关系，不要盲目递归删除或跟随链接清理源目录。
- 先检查失败阶段对应的日志。`strcmp`/`memset` 的声明问题详见[头文件包含链](compatibility.md#stringh-的间接包含依赖)。
- 当前没有自动处理源码切换后的全部增量构建失效问题。更换源码基线时使用新的构建项目副本更容易获得可核对的结果。
