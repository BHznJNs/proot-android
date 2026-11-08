# Android 应用集成

## 产物角色

| 文件 | 含义 |
| --- | --- |
| `jniLibs/arm64-v8a/libproot.so` | ARM64 PIE 可执行程序 |
| `jniLibs/arm64-v8a/libproot_loader.so` | ARM64 静态 loader |
| `compat/libproot_loader32.so` | 可选 ARM32 guest 的兼容 loader |

这些文件采用 `.so` 后缀参与 APK 打包，通过 `ProcessBuilder`/`exec` 执行。它们没有提供可由 `System.loadLibrary()` 使用的 JNI 接口。主程序已静态链接 talloc，交付基线的动态依赖仅为系统 `libc.so`、`libdl.so`。

## APK 打包

把两个 ARM64 文件复制到应用的 `app/src/main/jniLibs/arm64-v8a`。Gradle Kotlin DSL 示例：

```kotlin
android {
    defaultConfig {
        minSdk = 28
        ndk { abiFilters += "arm64-v8a" }
    }
    packaging {
        jniLibs {
            useLegacyPackaging = true
            keepDebugSymbols += "**/libproot*.so"
        }
    }
}
```

安装后应确认两个文件真实存在于 `applicationInfo.nativeLibraryDir`。Android 对 targetSdk >= 29 的应用限制直接执行可写应用私有目录中的程序，因此不要用“从 assets 解压到 filesDir 再执行”的步骤替代 APK 安装目录中的主程序和 loader。[Android 行为变更](https://developer.android.com/about/versions/10/behavior-changes-10#execute-permission)

## loader 与 rootfs

loader 由同一份 PRoot 源码构建，按 PRoot 提供的信息加载 guest ELF。guest 自身需要的 Linux 动态加载器和库仍应存在于 rootfs 中。

| 配置 | 指向 |
| --- | --- |
| `PROOT_LOADER` | 已安装的 `libproot_loader.so` 绝对路径，必须显式设置 |
| `PROOT_TMP_DIR` | 应用可写、已存在的临时目录 |
| `-r` | 已正确解包、包含目标程序的 ARM64 rootfs |

构建使用的 `/proot-loader` 是通用回退位置，不是 Android 的实际安装目录。rootfs 和临时文件可以放在应用私有目录；loader 应使用 APK 安装后的文件。

## 最小启动示例

以下代码用于首次测试，假设 rootfs 内已有 `/bin/sh` 和 `uname`，并在后台线程执行：

```kotlin
val libs = context.applicationInfo.nativeLibraryDir
val temporary = File(context.cacheDir, "proot").apply { mkdirs() }
val rootfs = File(context.filesDir, "rootfs")

val pb = ProcessBuilder(
    "$libs/libproot.so",
    "-0", "-r", rootfs.absolutePath,
    "-b", "/dev", "-b", "/proc",
    "-w", "/", "/bin/sh", "-c", "echo proot-ok; uname -m"
)
pb.environment()["PROOT_LOADER"] = "$libs/libproot_loader.so"
pb.environment()["PROOT_TMP_DIR"] = temporary.absolutePath
pb.environment().remove("LD_PRELOAD")
pb.redirectErrorStream(true)
val child = pb.start()
val output = child.inputStream.bufferedReader().use { it.readText() }
val exitCode = child.waitFor()
```

这版不需要为 talloc 设置 `LD_LIBRARY_PATH`。上例一次性收集小量输出；长期任务应持续消费输出并控制缓存大小，交互式终端还需要 PTY、输入转发和窗口尺寸管理。

普通 PRoot 会启动 guest 进程树，停止逻辑需要管理整个会话；不能仅凭 `Process.destroy()` 就认定所有后代进程已回收。

## 非交互后台会话

长期服务建议以 `libproot.so --android-session --kill-on-exit ...` 启动；`--android-session` 必须是第一个参数。这个模式内置监督父进程和 PRoot worker，无需单独打包 `libsupervisor.so`，也不减少进程数。

宿主持有 `Process.outputStream` 作为控制管道；guest 的 stdin 为 `/dev/null`。停止时写入字节 `q` 并 flush，或者关闭控制管道。TERM/INT/QUIT 发给会话父进程也会请求停止。持续读取日志，并等待 `waitFor()` 后再把会话标记为已停止。

会话模式清空 ART 继承的信号屏蔽，处理管道 EOF 和父进程死亡；停止仍通过 worker 的 SIGQUIT 清理 tracee，属于立即强制清理，没有 guest TERM 宽限期。`--kill-on-exit` 同时确保主命令正常结束时清理后台子进程。普通启动方式不受影响。详细协议与启动竞态处理见 [Android 会话模式](../extensions/android-session/README.md)。

## 当前边界

- 首次集成仅使用 ARM64 guest。额外生成的 ARM32 loader 不代表设备支持 32 位执行；未来启用时需另行打包并设置 `PROOT_LOADER_32`。
- PRoot 使用应用现有权限，不能提供真实 root、完整 Docker 隔离或通用的内核能力。
- 应从实际安装的 APK 应用进程验证。adb shell 或 run-as 的成功不能替代应用内运行结果。
- 16 KB ELF 对齐已经检查，APK 打包、guest ELF 和设备上的实际运行仍需验证，见[验证记录](verification.md)。
