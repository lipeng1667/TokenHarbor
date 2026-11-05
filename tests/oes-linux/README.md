# OES Linux 编译与功能验证

2026-11-05 已在 `tencent-3` 的 Ubuntu 26.04 / x86_64 / GCC 15.2 环境完成编译和隔离功能验证。结果及边界见 [验收报告](REPORT-2026-11-05.md)。测试程序已正常停止，文件保留用于复现。

这里保存构建脚本、一个最小兼容补丁、合成数据库 fixture、低流量功能探针及验收证据。原 OES 和公共库仓库没有修改；源码、旧对象、真实业务配置和数据库密码不进入本目录。

## 文件

- `prepare_source.py`：从三个原仓库打包受版本控制的 C 源码/头文件，并记录版本与哈希；不打包原配置、旧二进制及对象。
- `build.sh`：在新的输出目录构建必要公共模块及三个程序，使用 GNU C11 和 `-fno-common`，记录警告、ELF 和哈希。
- `patches/0001-kernel-private-inline.patch`：将同一翻译单元内部的两个函数改为 `static inline`，修复现代 GNU C11 链接错误。
- `launch.sh`：在 Linux 测试机创建限时、非 root、独立网络/IPC 的 systemd 单元。
- `run_functional.py`：初始化专用数据库、启动节点、验证拓扑和数据、检查落盘并正常退出。
- `functional_probe.py`：每轮最多提交两个有效订单，验证同步、查询、重复拒绝、异步回调、签名拒绝和准确扣费。
- `fixture.sql`、`configs/`：纯合成测试数据和带占位符的配置模板；[数据库说明](db-fixture.md)记录最小 schema 和权限。
- `evidence/2026-11-05/`：选定的无数据库密码测试证据。

## 复现已准备的测试环境

仅在获准使用的 `tencent-3` 上执行。不要在其他业务服务器直接运行这些命令，也不要对现有数据库应用 fixture。

远端目录：

```text
/srv/tokenharbor-oes-test/20261105/
  source/     原源码的构建副本
  packages/   从 Ubuntu 仓库下载的 .deb 与 SHA256 清单
  sysroot/    仅解包的 libevent/MariaDB 依赖
  harness/    本目录脚本、补丁、fixture、模板
  bin/        root 所有、0555 权限的三个新程序及测试文件链接
  evidence/   选定验收证据
/var/lib/tokenharbor-oes-test/
  build/      编译输出，位于 systemd 管理的 noexec 状态目录
  runs/       每轮独立配置、数据库、日志、CDR、订单历史和结果
  current     指向本轮 runs 子目录的链接
```

在远端以有权启动 transient systemd 单元的管理员执行：

```bash
bash /srv/tokenharbor-oes-test/20261105/harness/launch.sh /srv/tokenharbor-oes-test/20261105 build
bash /srv/tokenharbor-oes-test/20261105/harness/launch.sh /srv/tokenharbor-oes-test/20261105 functional
```

第一条重新编译并复制程序到只读部署目录；第二条创建全新的测试数据库，运行两笔订单后停止全部进程。无需打开防火墙端口、安装 Docker、修改现有服务或重启服务器。脚本不会建立开机启动单元。

`launch.sh` 限制总内存 900 MiB、禁止测试单元使用 Swap、CPU 最多单核的 50%、进程/线程数 96；编译限时 900 秒，功能测试限时 300 秒。网络 namespace 内只有回环接口。端口 19009、19011、19012、19100、19306 不映射到宿主机。

OES 配置及若干持久化文件按真实可执行文件目录解析。`bin/` 下固定链接指向 `state/current` 中的测试文件；日志/CDR 使用绝对路径。不能仅改变 cwd，也不能把可执行文件放在 noexec 状态目录里运行。链接只覆盖 fixture 用户 0 和两个测试 Dispatcher 槽位；扩大测试数据前须调整。

数据库使用 MariaDB 11.8.6 的独立二进制，显式 `--no-defaults`，不读取系统 MySQL 配置。应用登录密码每轮随机生成，只写入私有配置；管理员通过本轮动态系统用户的 Unix socket 认证。没有连接现有 PostgreSQL 或外部下游 API。

## 新环境准备说明

原源码父目录应包含 `oes_source`、`module`、`module-unstable` 三个 Git 仓库。打包示例：

```bash
python3 tests/oes-linux/prepare_source.py '/Users/kaka/Projects/C Programs' /tmp/tokenharbor-oes-source.tar.gz
```

本轮依赖使用 `apt-get download` 下载 `libevent-dev`、`libmariadb-dev`、`libmariadb-dev-compat`、`libmariadb3`、`mariadb-server-core`、`mariadb-server`、`mariadb-client-core`、`mariadb-common`、`liburing2`，随后只用 `dpkg-deb --extract` 解包到测试 sysroot。**未执行 `apt install` 或软件包维护脚本。** 系统已有 GCC、Make、binutils、glibc 开发文件、OpenSSL 3、zlib 及其他运行依赖。新的发行版须重新检查依赖和版本，不能假定这份包清单完整通用。

本轮 `StateDirectory` 被 systemd 挂载为 noexec，因此编译阶段显式使用 `OES_DEFER_RUNTIME_CHECK=1`；这只推迟动态加载检查。功能阶段从只读部署目录对三个 ELF 运行 `ldd` 并实际启动全部节点，完成了延期检查。

测试数据库和生成配置仍保留在服务器的私有状态目录中，不提交 Git。查看日志时不要输出生成配置中的数据库密码。清理应在确认没有测试单元运行后，仅处理上述两棵专用目录；现有业务服务不属于清理范围。
