#!/usr/bin/env bash
# Build the legacy OES sources without changing them or installing system packages.
# Usage: bash build.sh SOURCE_ROOT SYSROOT BUILD_DIR
# SOURCE_ROOT contains oes_source/, module/, and optionally module-unstable/.
# SYSROOT contains extracted development/runtime .deb packages under usr/.
# OES_DEFER_RUNTIME_CHECK=1 allows a build on a noexec filesystem. The caller
# must then verify dependencies and execution from the isolated deployment path.
set -euo pipefail
export LC_ALL=C
umask 027
defer_runtime_check=${OES_DEFER_RUNTIME_CHECK:-0}
case "$defer_runtime_check" in
    0|1) ;;
    *) printf 'OES_DEFER_RUNTIME_CHECK must be 0 or 1.\n' >&2; exit 2 ;;
esac

if [[ $# -ne 3 ]]; then
    printf 'Usage: %s SOURCE_ROOT SYSROOT BUILD_DIR\n' "$0" >&2
    exit 2
fi
source_root=$(realpath -e -- "$1")
sysroot=$(realpath -e -- "$2")
mkdir -p -- "$3"
# Keep systemd's logical StateDirectory path. Resolving its symlink would bake
# /var/lib/private into tool arguments and diagnostics instead of the service's
# stable /var/lib/<name> entry point. Resolve separately only for overlap checks.
build_dir=$(realpath -s -e -- "$3")
build_realpath=$(realpath -e -- "$3")
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
case "$build_realpath/" in
    "$source_root/"*|"$sysroot/"*)
        printf 'BUILD_DIR must be outside SOURCE_ROOT and SYSROOT.\n' >&2
        exit 2
        ;;
esac
[[ $(uname -s) == Linux && $(uname -m) == x86_64 ]] || {
    printf 'This baseline targets native x86_64 Linux only.\n' >&2
    exit 2
}

cc=${CC:-gcc}
ar=${AR:-ar}
for tool in "$cc" "$ar" python3 sha256sum readelf ldd; do
    command -v "$tool" >/dev/null
done
multiarch=$("$cc" -print-multiarch)
[[ -n "$multiarch" ]] || { printf 'Compiler has no multiarch target.\n' >&2; exit 2; }
lib_dir="$sysroot/usr/lib/$multiarch"
include_dir="$sysroot/usr/include"
[[ -f "$include_dir/event2/event.h" ]]
[[ -f "$lib_dir/libevent_core.a" ]]
if [[ -f "$include_dir/mysql/mysql.h" && -e "$lib_dir/libmysqlclient.so" ]]; then
    mysql_lib=-lmysqlclient
elif [[ -f "$include_dir/mariadb/mysql.h" && -e "$lib_dir/libmariadb.so" ]]; then
    mysql_lib=-lmariadb
else
    printf 'Missing isolated MySQL/MariaDB headers and client library.\n' >&2
    exit 2
fi

mkdir -p -- "$build_dir/src" "$build_dir/obj" "$build_dir/lib" "$build_dir/bin"
exec > >(tee "$build_dir/build.log") 2>&1
printf 'BUILD_START %s\n' "$(date --iso-8601=seconds)"
printf 'SOURCE_ROOT=%s\nSYSROOT=%s\nBUILD_DIR=%s\n' "$source_root" "$sysroot" "$build_dir"
{
    uname -srmo
    "$cc" --version
    "$ar" --version
    getconf GNU_LIBC_VERSION
    printf 'MYSQL_LINK=%s\nMULTIARCH=%s\n' "$mysql_lib" "$multiarch"
} > "$build_dir/toolchain.txt"
cat "$build_dir/toolchain.txt"

# Copy source files only: never copy old objects, executables, credentials,
# production configuration, state, logs, or version-control metadata.
python3 - "$source_root" "$build_dir/src" <<'PY'
from pathlib import Path
import shutil
import sys

origin, target = map(Path, sys.argv[1:])
for relative in ('module', 'oes_source', 'oes_source/httpportal',
                 'oes_source/okernel', 'oes_source/dispatcher'):
    src = origin / relative
    dst = target / relative
    if not src.is_dir():
        raise SystemExit(f'Missing source directory: {src}')
    dst.mkdir(parents=True, exist_ok=True)
    for path in sorted(src.iterdir()):
        if path.is_file() and path.suffix in ('.c', '.h'):
            shutil.copyfile(path, dst / path.name)
PY

# Any narrow compatibility fixes live alongside this harness, not in the
# original source checkout. Each fresh source copy receives the same patches.
shopt -s nullglob
patches=("$script_dir"/patches/*.patch)
if (( ${#patches[@]} )); then
    command -v patch >/dev/null
    for patch_file in "${patches[@]}"; do
        printf 'APPLY_PATCH %s\n' "$(basename -- "$patch_file")"
        patch --batch --forward -d "$build_dir/src" -p1 < "$patch_file"
    done
fi

# The legacy headers use <mysql/mysql.h>. With mariadb-dev alone, create a
# private include alias; mariadb-dev-compat already supplies this alias.
compat_include="$build_dir/compat-include"
mkdir -p -- "$compat_include"
if [[ ! -f "$include_dir/mysql/mysql.h" ]]; then
    ln -sfn -- "$include_dir/mariadb" "$compat_include/mysql"
fi

cflags=(
    -std=gnu11 -O2 -g -Wall -Wextra -fno-common
    -Werror=implicit-function-declaration -Werror=incompatible-pointer-types
    -Werror=int-conversion -pthread
    -I"$build_dir/src/module" -I"$compat_include" -I"$include_dir"
    -I"$include_dir/mariadb" -I"$include_dir/mysql"
)
ldflags=(
    -L"$lib_dir" -Wl,-rpath,"$lib_dir" -Wl,-rpath-link,"$lib_dir"
    -pthread -lrt -lz
)
# Dependency closure of the three OES executables. The unreferenced utility
# modules and module-unstable/cJSON are deliberately outside this build.
modules=(
    common config convert avltree avltree16 avltree32 avlload
    dblog filelog http ipauth ipc queue rtree strplus
)
objects=()
for module in "${modules[@]}"; do
    obj="$build_dir/obj/$module.o"
    printf 'COMPILE module/%s.c\n' "$module"
    "$cc" "${cflags[@]}" -c "$build_dir/src/module/$module.c" -o "$obj"
    objects+=("$obj")
done
# Recreate the archive so an older, unreferenced member cannot survive a rerun.
rm -f -- "$build_dir/lib/libmodule.a"
"$ar" rcs "$build_dir/lib/libmodule.a" "${objects[@]}"

for program in httpportal okernel dispatcher; do
    printf 'COMPILE oes_source/%s/%s.c\n' "$program" "$program"
    # These source files include their sibling .c files; compile each once.
    "$cc" "${cflags[@]}" -c "$build_dir/src/oes_source/$program/$program.c" \
        -o "$build_dir/obj/$program.o"
    extra_libs=()
    if [[ "$program" != dispatcher ]]; then
        extra_libs=("$mysql_lib" -lcrypto)
    fi
    printf 'LINK %s\n' "$program"
    "$cc" -o "$build_dir/bin/$program" "$build_dir/obj/$program.o" \
        "$build_dir/lib/libmodule.a" "$lib_dir/libevent_core.a" \
        "${ldflags[@]}" "${extra_libs[@]}"
    readelf -h -d "$build_dir/bin/$program" > "$build_dir/$program.elf.txt"
    if [[ "$defer_runtime_check" == 1 ]]; then
        # StateDirectory may be mounted noexec in a hardened systemd unit.
        # Do not weaken that mount: record the static ELF metadata and require
        # a separate check after copying to the read-only deployment directory.
        printf 'DEPENDENCY_CHECK_DEFERRED %s: static ELF metadata only; verify from deployment path\n' \
            "$program" | tee "$build_dir/$program.ldd.txt"
        readelf -d "$build_dir/bin/$program" | grep -E '\((NEEDED|RPATH|RUNPATH)\)'
    else
        ldd "$build_dir/bin/$program" > "$build_dir/$program.ldd.txt"
        cat "$build_dir/$program.ldd.txt"
        if grep -q 'not found' "$build_dir/$program.ldd.txt"; then
            printf 'Unresolved runtime library for %s.\n' "$program" >&2
            exit 1
        fi
    fi
done
(
    cd -- "$build_dir"
    find src -type f \( -name '*.c' -o -name '*.h' \) -print0 \
        | sort -z | xargs -0 sha256sum
    sha256sum bin/httpportal bin/okernel bin/dispatcher lib/libmodule.a
) > "$build_dir/manifest.sha256"
printf 'BUILD_SUCCESS %s\n' "$(date --iso-8601=seconds)"
if [[ "$defer_runtime_check" == 1 ]]; then
    printf 'RUNTIME_VALIDATION_PENDING: dependency loading and execution must be checked at deployment.\n'
fi
