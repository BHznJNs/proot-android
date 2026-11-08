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

## 构建时注入端口映射扩展（2026-11-08）

端口映射实现由本项目的 `extensions/port-map/port_map.c` 提供，四处编译和 CLI 接入修改保存在同目录 `integration.patch`。接入补丁已验证的 Termux PRoot 基线为 `52d65a4dc140ca554d241a1438ddd4f6b00c9813`；输入仓库保持原样，无需维护带功能修改的 PRoot 分支。

每次构建在经过路径检查的生成目录中创建新副本，先检查全部补丁，再在副本应用补丁并复制扩展。补丁命令通过 Git 搜索边界与输入仓库隔离，并显式验证四个接入点，避免 Git 在宿主仓库子目录中跳过补丁却返回成功。旧对象和注入文件不会跨构建复用。完整版本字符串、输入版本及源码／扩展／补丁散列写入 `build-support/build-manifest.json`。

验证结果：

- 5 项 Python 构建准备测试通过：只修改副本、原始源码散列不变、在另一个 Git 仓库内部正确注入、不兼容上游拒绝、重复注入拒绝，以及既有构建目录和重叠路径拒绝。
- 从恢复原版内容的 PRoot 输入构建主程序及 ARM64 / ARM32 loader 成功，接入编译单元在编译日志中确认。
- Android 12 ARM64 设备上的集成验证覆盖组件行为：IPv4 / IPv6 TCP / UDP 端口转换、并行 PRoot 会话使用独立宿主端口、非法映射拒绝、停止后端口复用。

本项目的本次编译日志为 `build-support/compile.log`，构建输入信息见 `build-support/build-manifest.json`。集成应用的界面、配置存储和服务生命周期测试由集成方记录。原 `verification.json`、`elf-details.txt` 和 `build-log.txt` 继续表示原始交付基线，不会被重建自动更新。

## 内置 Android 会话监督（2026-11-08）

新增可选的 `--android-session` 首参数入口，源码和接入补丁位于 `extensions/android-session`。同一个 ELF 内保留会话父进程与 PRoot worker，接管原来 App 独立 supervisor 的控制管道、信号掩码初始化、父进程死亡处理及等待退出。停止仍通过 SIGQUIT 触发 tracee 的 SIGKILL 清理；没有新增 guest TERM 宽限期。worker 在安装清理处理器后才解除启动阶段的 SIGQUIT 屏蔽，guest 则在进入 tracing 前清空掩码。未启用该模式的启动钩子为空操作。

验证结果：

- 6 项主机源码准备测试通过，包括会话接入点不兼容时在写入任何补丁前拒绝；原版 `proot` 仓库保持干净。
- NDK 30 / ARM64 API 28 构建主程序及 ARM64 / ARM32 loader 成功；会话源文件单独通过 `-Wall -Wextra -Werror -fsyntax-only` 检查，主程序 LOAD 段为 16 KB 对齐。
- Android 12 / ARM64 / 4 KB 页设备，从实际安装的 App 经 ART → ProcessBuilder 运行 8 项会话设备测试通过：停止字节、管道 EOF、TERM、会话父进程 SIGKILL、启动时立即取消（12 轮）、guest stdin EOF 和退出码、主命令退出清理后台子进程，以及普通 PRoot 入口回归。
- 同一设备另有 5 项集成测试通过：3 项端口映射（IPv4 / IPv6 TCP / UDP、并行会话、冲突、停止后重启及非法参数）、1 项真实 Alpine 拉取／启动／停止／重启／删除、1 项配置存储。合计 `OK (13 tests)`。
- 集成 App 的 APK 构建、21 项 JVM 测试及 Lint 通过；Lint 无错误，22 项警告位于既有配置、依赖及资源。APK 确认没有 `libsupervisor.so`，包含的 `libproot.so` 与本项目重建产物逐字节一致。

本轮未验证其他 Android 版本、16 KB 页设备、交互 PTY 或系统强行停止时的行为。原始日志、产物散列及集成记录位于同级集成工作区的 `build-results/android-session-*`，集成方的 `app/DEVICE_VALIDATION.md` 记录详细结果。原始交付基线记录继续保留。
