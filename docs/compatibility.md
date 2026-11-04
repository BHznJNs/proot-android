# 构建兼容处理

本项目以 PRoot 原有进程模型为基础，通过编译、链接及宿主构建适配生成独立 Android 应用可使用的产物。以下记录对应已验证的构建基线。

## string.h 的间接包含依赖

`extension/ashmem_memfd/ashmem_memfd.c` 使用 `strcmp()`、`memset()`，但没有直接包含 `<string.h>`。使用 stock NDK r30、Clang 21 和 GNU C11 编译时，出现两处隐式函数声明错误。

Termux 会修改 NDK 的 `stdio.h`。其补丁为了实现调用 `strcpy()` 的 `ctermid()`，加入了 `<string.h>`。结合 talloc 2.5.0 的头文件，形成以下包含链：

```text
ashmem_memfd.c
  -> talloc.h
    -> stdio.h（Termux 补丁）
      -> string.h
```

原生 NDK 没有这层间接包含，因此暴露了该源文件的声明依赖。这个问题不代表系统缺少 string.h，也不代表程序运行时必须依赖 Termux App。

2026-11-04，针对同一个源文件、同一个 Clang 21、相同的 ARM64/API 28/GNU C11 配置进行了 `-fsyntax-only` 对照：

| 条件 | 退出码 | 结果 |
| --- | --- | --- |
| 原生 NDK，无强制包含 | 1 | 两处隐式函数声明错误 |
| 临时 stdio.h 副本应用 Termux 官方补丁 | 0 | 无相关诊断 |
| 原生 NDK，定向 `-include string.h` | 0 | 无相关诊断 |

对照实验没有修改系统 NDK 或 PRoot 仓库源码，也没有执行 Android 程序。本项目在 `ndk_cc.py` 中只对该编译单元加入 `-include string.h`，没有关闭隐式声明错误检查。若以后选择修复 PRoot 源码，可直接在该文件添加 `#include <string.h>`。

另行降级诊断为警告也能让这个文件通过语法检查，但已查明的 Termux 成功原因是补丁引入的包含链，无需以编译器宽松程度解释。

依据：[PRoot 源文件](https://github.com/termux/proot/blob/52d65a4dc140ca554d241a1438ddd4f6b00c9813/src/extension/ashmem_memfd/ashmem_memfd.c)、[Termux stdio.h 补丁](https://github.com/termux/termux-packages/blob/master/ndk-patches/30/stdio.h.patch)、[Termux 工具链设置](https://github.com/termux/termux-packages/blob/master/scripts/build/toolchain/termux_setup_toolchain_30.sh)。Termux 的 master 链接内容可能随时间变化。

## 其他已采用的构建处理

| 处理 | 原因与实现 |
| --- | --- |
| 在源码副本中构建 | 原始 Makefile 的外部目录模式曾出现 SRC 与 VPATH 展开路径重复；复制 src 后保持 Makefile 原样执行 |
| 先生成 build.h | 显式完成平台编译/链接探测，再并行构建其他目标 |
| `-m32` 映射 | 将 Makefile 的兼容调用映射到 `armv7a-linux-androideabi28`，并使用 `-marm` |
| `/dev/null` 探测输出 | Windows 编译器包装器使用临时输出文件接收 Makefile 的链接探测结果 |
| 主程序 PIE | 保留 Android 可执行程序模型，通过子进程启动 |
| 独立 loader | 设置 `PROOT_UNBUNDLE_LOADER`，运行时显式传入实际安装位置 |
| 静态 talloc + libreplace | 补齐 talloc 所需的 `rep_memset_explicit` 等实现，减少应用运行时附带的动态依赖 |
| 16 KB 对齐 | 主程序和两个 loader 显式设置相应链接参数，并检查最终 ELF |
| 路径映射 | 使用 `-ffile-prefix-map` 避免将构建机源码路径直接写入产物 |
| Git Bash 与 junction | 为 talloc 的 Waf 提供 `/bin/sh` 调用适配和 Windows 宿主目录链接能力 |

## cross-answers 与运行验证

talloc 的交叉配置使用预设 cross-answers，因为 Windows 无法直接执行生成的 Android ELF。编译器仍会进行相应的编译/链接检查，但预设答案不是目标设备运行结果。

同样，`HAVE_PROCESS_VM`、`HAVE_SECCOMP_FILTER` 表示本次构建探测支持相应接口，不表示所有 Android 内核或应用沙箱都已通过运行测试。

## 可选依赖

本次未启用 `PROOT_WITH_LIBANDROID_SHMEM`，使用 PRoot 自带的 SysV IPC 实现。跨独立会话的共享内存行为未验证。若以后启用该选项，应同时记录新增链接依赖、路径配置和实际设备验证结果。
