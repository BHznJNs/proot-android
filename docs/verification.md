# 验证记录

## 交付基线：2026-11-04

| 项目 | 记录 |
| --- | --- |
| PRoot 提交 | `52d65a4dc140ca554d241a1438ddd4f6b00c9813` |
| NDK / 编译器 | `30.0.16248370` / Clang 21 |
| 目标 | ARM64，native API 28 |
| talloc | 2.5.0，静态链接所需 libreplace |
| libandroid-shmem | 未启用 |
| 源码变更 | 本次构建没有修改 PRoot C 源码和 Makefile |
| 运行测试 | 未进行；当时 ADB 无连接设备 |

## 已完成

- PRoot 主程序、ARM64 loader、ARM32 兼容 loader 实际编译链接成功。
- 主程序为 ELF64/AArch64/PIE，解释器为 `/system/bin/linker64`。
- 主程序的 DT_NEEDED 只有 `libdl.so`、`libc.so`，没有外部 talloc 依赖或 Termux 动态库搜索路径。
- 两个 loader 为对应架构的静态 ELF，无 PT_INTERP 和动态库依赖。
- 三份交付文件的 PT_LOAD 均为 16 KB 对齐。
- 已记录 strip 后的大小与 SHA256。
- 已完成[头文件问题的三组语法编译对照](compatibility.md#stringh-的间接包含依赖)。

基线大小：主程序 242,960 字节；ARM64 loader 17,800 字节；ARM32 loader 17,796 字节。完整 SHA256 和 ELF 信息分别见根目录 `verification.json`、`elf-details.txt`；原编译记录见 `build-log.txt`。

## 在本项目目录核对基线文件

```powershell
$baseline = Get-Content -Raw .\verification.json | ConvertFrom-Json
foreach ($file in $baseline.files) {
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $file.file).Hash
    if ($actual.ToLowerInvariant() -ne $file.sha256) {
        throw "Checksum mismatch: $($file.file)"
    }
}
```

此命令只核对文件与既有记录一致，不会验证可执行行为。`build.ps1` 重建后不会自动更新基线 JSON、ELF 记录和 ARM32 交付文件，详见[输出位置](build.md#输出位置)。

## 待进行的 Android 验证

1. 安装实际 APK，确认主程序和 loader 的解包位置及可执行性。
2. 从应用进程运行最小 ARM64 guest 命令，记录标准输出、错误和退出码。
3. 验证 ptrace/seccomp/SELinux 兼容性、子进程创建及进程树清理。
4. 验证应用后台、取消和退出时的会话行为；有交互终端需求时增加 PTY 测试。
5. 在 4 KB 与 16 KB 页大小设备上验证 APK、loader、guest ELF 和 guest 动态加载器的实际运行。

本次没有运行 PRoot 项目 tests，也没有安装 Android 测试 APK。编译记录中保留了上游代码的警告；编译成功不代表这些警告已修复。

后续结果应记录设备 ABI、Android/API/targetSdk、页大小、源码与二进制版本、实际命令和观测结果。只有对应操作实际成功后，才将其标为通过。
